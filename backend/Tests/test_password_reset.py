"""
Password reset flow and mail retry (A3.x, A16.x).

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import io
import os
import pickle
import smtplib
import socket
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from unittest import mock

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("testing_on", "1")
os.environ.setdefault("secret_key", "test")
os.environ.setdefault("session_cookie_secure", "0")
os.environ.setdefault("root_user_name", "root@ovgu.de")
os.environ.setdefault("root_user_password", "rootpassword1")
os.environ.setdefault("template_directory", os.path.join(os.path.dirname(_BACKEND), "templates"))
for _p in (_BACKEND, os.path.join(_BACKEND, "mutations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from argon2 import PasswordHasher  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

import app as app_module  # noqa: E402
import manage  # noqa: E402
import password_reset  # noqa: E402
import sendMail as send_mail_module  # noqa: E402
from config import db, engine  # noqa: E402
from models import Base, PasswordResetToken, User  # noqa: E402

ALICE = "alice@ovgu.de"
OLD_PASSWORD = "alice-old-password"
NEW_PASSWORD = "alice-new-password"
BASE_URL = "https://lending.example.test"

REQUEST = """mutation($email: String!) {
  requestPasswordReset(email: $email) { ok infoText statusCode } }"""
CONFIRM = """mutation($token: String!, $newPassword: String!) {
  confirmPasswordReset(token: $token, newPassword: $newPassword) { ok infoText statusCode } }"""
LOGIN = """mutation($email: String!, $password: String!) {
  login(email: $email, password: $password) { ok statusCode } }"""
CHECK_SESSION = "mutation { checkSession { ok } }"


class PasswordResetTestCase(unittest.TestCase):

    def setUp(self):
        db.remove()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app_module.ensure_root()
        db.add(User(first_name="Alice", last_name="A", email=ALICE,
                    password_hash=PasswordHasher().hash(OLD_PASSWORD)))
        db.commit()
        self.sent = []
        self.mail_ok = True
        self.add_job = mock.patch.object(send_mail_module.scheduler, "add_job").start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(db.remove)

    # helpers
    def enable_mail(self, mail=True, base_url=BASE_URL):
        mock.patch.object(password_reset, "mail_server_address", "smtp.example.test" if mail else None).start()
        mock.patch.object(password_reset, "public_base_url", base_url).start()

        def fake_send(receiver, subject, body, attempt=0, retry=True):
            self.sent.append({"receiver": receiver, "subject": subject, "body": body, "retry": retry})
            return self.mail_ok
        mock.patch.object(password_reset, "sendMail", side_effect=fake_send).start()

    def gql(self, client, query, variables=None):
        response = client.post("/graphql", json={"query": query, "variables": variables or {}})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response

    def login(self, password, client=None):
        client = client or app_module.app.test_client()
        data = self.gql(client, LOGIN, {"email": ALICE, "password": password}).get_json()
        return client, bool(data["data"]["login"]["ok"])

    def request_reset(self, email=ALICE):
        return self.gql(app_module.app.test_client(), REQUEST, {"email": email})

    def confirm(self, token, password=NEW_PASSWORD):
        return self.gql(app_module.app.test_client(), CONFIRM,
                        {"token": token, "newPassword": password}).get_json()["data"]["confirmPasswordReset"]

    def token_from_mail(self):
        self.assertEqual(len(self.sent), 1)
        body = self.sent[-1]["body"]
        marker = BASE_URL + "/reset-password?token="
        self.assertIn(marker, body)
        return body.split(marker, 1)[1].split('"', 1)[0].split("<", 1)[0]

    def alice(self):
        db.expire_all()
        return db.query(User).filter(User.email == ALICE).one()

    def tokens(self):
        db.expire_all()
        return db.query(PasswordResetToken).all()

    # A3.1 / A3.5
    def test_request_does_not_change_password(self):
        self.enable_mail()
        data = self.request_reset().get_json()["data"]["requestPasswordReset"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["infoText"], password_reset.REQUEST_INFO)
        self.assertTrue(self.login(OLD_PASSWORD)[1])

    def test_mail_disabled_creates_no_token_and_keeps_password(self):
        self.enable_mail(mail=False)
        data = self.request_reset().get_json()["data"]["requestPasswordReset"]
        self.assertEqual(data["infoText"], password_reset.REQUEST_INFO)
        self.assertEqual(self.tokens(), [])
        self.assertEqual(self.sent, [])
        self.assertTrue(self.login(OLD_PASSWORD)[1])

    def test_missing_public_base_url_creates_no_token(self):
        self.enable_mail(base_url="")
        self.request_reset()
        self.assertEqual(self.tokens(), [])
        self.assertEqual(self.sent, [])

    # A3.2
    def test_response_identical_for_known_and_unknown_email(self):
        self.enable_mail()
        known = self.request_reset(ALICE).get_data()
        unknown = self.request_reset("nobody@ovgu.de").get_data()
        self.assertEqual(known, unknown)
        self.assertEqual(len(self.sent), 1)

    def test_unexpected_error_keeps_generic_response(self):
        self.enable_mail()
        expected = self.request_reset("nobody@ovgu.de").get_data()
        with mock.patch.object(password_reset, "issue_link", side_effect=RuntimeError("boom")), \
                self.assertLogs("lending", "ERROR"):
            self.assertEqual(self.request_reset(ALICE).get_data(), expected)

    # A3.3 + R20.2
    def test_confirm_sets_new_password_once_and_ends_sessions(self):
        self.enable_mail()
        old_session, ok = self.login(OLD_PASSWORD)
        self.assertTrue(ok)
        self.request_reset()
        token = self.token_from_mail()

        data = self.confirm(token)
        self.assertTrue(data["ok"], data)
        self.assertTrue(self.login(NEW_PASSWORD)[1])
        self.assertFalse(self.login(OLD_PASSWORD)[1])
        self.assertFalse(self.gql(old_session, CHECK_SESSION).get_json()["data"]["checkSession"]["ok"])

        again = self.confirm(token, "another-password-1")
        self.assertEqual((again["ok"], again["statusCode"]), (False, 400))
        self.assertTrue(self.login(NEW_PASSWORD)[1])

    def test_expired_token_rejected(self):
        self.enable_mail()
        self.request_reset()
        token = self.token_from_mail()
        row = self.tokens()[0]
        row.expires_at = password_reset._utcnow() - timedelta(seconds=1)
        db.commit()
        data = self.confirm(token)
        self.assertEqual((data["ok"], data["statusCode"]), (False, 400))
        self.assertEqual(data["infoText"], password_reset.INVALID_LINK)
        self.assertTrue(self.login(OLD_PASSWORD)[1])

    def test_unknown_token_rejected(self):
        data = self.confirm("not-a-real-token")
        self.assertEqual((data["ok"], data["statusCode"]), (False, 400))

    def test_short_password_rejected_and_token_kept(self):
        self.enable_mail()
        self.request_reset()
        token = self.token_from_mail()
        data = self.confirm(token, "short")
        self.assertEqual((data["ok"], data["statusCode"]), (False, 400))
        self.assertTrue(self.confirm(token)["ok"])

    def test_new_request_replaces_unused_token(self):
        self.enable_mail()
        self.request_reset()
        self.request_reset()
        first = self.sent[0]["body"].split("token=", 1)[1].split('"', 1)[0]
        self.assertEqual(len(self.tokens()), 1)
        self.assertFalse(self.confirm(first)["ok"])

    # A3.4 / A16.3 / R16.2
    def test_no_plaintext_token_in_db_or_job_store(self):
        self.enable_mail()
        self.request_reset()
        token = self.token_from_mail()
        self.assertFalse(self.sent[0]["retry"])
        self.add_job.assert_not_called()

        row = self.tokens()[0]
        self.assertNotEqual(row.token_hash, token)
        self.assertEqual(len(row.token_hash), 64)
        with engine.connect() as conn:
            for table in inspect(conn).get_table_names():
                dump = repr(conn.execute(text(f'SELECT * FROM "{table}"')).fetchall())
                self.assertNotIn(token, dump, table)
                if table == "apscheduler_jobs":
                    for (state,) in conn.execute(text("SELECT job_state FROM apscheduler_jobs")):
                        self.assertNotIn(token, repr(pickle.loads(state)))

    def test_mail_failure_discards_token(self):
        self.enable_mail()
        self.mail_ok = False
        data = self.request_reset().get_json()["data"]["requestPasswordReset"]
        self.assertEqual(data["infoText"], password_reset.REQUEST_INFO)
        self.assertEqual(self.tokens(), [])

    # R3.5 migration
    def test_template_with_link_is_used(self):
        body = password_reset.render_mail(BASE_URL + "/reset-password?token=abc")
        self.assertIn('href="' + BASE_URL + '/reset-password?token=abc"', body)
        self.assertNotIn("$password", body)

    def test_old_password_template_falls_back_to_builtin_text(self):
        legacy = "<p>Hier Ihr neues Passwort: $password</p>"
        with mock.patch("builtins.open", mock.mock_open(read_data=legacy)), \
                self.assertLogs("lending", "WARNING"):
            body = password_reset.render_mail("https://x.test/reset-password?token=abc")
        self.assertIn("https://x.test/reset-password?token=abc", body)
        self.assertNotIn("$password", body)

    # R3.4 operator CLI
    def test_cli_reset_link_prints_working_link(self):
        mock.patch.object(manage, "public_base_url", BASE_URL).start()
        mock.patch.object(password_reset, "public_base_url", BASE_URL).start()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            manage.main(["reset-link", "ALICE@ovgu.de"])
        link = out.getvalue().strip()
        self.assertTrue(link.startswith(BASE_URL + "/reset-password?token="))
        self.assertTrue(self.confirm(link.split("token=", 1)[1])["ok"])
        self.assertTrue(self.login(NEW_PASSWORD)[1])

    def test_cli_reset_link_needs_public_base_url(self):
        mock.patch.object(manage, "public_base_url", "").start()
        with self.assertRaises(SystemExit):
            manage.main(["reset-link", ALICE])
        self.assertEqual(self.tokens(), [])

    def test_cli_set_password(self):
        old_session, _ = self.login(OLD_PASSWORD)
        with mock.patch("getpass.getpass", return_value=NEW_PASSWORD), redirect_stdout(io.StringIO()):
            manage.main(["set-password", ALICE])
        self.assertTrue(self.login(NEW_PASSWORD)[1])
        self.assertFalse(self.gql(old_session, CHECK_SESSION).get_json()["data"]["checkSession"]["ok"])

    def test_cli_set_password_rejects_short_password(self):
        with mock.patch("getpass.getpass", return_value="short"), self.assertRaises(SystemExit):
            manage.main(["set-password", ALICE])
        self.assertTrue(self.login(OLD_PASSWORD)[1])


class SendMailRetryTestCase(unittest.TestCase):
    """A16.1 / A16.2 / R16.3 with the SMTP client mocked."""

    def setUp(self):
        mock.patch.object(send_mail_module, "mail_server_address", "smtp.example.test").start()
        self.smtp = mock.patch.object(send_mail_module, "smtplib", wraps=smtplib).start()
        self.add_job = mock.patch.object(send_mail_module.scheduler, "add_job").start()
        self.addCleanup(mock.patch.stopall)

    def fail_with(self, error):
        server = mock.MagicMock()
        server.sendmail.side_effect = error
        self.smtp.SMTP.return_value = server
        self.smtp.SMTP_SSL.return_value = server

    def send(self, **kwargs):
        with self.assertLogs("lending", "WARNING"):
            return send_mail_module.sendMail("bob@ovgu.de", "Erinnerung", "<p>body</p>", **kwargs)

    def test_success_schedules_nothing(self):
        self.smtp.SMTP.return_value = mock.MagicMock()
        self.assertTrue(send_mail_module.sendMail("bob@ovgu.de", "Erinnerung", "<p>body</p>"))
        self.add_job.assert_not_called()

    def test_permanent_errors_are_dropped(self):
        for error in (smtplib.SMTPRecipientsRefused({"bob@ovgu.de": (550, b"no")}),
                      smtplib.SMTPAuthenticationError(535, b"auth"),
                      smtplib.SMTPDataError(554, b"rejected"),
                      ValueError("unexpected")):
            with self.subTest(error=type(error).__name__):
                self.fail_with(error)
                self.assertFalse(self.send())
        self.add_job.assert_not_called()

    def test_transient_error_retries_with_original_subject(self):
        for error in (smtplib.SMTPServerDisconnected("gone"), smtplib.SMTPDataError(451, b"later"),
                      socket.timeout(), ConnectionRefusedError()):
            with self.subTest(error=type(error).__name__):
                self.add_job.reset_mock()
                self.fail_with(error)
                self.send()
                self.add_job.assert_called_once()
                self.assertEqual(self.add_job.call_args.kwargs["args"],
                                 ("bob@ovgu.de", "Erinnerung", "<p>body</p>", 1, True))

    def test_at_most_three_retries(self):
        self.fail_with(smtplib.SMTPServerDisconnected("gone"))
        for attempt in range(len(send_mail_module.BACKOFF_MIN)):
            self.add_job.reset_mock()
            self.send(attempt=attempt)
            self.assertEqual(self.add_job.call_args.kwargs["args"][3], attempt + 1)
        self.add_job.reset_mock()
        self.send(attempt=len(send_mail_module.BACKOFF_MIN))
        self.add_job.assert_not_called()
        self.assertEqual(len(send_mail_module.BACKOFF_MIN), 3)

    def test_retry_false_never_schedules(self):
        self.fail_with(smtplib.SMTPServerDisconnected("gone"))
        self.assertFalse(self.send(retry=False))
        self.add_job.assert_not_called()

    def test_old_three_argument_jobs_still_run(self):
        self.smtp.SMTP.return_value = mock.MagicMock()
        self.assertTrue(send_mail_module.sendMail("bob@ovgu.de", "Erinnerung RETRY", "<p>body</p>"))


if __name__ == "__main__":
    unittest.main()

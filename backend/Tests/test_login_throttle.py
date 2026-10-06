"""
Per-account login backoff.

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
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

import app as app_module  # noqa: E402
import login_throttle  # noqa: E402
import manage  # noqa: E402
import password_reset  # noqa: E402
from config import db, engine  # noqa: E402
from models import Base, LoginThrottle, User  # noqa: E402

ALICE = "alice@ovgu.de"
PASSWORD = "alice-password-1"
NEW_PASSWORD = "alice-new-password"
UNKNOWN = "nobody@ovgu.de"
LOGIN = """mutation($email: String!, $password: String!) {
  login(email: $email, password: $password) { ok statusCode infoText } }"""


class LoginThrottleTestCase(unittest.TestCase):

    def setUp(self):
        db.remove()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app_module.ensure_root()
        db.add(User(first_name="Alice", last_name="A", email=ALICE,
                    password_hash=PasswordHasher().hash(PASSWORD)))
        db.commit()
        self.now = datetime(2030, 1, 1, 12, 0, 0)
        mock.patch.object(login_throttle, "_utcnow", self.utcnow).start()
        mock.patch.object(login_throttle, "login_max_failures", 5).start()
        mock.patch.object(login_throttle, "login_lockout_minutes", 15).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(db.remove)

    def utcnow(self):
        return self.now

    def login(self, email=ALICE, password=PASSWORD):
        response = app_module.app.test_client().post(
            "/graphql", json={"query": LOGIN, "variables": {"email": email, "password": password}})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["data"]["login"]

    def fail(self, times, email=ALICE):
        for _ in range(times):
            self.assertFalse(self.login(email, "wrong-password")["ok"])

    def test_four_failures_do_not_lock(self):
        self.fail(4)
        self.assertTrue(self.login()["ok"])

    def test_five_failures_lock_even_correct_password(self):
        wrong = self.login(password="wrong-password")
        self.fail(4)
        locked = self.login()
        self.assertEqual(locked, wrong)
        self.assertFalse(locked["ok"])

    def test_locked_login_does_not_check_password(self):
        self.fail(5)
        import mutation_login
        hasher = mock.Mock(wraps=mutation_login._ph)
        with mock.patch.object(mutation_login, "_ph", hasher):
            self.assertFalse(self.login()["ok"])
        # only the dummy hash is verified (same cost as a normal attempt)
        self.assertTrue(hasher.verify.called)
        for call in hasher.verify.call_args_list:
            self.assertEqual(call.args[0], mutation_login._DUMMY_HASH)

    def test_key_is_normalized_email(self):
        self.fail(5, "  ALICE@OVGU.DE ")
        self.assertFalse(self.login()["ok"])

    def test_unknown_email_same_behaviour(self):
        known = [self.login(ALICE, "wrong-password") for _ in range(6)]
        unknown = [self.login(UNKNOWN, "wrong-password") for _ in range(6)]
        self.assertEqual(known, unknown)
        self.assertEqual(db.query(LoginThrottle).count(), 2)

    def test_lock_does_not_affect_other_accounts(self):
        self.fail(5, UNKNOWN)
        self.assertTrue(self.login()["ok"])

    def test_lock_ends_after_lockout(self):
        self.fail(5)
        self.now += timedelta(minutes=14)
        self.assertFalse(self.login()["ok"])
        self.now += timedelta(minutes=1, seconds=1)
        self.assertTrue(self.login()["ok"])

    def test_failures_outside_window_are_forgotten(self):
        self.fail(4)
        self.now += timedelta(minutes=15, seconds=1)
        self.fail(4)
        self.assertTrue(self.login()["ok"])

    def test_attempts_while_locked_do_not_extend_lock(self):
        self.fail(5)
        self.now += timedelta(minutes=10)
        self.fail(3)
        self.now += timedelta(minutes=5, seconds=1)
        self.assertTrue(self.login()["ok"])

    def test_success_resets_counter(self):
        self.fail(4)
        self.assertTrue(self.login()["ok"])
        self.fail(4)
        self.assertTrue(self.login()["ok"])

    def test_cli_set_password_unlocks(self):
        self.fail(5)
        with mock.patch("getpass.getpass", return_value=NEW_PASSWORD), redirect_stdout(io.StringIO()):
            manage.main(["set-password", ALICE])
        self.assertTrue(self.login(password=NEW_PASSWORD)["ok"])

    def test_password_reset_unlocks(self):
        self.fail(5)
        user = password_reset.find_user(ALICE)
        mock.patch.object(password_reset, "public_base_url", "https://lending.example.test").start()
        token = password_reset.issue_link(user).split("token=", 1)[1]
        password_reset.confirm_reset(token, NEW_PASSWORD)
        self.assertTrue(self.login(password=NEW_PASSWORD)["ok"])

    def test_settings_are_used(self):
        mock.patch.object(login_throttle, "login_max_failures", 2).start()
        mock.patch.object(login_throttle, "login_lockout_minutes", 1).start()
        self.fail(2)
        self.assertFalse(self.login()["ok"])
        self.now += timedelta(minutes=1, seconds=1)
        self.assertTrue(self.login()["ok"])

    def test_stale_rows_are_removed(self):
        self.fail(1, UNKNOWN)
        self.now += timedelta(hours=1)
        self.fail(1)
        db.expire_all()
        self.assertEqual(db.query(LoginThrottle).count(), 1)

    def test_no_plain_email_stored(self):
        self.fail(1)
        db.expire_all()
        row = db.query(LoginThrottle).one()
        self.assertNotIn("alice", row.key_hash)


if __name__ == "__main__":
    unittest.main()

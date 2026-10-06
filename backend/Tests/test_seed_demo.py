"""
Demo seed (manage.py seed-demo): idempotent, guarded, logins per role, public lent-out state.

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
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

import app as app_module  # noqa: E402
import manage  # noqa: E402
import seed_demo  # noqa: E402
from config import db, engine  # noqa: E402
from models import (Base, File, Group, Order, Organization, Organization_User, PhysicalObject,  # noqa: E402
                    Tag, User)

COUNTED = (Organization, User, Organization_User, Tag, PhysicalObject, Group, Order, File)

LOGIN = """mutation($email: String!, $password: String!) {
  login(email: $email, password: $password) { ok statusCode } }"""
AVAILABILITY = """query($physIds: [String]!) {
  objectAvailability(physIds: $physIds) { physId fromDate tillDate pending } }"""


class SeedDemoTestCase(unittest.TestCase):

    def setUp(self):
        db.remove()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app_module.ensure_root()
        self.addCleanup(db.remove)

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            manage.main(["seed-demo", *args])
        return out.getvalue()

    def counts(self):
        db.expire_all()
        return {model.__name__: db.query(model).count() for model in COUNTED}

    def item(self, name):
        return db.query(PhysicalObject).filter_by(name=name).one()

    def test_runs_twice_without_duplicates(self):
        first = self.run_cli()
        self.assertIn(seed_demo.DEMO_PASSWORD, first)
        after_first = self.counts()
        second = self.run_cli()
        self.assertIn("nothing new", second)
        self.assertEqual(self.counts(), after_first)
        self.assertEqual(after_first["Order"], len(seed_demo.ORDERS))
        self.assertEqual(after_first["PhysicalObject"], len(seed_demo.ITEMS))
        self.assertEqual(after_first["User"], len(seed_demo.USERS) + 1)  # + bootstrap root

    def test_refuses_without_testing_on_or_force_dev(self):
        with mock.patch.object(manage, "testing_on", 0), self.assertRaises(SystemExit):
            self.run_cli()
        self.assertEqual(db.query(PhysicalObject).count(), 0)
        with mock.patch.object(manage, "testing_on", 0):
            self.run_cli("--force-dev")
        self.assertEqual(db.query(PhysicalObject).count(), len(seed_demo.ITEMS))

    def test_refuses_database_with_other_users(self):
        db.add(User(first_name="Real", last_name="User", email="real.user@ovgu.de",
                    password_hash="x"))
        db.commit()
        with mock.patch.object(manage, "testing_on", 0), self.assertRaises(SystemExit):
            self.run_cli("--force-dev")
        with self.assertRaises(SystemExit):
            self.run_cli()
        self.assertEqual(db.query(PhysicalObject).count(), 0)
        self.assertEqual(db.query(User).count(), 2)  # root + the existing user

    def test_every_role_is_covered_and_can_log_in(self):
        self.run_cli()
        rights = {m.rights.name for m in db.query(Organization_User).all()}
        self.assertEqual(rights, {"system_admin", "organization_admin", "inventory_admin",
                                  "member", "customer", "watcher"})
        for email in seed_demo.USERS:
            with self.subTest(email=email):
                client = app_module.app.test_client()
                data = client.post("/graphql", json={"query": LOGIN, "variables": {
                    "email": email, "password": seed_demo.DEMO_PASSWORD}}).get_json()
                self.assertTrue(data["data"]["login"]["ok"], data)

    def test_existing_password_is_not_overwritten(self):
        self.run_cli()
        user = db.query(User).filter_by(email="harry.potter@ovgu.de").one()
        user.password_hash = "kept"
        db.commit()
        self.run_cli()
        db.expire_all()
        self.assertEqual(db.query(User).filter_by(email="harry.potter@ovgu.de").one().password_hash, "kept")

    def test_anonymous_availability_shows_current_loan_without_person_data(self):
        self.run_cli()
        lent, free = self.item("Firebolt"), self.item("Pensieve")
        response = app_module.app.test_client().post("/graphql", json={
            "query": AVAILABILITY, "variables": {"physIds": [lent.phys_id, free.phys_id]}})
        body = response.get_data(as_text=True)
        ranges = response.get_json()["data"]["objectAvailability"]
        now = datetime.now()
        current = [r for r in ranges if r["physId"] == lent.phys_id and not r["pending"]
                   and datetime.fromisoformat(r["fromDate"]) <= now <= datetime.fromisoformat(r["tillDate"])]
        self.assertEqual(len(current), 1, ranges)
        self.assertFalse([r for r in ranges if r["physId"] == free.phys_id])
        for email in seed_demo.USERS:
            self.assertNotIn(email, body)
        for first, last, _ in seed_demo.USERS.values():
            self.assertNotIn(last, body)

    def test_returned_and_rejected_orders_are_not_busy(self):
        self.run_cli()
        ids = [self.item("Invisibility Cloak").phys_id, self.item("Remembrall").phys_id]
        data = app_module.app.test_client().post("/graphql", json={
            "query": AVAILABILITY, "variables": {"physIds": ids}}).get_json()
        self.assertEqual(data["data"]["objectAvailability"], [])

    def test_agb_pdf_written_for_each_organisation(self):
        self.run_cli()
        for name in seed_demo.ORGANIZATIONS:
            org = db.query(Organization).filter_by(name=name).one()
            self.assertEqual(len(org.agb), 1)
            path = os.path.join(seed_demo.pdf_directory, org.agb[0].path)
            with open(path, "rb") as f:
                self.assertTrue(f.read().startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()

"""
Shared fixture for authorization tests: an in-memory app with seeded principals.

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import datetime
import json
import os
import sys
import unittest

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
from config import db, engine  # noqa: E402
from models import (Base, userRights, orderStatus, User, Organization, Organization_User,  # noqa: E402
                    PhysicalObject, Group, Tag, File, Order)

PASSWORD = "password-1234"
ROOT_EMAIL = os.environ["root_user_name"]
ROOT_PASSWORD = os.environ["root_user_password"]

EMAILS = {
    "oa_b": "oa.b@ovgu.de",
    "ia_a": "ia.a@ovgu.de",
    "m_a": "m.a@ovgu.de",
    "bob": "bob.a@ovgu.de",
    "carol": "carol.a@ovgu.de",
    "u": "u.none@ovgu.de",
}

LOGIN = """mutation($email: String!, $password: String!) {
  login(email: $email, password: $password) { ok statusCode infoText } }"""

FORBIDDEN_MARKERS = ("Traceback", 'File "', "SELECT", "INSERT", "$argon2", "IntegrityError")

_HASH = PasswordHasher().hash(PASSWORD)


class SecurityTestCase(unittest.TestCase):
    """Seeds: org A and B, root (SA), OA_B, IA_A, M_A, bob/carol (customers of A), U (no
    membership), obj50 (deposit 50, org A), an empty tag, an empty and a non-empty group of A,
    a picture attached to obj50 and bob's pending order. maxDeposit(A, customer) = 30."""

    app = app_module.app

    def setUp(self):
        db.remove()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app_module.ensure_root()

        self.root = User.query.filter(User.email == ROOT_EMAIL).one()
        self.org_a = Organization(name="Org A", location="A")
        self.org_b = Organization(name="Org B", location="B")
        db.add_all([self.org_a, self.org_b])
        self.users = {}
        for key, email in EMAILS.items():
            user = User(first_name=key, last_name="Test", email=email, password_hash=_HASH,
                        city="Magdeburg", phone_number=1000 + len(self.users))
            db.add(user)
            self.users[key] = user
        db.flush()

        for org, key, right in ((self.org_b, "oa_b", userRights.organization_admin),
                                (self.org_a, "ia_a", userRights.inventory_admin),
                                (self.org_a, "m_a", userRights.member),
                                (self.org_a, "bob", userRights.customer),
                                (self.org_a, "carol", userRights.customer)):
            db.add(Organization_User(organization_id=org.organization_id,
                                     user_id=self.users[key].user_id, rights=right))
        # createOrganization adds root as system_admin to every organisation
        for org in (self.org_a, self.org_b):
            db.add(Organization_User(organization_id=org.organization_id,
                                     user_id=self.root.user_id, rights=userRights.system_admin))
        self.org_a.max_deposit = json.dumps({"customer": 30, "member": 40, "inventory_admin": 100,
                                             "organization_admin": 100, "system_admin": 100})

        self.obj50 = PhysicalObject(inv_num_internal=1, inv_num_external=1, deposit=50,
                                    storage_location="S", name="Obj50", borrowable=True,
                                    organization_id=self.org_a.organization_id)
        self.obj_a2 = PhysicalObject(inv_num_internal=2, inv_num_external=2, deposit=10,
                                     storage_location="S", name="ObjA2", borrowable=True,
                                     organization_id=self.org_a.organization_id)
        self.obj_b = PhysicalObject(inv_num_internal=3, inv_num_external=3, deposit=5,
                                    storage_location="S", name="ObjB", borrowable=True,
                                    organization_id=self.org_b.organization_id)
        db.add_all([self.obj50, self.obj_a2, self.obj_b])
        db.flush()

        self.empty_tag = Tag(name="empty-tag")
        self.empty_group = Group(name="Empty group", organization_id=self.org_a.organization_id)
        self.group_a = Group(name="Group A", organization_id=self.org_a.organization_id,
                             physicalobjects=[self.obj50])
        self.file_a = File(path="a_picture.png", file_type="picture", picture_id=self.obj50.phys_id)
        self.file_free = File(path="free_picture.png", file_type="picture")
        db.add_all([self.empty_tag, self.empty_group, self.group_a, self.file_a, self.file_free])

        self.order = Order(creation_date=datetime.datetime(2030, 1, 1),
                           from_date=datetime.datetime(2030, 2, 1, 10),
                           till_date=datetime.datetime(2030, 2, 5, 10),
                           deposit=30, organization_id=self.org_a.organization_id,
                           users=[self.users["bob"]])
        self.order.addPhysicalObject(self.obj50)
        db.add(self.order)
        db.commit()

        self.ids = {
            "org_a": self.org_a.organization_id, "org_b": self.org_b.organization_id,
            "obj50": self.obj50.phys_id, "obj_a2": self.obj_a2.phys_id, "obj_b": self.obj_b.phys_id,
            "empty_tag": self.empty_tag.tag_id, "empty_group": self.empty_group.group_id,
            "group_a": self.group_a.group_id, "file_a": self.file_a.file_id,
            "file_free": self.file_free.file_id, "order": self.order.order_id,
            "root": self.root.user_id,
        }
        for key, user in self.users.items():
            self.ids[key] = user.user_id
        db.remove()

    def tearDown(self):
        db.remove()

    # helpers
    def client_for(self, who=None):
        """Test client; logged in through the real login mutation when who is given."""
        client = self.app.test_client()
        if who is not None:
            email, password = (ROOT_EMAIL, ROOT_PASSWORD) if who == "root" else (EMAILS[who], PASSWORD)
            resp = self.gql(client, LOGIN, {"email": email, "password": password})
            assert resp["data"]["login"]["ok"], resp
        return client

    def gql(self, client, query, variables=None):
        resp = client.post("/graphql", json={"query": query, "variables": variables or {}})
        self.last_text = resp.get_data(as_text=True)
        return resp.get_json()

    def assert_rejected(self, resp, field, status):
        payload = resp["data"][field]
        self.assertFalse(payload["ok"], resp)
        self.assertEqual(payload["statusCode"], status, resp)

    def assert_ok(self, resp, field):
        payload = resp["data"][field]
        self.assertTrue(payload["ok"], resp)
        self.assertEqual(payload["statusCode"], 200, resp)

    def assert_no_leak(self, text=None):
        text = self.last_text if text is None else text
        for email in list(EMAILS.values()) + [ROOT_EMAIL]:
            self.assertNotIn(email, text)
        for marker in FORBIDDEN_MARKERS:
            self.assertNotIn(marker, text)

    def assert_query_rejected(self, resp, field):
        self.assertIsNone((resp.get("data") or {}).get(field), resp)
        self.assertTrue(resp.get("errors"), resp)

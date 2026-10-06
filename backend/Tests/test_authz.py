"""
Authorization regression tests: one test per acceptance criterion (A1, A2, A4, A10, A11, A14, A15, A20).

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import json
import os
import re
import unittest
from unittest import mock

from security_fixture import SecurityTestCase, EMAILS, PASSWORD, ROOT_EMAIL, _BACKEND

from config import db
from models import (userRights, orderStatus, User, Organization, Organization_User, PhysicalObject,
                    PhysicalObject_Order, Group, Tag, File, Order)

UPDATE_RIGHTS = """mutation($org: String!, $user: String!, $r: String!) {
  updateUserRights(organizationId: $org, userId: $user, newRights: $r) { ok statusCode infoText } }"""
ADD_USER = """mutation($org: String!, $user: String!, $r: String) {
  addUserToOrganization(organizationId: $org, userId: $user, userRight: $r) { ok statusCode infoText } }"""
REMOVE_USER = """mutation($org: String!, $user: String!) {
  removeUserFromOrganization(organizationId: $org, userId: $user) { ok statusCode infoText } }"""
DELETE_ORG = """mutation($org: String!) {
  deleteOrganization(organizationId: $org) { ok statusCode infoText } }"""
CREATE_ORG = """mutation($name: String!) {
  createOrganization(name: $name, location: "L") { ok statusCode infoText organization { organizationId } } }"""
ORDER_STATUS = """mutation($order: String!, $objs: [String]!, $s: String) {
  updateOrderStatus(orderId: $order, physicalObjects: $objs, status: $s) { ok statusCode infoText } }"""
DELETE_ORDER = """mutation($order: String!) { deleteOrder(orderId: $order) { ok statusCode infoText } }"""
UPDATE_ORDER = """mutation($order: String!, $deposit: Int, $from: Date, $till: Date) {
  updateOrder(orderId: $order, deposit: $deposit, fromDate: $from, tillDate: $till) { ok statusCode infoText } }"""
CREATE_ORDER = """mutation($objs: [String]!, $deposit: Int) {
  createOrder(fromDate: "2031-03-01T10:00:00", tillDate: "2031-03-03T10:00:00", physicalobjects: $objs,
              deposit: $deposit) { ok statusCode infoText } }"""
CREATE_USER = """mutation($email: String!, $phone: Int) {
  createUser(email: $email, firstName: "New", lastName: "User", password: "long-password-1",
             phoneNumber: $phone) { ok statusCode infoText } }"""
UPDATE_USER = """mutation($id: String!, $email: String, $pw: String, $current: String) {
  updateUser(userId: $id, email: $email, password: $pw, currentPassword: $current) { ok statusCode infoText } }"""
UPDATE_GROUP = """mutation($id: String!) { updateGroup(groupId: $id, description: "x") { ok statusCode infoText } }"""
DELETE_GROUP = """mutation($id: String!) { deleteGroup(groupId: $id) { ok statusCode infoText } }"""
UPDATE_TAG = """mutation($id: String!) { updateTag(tagId: $id, name: "renamed") { ok statusCode infoText } }"""
DELETE_TAG = """mutation($id: String!) { deleteTag(tagId: $id) { ok statusCode infoText } }"""
CHECK_SESSION = "mutation { checkSession { ok statusCode userId } }"


class A1QueryAccess(SecurityTestCase):

    def test_a1_1_anonymous_filter_users_rejected(self):
        resp = self.gql(self.client_for(), "{ filterUsers { email } }")
        self.assert_query_rejected(resp, "filterUsers")
        self.assertEqual(resp["errors"][0]["message"], "Nicht angemeldet")
        self.assert_no_leak()

    def test_a1_2_anonymous_order_queries_rejected(self):
        client = self.client_for()
        for query, field in (("{ filterOrders { orderId } }", "filterOrders"),
                             ("{ filterPhysicalObjectOrder { orderId } }", "filterPhysicalObjectOrder")):
            resp = self.gql(client, query)
            self.assert_query_rejected(resp, field)
            self.assertNotIn(self.ids["order"], self.last_text)
            self.assert_no_leak()

    def test_a1_3_anonymous_nested_edges_leak_nothing(self):
        client = self.client_for()
        queries = [
            "{ filterPhysicalObjects { orders { edges { node { orderId order { users { edges { node { email } } } } } } } } }",
            "{ filterOrganizations { users { edges { node { user { email } } } } } }",
            "{ filterGroups { physicalobjects { edges { node { orders { edges { node { order { orderId } } } } } } } } }",
            "{ filterTags { physicalobjects { edges { node { orders { edges { node { orderId } } } } } } } }",
            '{ node(id: "VXNlcjox") { ... on User { email } } }',
        ]
        for query in queries:
            self.gql(client, query)
            self.assert_no_leak()
            self.assertNotIn(self.ids["order"], self.last_text)
        resp = self.gql(client, queries[0])
        obj = [o for o in resp["data"]["filterPhysicalObjects"] if o["orders"]["edges"]]
        self.assertEqual(obj, [])

    def test_a1_4_customer_sees_only_own_user(self):
        client = self.client_for("carol")
        resp = self.gql(client, "{ filterUsers { userId } }")
        self.assertEqual([u["userId"] for u in resp["data"]["filterUsers"]], [self.ids["carol"]])
        resp = self.gql(client, "query($e: String) { filterUsers(email: $e) { userId } }", {"e": EMAILS["bob"]})
        self.assertEqual(resp["data"]["filterUsers"], [])
        resp = self.gql(client, "query($o: [String]) { filterUsers(organizations: $o) { userId email } }",
                        {"o": [self.ids["org_a"]]})
        self.assertEqual([u["userId"] for u in resp["data"]["filterUsers"]], [self.ids["carol"]])

    def test_a1_5_order_scoping(self):
        query = "{ filterOrders { orderId } }"
        self.assertEqual(self.gql(self.client_for("carol"), query)["data"]["filterOrders"], [])
        self.assertEqual(self.gql(self.client_for("bob"), query)["data"]["filterOrders"],
                         [{"orderId": self.ids["order"]}])
        self.assertEqual(self.gql(self.client_for("ia_a"), query)["data"]["filterOrders"],
                         [{"orderId": self.ids["order"]}])
        self.assertEqual(self.gql(self.client_for("oa_b"), query)["data"]["filterOrders"], [])
        self.assertEqual(self.gql(self.client_for("root"), query)["data"]["filterOrders"],
                         [{"orderId": self.ids["order"]}])
        pos = "{ filterPhysicalObjectOrder { orderId } }"
        self.assertEqual(self.gql(self.client_for("carol"), pos)["data"]["filterPhysicalObjectOrder"], [])
        self.assertEqual(len(self.gql(self.client_for("ia_a"), pos)["data"]["filterPhysicalObjectOrder"]), 1)

    def test_a1_6_public_catalogue_still_works(self):
        client = self.client_for()
        resp = self.gql(client, """{
          filterPhysicalObjects { physId name deposit faults pictures { edges { node { path } } }
                                  tags { edges { node { name } } } organization { organizationId name } }
          filterGroups { groupId name }
          filterTags { tagId name }
          filterOrganizations { organizationId name location agb { edges { node { path } } } }
          getImprint getPrivacyPolicy getContactInformation }""")
        self.assertNotIn("errors", resp, resp)
        data = resp["data"]
        self.assertEqual(len(data["filterPhysicalObjects"]), 3)
        self.assertEqual(len(data["filterGroups"]), 2)
        self.assertEqual(len(data["filterTags"]), 1)
        self.assertEqual(len(data["filterOrganizations"]), 3)
        self.assertTrue(data["getImprint"])

    def test_a1_6_public_availability_has_dates_only(self):
        resp = self.gql(self.client_for(), """query($ids: [String]!) {
          objectAvailability(physIds: $ids) { physId fromDate tillDate pending } }""",
                        {"ids": [self.ids["obj50"], self.ids["obj_a2"]]})
        self.assertEqual(resp["data"]["objectAvailability"],
                         [{"physId": self.ids["obj50"], "fromDate": "2030-02-01T10:00:00",
                           "tillDate": "2030-02-05T10:00:00", "pending": True}])
        self.assert_no_leak()
        resp = self.gql(self.client_for(), """query($ids: [String]!) {
          objectAvailability(physIds: $ids) { physId } }""", {"ids": ["x"] * 201})
        self.assert_query_rejected(resp, "objectAvailability")

    def test_a1_5_field_level_user_data(self):
        # staff of the order org sees name and email of the borrower, not the address
        resp = self.gql(self.client_for("ia_a"),
                        "{ filterOrders { users { edges { node { email city phoneNumber } } } } }")
        self.assertEqual(resp["data"]["filterOrders"][0]["users"]["edges"],
                         [{"node": {"email": EMAILS["bob"], "city": None, "phoneNumber": None}}])
        # a customer sees no members or deposit limits of the organisation
        resp = self.gql(self.client_for("bob"),
                        "{ filterOrganizations { maxDeposit users { edges { node { userId } } } } }")
        for org in resp["data"]["filterOrganizations"]:
            self.assertIsNone(org["maxDeposit"])
            self.assertEqual(org["users"]["edges"], [])


class A2GrantBounds(SecurityTestCase):

    def _right(self, org_key, user_key):
        row = db.query(Organization_User).get((self.ids[org_key], self.ids[user_key]))
        db.remove()
        return row.rights if row else None

    def test_a2_1_oa_cannot_grant_self_system_admin(self):
        resp = self.gql(self.client_for("oa_b"), UPDATE_RIGHTS,
                        {"org": self.ids["org_b"], "user": self.ids["oa_b"], "r": "system_admin"})
        self.assert_rejected(resp, "updateUserRights", 403)
        self.assertEqual(self._right("org_b", "oa_b"), userRights.organization_admin)

    def test_a2_2_non_member_oa_cannot_grant_in_other_org(self):
        resp = self.gql(self.client_for("oa_b"), UPDATE_RIGHTS,
                        {"org": self.ids["org_a"], "user": self.ids["oa_b"], "r": "system_admin"})
        self.assert_rejected(resp, "updateUserRights", 403)
        self.assertIsNone(self._right("org_a", "oa_b"))

    def test_a2_3_oa_cannot_add_system_admin(self):
        resp = self.gql(self.client_for("oa_b"), ADD_USER,
                        {"org": self.ids["org_b"], "user": self.ids["u"], "r": "system_admin"})
        self.assert_rejected(resp, "addUserToOrganization", 403)
        self.assertIsNone(self._right("org_b", "u"))

    def test_a2_4_oa_cannot_demote_root(self):
        resp = self.gql(self.client_for("oa_b"), UPDATE_RIGHTS,
                        {"org": self.ids["org_b"], "user": self.ids["root"], "r": "customer"})
        self.assert_rejected(resp, "updateUserRights", 403)
        self.assertEqual(self._right("org_b", "root"), userRights.system_admin)
        resp = self.gql(self.client_for("oa_b"), REMOVE_USER, {"org": self.ids["org_b"], "user": self.ids["root"]})
        self.assert_rejected(resp, "removeUserFromOrganization", 403)

    def test_a2_5_invalid_right_is_400(self):
        resp = self.gql(self.client_for("oa_b"), UPDATE_RIGHTS,
                        {"org": self.ids["org_b"], "user": self.ids["u"], "r": "foo"})
        self.assert_rejected(resp, "updateUserRights", 400)
        self.assert_no_leak()
        resp = self.gql(self.client_for("oa_b"), ADD_USER,
                        {"org": self.ids["org_b"], "user": self.ids["u"], "r": "foo"})
        self.assert_rejected(resp, "addUserToOrganization", 400)
        self.assertIsNone(self._right("org_b", "u"))

    def test_a2_6_no_global_admin_after_attempt(self):
        client = self.client_for("oa_b")
        self.gql(client, UPDATE_RIGHTS, {"org": self.ids["org_b"], "user": self.ids["oa_b"], "r": "system_admin"})
        resp = self.gql(client, DELETE_ORG, {"org": self.ids["org_a"]})
        self.assert_rejected(resp, "deleteOrganization", 403)
        self.assertIsNotNone(db.query(Organization).get(self.ids["org_a"]))
        # an organisation-level system_admin row elsewhere gives no global power
        db.query(Organization_User).get((self.ids["org_b"], self.ids["oa_b"])).rights = userRights.system_admin
        db.commit()
        resp = self.gql(self.client_for("oa_b"), DELETE_ORG, {"org": self.ids["org_a"]})
        self.assert_rejected(resp, "deleteOrganization", 403)

    def test_a2_7_sa_and_oa_flows_still_work(self):
        root = self.client_for("root")
        resp = self.gql(root, CREATE_ORG, {"name": "Org C"})
        self.assert_ok(resp, "createOrganization")
        org_c = resp["data"]["createOrganization"]["organization"]["organizationId"]
        resp = self.gql(root, UPDATE_RIGHTS, {"org": org_c, "user": self.ids["u"], "r": "organization_admin"})
        self.assert_ok(resp, "updateUserRights")
        self.assertEqual(db.query(Organization_User).get((org_c, self.ids["u"])).rights,
                         userRights.organization_admin)
        db.remove()
        # D11: an OA may grant OA to a new member, but may not change another OA afterwards
        oa = self.client_for("oa_b")
        self.assert_ok(self.gql(oa, UPDATE_RIGHTS, {"org": self.ids["org_b"], "user": self.ids["u"],
                                                    "r": "organization_admin"}), "updateUserRights")
        self.assert_rejected(self.gql(oa, UPDATE_RIGHTS, {"org": self.ids["org_b"], "user": self.ids["u"],
                                                          "r": "customer"}), "updateUserRights", 403)
        # SA may not grant system_admin through the API either
        self.assert_rejected(self.gql(root, UPDATE_RIGHTS, {"org": self.ids["org_b"], "user": self.ids["u"],
                                                            "r": "system_admin"}), "updateUserRights", 403)
        # a non-OA cannot manage members at all
        self.assert_rejected(self.gql(self.client_for("ia_a"), ADD_USER,
                                      {"org": self.ids["org_a"], "user": self.ids["u"], "r": "customer"}),
                             "addUserToOrganization", 403)


class A4Orders(SecurityTestCase):

    def _status(self):
        row = db.query(PhysicalObject_Order).get((self.ids["obj50"], self.ids["order"]))
        db.remove()
        return row.order_status

    def test_a4_1_foreign_customer_cannot_change_status(self):
        resp = self.gql(self.client_for("carol"), ORDER_STATUS,
                        {"order": self.ids["order"], "objs": [self.ids["obj50"]], "s": "accepted"})
        self.assert_rejected(resp, "updateOrderStatus", 403)
        self.assertEqual(self._status(), orderStatus.pending)

    def test_a4_2_foreign_customer_cannot_delete(self):
        resp = self.gql(self.client_for("carol"), DELETE_ORDER, {"order": self.ids["order"]})
        self.assert_rejected(resp, "deleteOrder", 403)
        self.assertIsNotNone(db.query(Order).get(self.ids["order"]))

    def test_a4_3_foreign_customer_cannot_set_deposit(self):
        resp = self.gql(self.client_for("carol"), UPDATE_ORDER, {"order": self.ids["order"], "deposit": 1})
        self.assert_rejected(resp, "updateOrder", 403)
        self.assertEqual(db.query(Order).get(self.ids["order"]).deposit, 30)
        # the borrower may not set the deposit either
        resp = self.gql(self.client_for("bob"), UPDATE_ORDER, {"order": self.ids["order"], "deposit": 1})
        self.assert_rejected(resp, "updateOrder", 403)

    def test_a4_4_client_deposit_ignored(self):
        resp = self.gql(self.client_for("bob"), CREATE_ORDER, {"objs": [self.ids["obj50"]], "deposit": 1})
        self.assert_ok(resp, "createOrder")
        orders = db.query(Order).filter(Order.order_id != self.ids["order"]).all()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].deposit, 30)  # min(50, maxDeposit(customer)=30)

    def test_a4_4_auto_join_as_customer(self):
        resp = self.gql(self.client_for("u"), CREATE_ORDER, {"objs": [self.ids["obj_a2"]], "deposit": 1})
        self.assert_ok(resp, "createOrder")
        self.assertEqual(db.query(Organization_User).get((self.ids["org_a"], self.ids["u"])).rights,
                         userRights.customer)
        order = db.query(Order).filter(Order.order_id != self.ids["order"]).one()
        self.assertEqual(order.deposit, 10)

    def test_a4_4_watcher_cannot_create_order(self):
        db.add(Organization_User(organization_id=self.ids["org_a"], user_id=self.ids["u"],
                                 rights=userRights.watcher))
        db.commit()
        resp = self.gql(self.client_for("u"), CREATE_ORDER, {"objs": [self.ids["obj_a2"]]})
        self.assert_rejected(resp, "createOrder", 403)
        self.assertEqual(db.query(Order).filter(Order.order_id != self.ids["order"]).count(), 0)
        self.assertEqual(db.query(Organization_User).get((self.ids["org_a"], self.ids["u"])).rights,
                         userRights.watcher)

    def test_a4_5_borrower_cannot_accept_own_order(self):
        resp = self.gql(self.client_for("bob"), ORDER_STATUS,
                        {"order": self.ids["order"], "objs": [self.ids["obj50"]], "s": "accepted"})
        self.assert_rejected(resp, "updateOrderStatus", 403)
        self.assertEqual(self._status(), orderStatus.pending)

    def test_a4_6_staff_accepts_order(self):
        client = self.client_for("ia_a")
        resp = self.gql(client, ORDER_STATUS,
                        {"order": self.ids["order"], "objs": [self.ids["obj50"]], "s": "accepted"})
        self.assert_ok(resp, "updateOrderStatus")
        self.assertEqual(self._status(), orderStatus.accepted)
        resp = self.gql(client, ORDER_STATUS,
                        {"order": self.ids["order"], "objs": [self.ids["obj50"]], "s": "bogus"})
        self.assert_rejected(resp, "updateOrderStatus", 400)

    def test_a4_7_borrower_edits_only_while_pending(self):
        bob = self.client_for("bob")
        resp = self.gql(bob, UPDATE_ORDER, {"order": self.ids["order"], "from": "2030-02-02", "till": "2030-02-06"})
        self.assert_ok(resp, "updateOrder")
        self.assertEqual(db.query(Order).get(self.ids["order"]).from_date.day, 2)
        db.remove()
        self.gql(self.client_for("ia_a"), ORDER_STATUS,
                 {"order": self.ids["order"], "objs": [self.ids["obj50"]], "s": "accepted"})
        resp = self.gql(bob, UPDATE_ORDER, {"order": self.ids["order"], "from": "2030-02-03"})
        self.assert_rejected(resp, "updateOrder", 403)
        self.assertEqual(db.query(Order).get(self.ids["order"]).from_date.day, 2)

    def test_a4_recompute_deposit_uses_borrower_right(self):
        resp = self.gql(self.client_for("ia_a"), """mutation($o: String!, $p: [String]!) {
          addPhysicalObjectToOrder(orderId: $o, physicalObjects: $p) { ok statusCode } }""",
                        {"o": self.ids["order"], "p": [self.ids["obj_a2"]]})
        self.assert_ok(resp, "addPhysicalObjectToOrder")
        self.assertEqual(db.query(Order).get(self.ids["order"]).deposit, 30)  # bob's limit, not staff's


class A10EmailValidation(SecurityTestCase):

    def test_a10_1_foreign_domains_rejected(self):
        client = self.client_for()
        for email in ("mallory@evil-ovgu.de", "x@ovgu.de.evil.com", "x@prhn.dynpc.net", '"a@b"@ovgu.de'):
            resp = self.gql(client, CREATE_USER, {"email": email})
            self.assert_rejected(resp, "createUser", 403)
        self.assertEqual(db.query(User).filter(User.first_name == "New").count(), 0)

    def test_a10_2_university_domains_accepted(self):
        client = self.client_for()
        for email in ("alice@ovgu.de", "alice@st.ovgu.de", "ALICE.UP@OVGU.DE"):
            self.assert_ok(self.gql(client, CREATE_USER, {"email": email}), "createUser")
        self.assertIsNotNone(db.query(User).filter(User.email == "alice.up@ovgu.de").first())
        # same address in other case is a duplicate
        self.assert_rejected(self.gql(client, CREATE_USER, {"email": "Alice@OVGU.de"}), "createUser", 409)
        # short passwords are rejected
        resp = self.gql(client, """mutation { createUser(email: "short@ovgu.de", firstName: "a", lastName: "b",
                                   password: "short") { ok statusCode } }""")
        self.assert_rejected(resp, "createUser", 400)

    def test_a10_3_email_change_checked(self):
        resp = self.gql(self.client_for("bob"), UPDATE_USER,
                        {"id": self.ids["bob"], "email": "x@evil.com", "current": PASSWORD})
        self.assert_rejected(resp, "updateUser", 403)
        self.assertEqual(db.query(User).get(self.ids["bob"]).email, EMAILS["bob"])


class A11ErrorMasking(SecurityTestCase):

    def test_a11_1_mutation_errors_are_generic_and_logged(self):
        client = self.client_for()
        self.assert_ok(self.gql(client, CREATE_USER, {"email": "first@ovgu.de", "phone": 4711}), "createUser")
        with self.assertLogs("lending", level="ERROR") as logs:
            resp = self.gql(client, CREATE_USER, {"email": "second@ovgu.de", "phone": 4711})
        self.assert_rejected(resp, "createUser", 500)
        self.assertRegex(resp["data"]["createUser"]["infoText"], r"^Interner Fehler \(Ref: [0-9a-f]{8}\)$")
        self.assert_no_leak()
        self.assertIn("IntegrityError", "\n".join(logs.output))
        self.assertIsNone(db.query(User).filter(User.email == "second@ovgu.de").first())

    def test_a11_2_no_exception_text_in_mutations(self):
        pattern = re.compile(r"format_exc|str\(e\)")
        mutations_dir = os.path.join(_BACKEND, "mutations")
        hits = []
        for name in sorted(os.listdir(mutations_dir)):
            if name.endswith(".py"):
                with open(os.path.join(mutations_dir, name), encoding="utf-8") as f:
                    hits += [f"{name}:{i}" for i, line in enumerate(f, 1) if pattern.search(line)]
        self.assertEqual(hits, [])

    def test_a11_3_query_errors_are_generic(self):
        with mock.patch("schema_queries.template_directory", "/nonexistent-directory"), \
                self.assertLogs("lending", level="ERROR"):
            resp = self.gql(self.client_for(), "{ getImprint }")
        self.assertEqual(resp["errors"][0]["message"], "Interner Fehler")
        self.assertNotIn("nonexistent", self.last_text)
        self.assert_no_leak()


class A14GroupsAndTags(SecurityTestCase):

    def test_a14_1_outsider_cannot_touch_empty_group(self):
        client = self.client_for("u")
        self.assert_rejected(self.gql(client, UPDATE_GROUP, {"id": self.ids["empty_group"]}), "updateGroup", 403)
        self.assert_rejected(self.gql(client, DELETE_GROUP, {"id": self.ids["empty_group"]}), "deleteGroup", 403)
        self.assertIsNotNone(db.query(Group).get(self.ids["empty_group"]))

    def test_a14_2_outsider_cannot_touch_empty_tag(self):
        for who in ("u", "ia_a"):
            client = self.client_for(who)
            self.assert_rejected(self.gql(client, UPDATE_TAG, {"id": self.ids["empty_tag"]}), "updateTag", 403)
            self.assert_rejected(self.gql(client, DELETE_TAG, {"id": self.ids["empty_tag"]}), "deleteTag", 403)
        self.assertEqual(db.query(Tag).get(self.ids["empty_tag"]).name, "empty-tag")
        db.remove()
        self.assert_ok(self.gql(self.client_for("root"), DELETE_TAG, {"id": self.ids["empty_tag"]}), "deleteTag")

    def test_a14_3_inventory_admin_updates_own_group(self):
        resp = self.gql(self.client_for("ia_a"), UPDATE_GROUP, {"id": self.ids["group_a"]})
        self.assert_ok(resp, "updateGroup")
        self.assertEqual(db.query(Group).get(self.ids["group_a"]).description, "x")

    def test_a14_4_other_org_admin_cannot_update_group(self):
        resp = self.gql(self.client_for("oa_b"), UPDATE_GROUP, {"id": self.ids["group_a"]})
        self.assert_rejected(resp, "updateGroup", 403)
        self.assertIsNone(db.query(Group).get(self.ids["group_a"]).description)

    def test_a14_tag_create_requires_staff(self):
        create = 'mutation { createTag(name: "new-tag") { ok statusCode } }'
        self.assert_rejected(self.gql(self.client_for("bob"), create), "createTag", 403)
        self.assert_ok(self.gql(self.client_for("ia_a"), create), "createTag")


class A15CrossTenantLinks(SecurityTestCase):

    def test_a15_1_cannot_move_objects_into_own_org(self):
        resp = self.gql(self.client_for("oa_b"), """mutation($org: String!, $p: [String]) {
          updateOrganization(organizationId: $org, physicalobjects: $p) { ok statusCode } }""",
                        {"org": self.ids["org_b"], "p": [self.ids["obj50"]]})
        self.assert_rejected(resp, "updateOrganization", 403)
        self.assertEqual(db.query(PhysicalObject).get(self.ids["obj50"]).organization_id, self.ids["org_a"])

    def test_a15_2_cannot_attach_foreign_picture(self):
        resp = self.gql(self.client_for("oa_b"), """mutation($id: String!, $p: [String]) {
          updatePhysicalObject(physId: $id, pictures: $p) { ok statusCode } }""",
                        {"id": self.ids["obj_b"], "p": [self.ids["file_a"]]})
        self.assert_rejected(resp, "updatePhysicalObject", 403)
        self.assertEqual(db.query(File).get(self.ids["file_a"]).picture_id, self.ids["obj50"])

    def test_a15_3_cannot_create_group_with_foreign_picture(self):
        resp = self.gql(self.client_for("oa_b"), """mutation($org: String!, $p: [String]) {
          createGroup(name: "Stolen", organizationId: $org, pictures: $p) { ok statusCode } }""",
                        {"org": self.ids["org_b"], "p": [self.ids["file_a"]]})
        self.assert_rejected(resp, "createGroup", 403)
        self.assertIsNone(db.query(Group).filter(Group.name == "Stolen").first())

    def test_a15_unattached_file_can_be_linked_by_staff(self):
        resp = self.gql(self.client_for("oa_b"), """mutation($id: String!, $p: [String]) {
          updatePhysicalObject(physId: $id, pictures: $p) { ok statusCode } }""",
                        {"id": self.ids["obj_b"], "p": ["", self.ids["file_free"]]})
        self.assert_ok(resp, "updatePhysicalObject")
        self.assertEqual(db.query(File).get(self.ids["file_free"]).picture_id, self.ids["obj_b"])


class A20Credentials(SecurityTestCase):

    def test_a20_1_password_change_needs_current_password(self):
        client = self.client_for("bob")
        for current in (None, "wrong-password"):
            resp = self.gql(client, UPDATE_USER, {"id": self.ids["bob"], "pw": "new-password-99", "current": current})
            self.assert_rejected(resp, "updateUser", 403)
        self.client_for("bob")  # old password still logs in

    def test_a20_2_password_change_ends_other_sessions(self):
        s1, s2 = self.client_for("bob"), self.client_for("bob")
        resp = self.gql(s1, UPDATE_USER, {"id": self.ids["bob"], "pw": "new-password-99", "current": PASSWORD})
        self.assert_ok(resp, "updateUser")
        resp = self.gql(s2, DELETE_ORDER, {"order": self.ids["order"]})
        self.assert_rejected(resp, "deleteOrder", 419)
        self.assertFalse(self.gql(s2, CHECK_SESSION)["data"]["checkSession"]["ok"])
        self.assertTrue(self.gql(s1, CHECK_SESSION)["data"]["checkSession"]["ok"])

    def test_a20_3_login_issues_new_session_id(self):
        client = self.client_for("bob")
        before = client.get_cookie("session").value
        resp = self.gql(client, """mutation { login(email: "carol.a@ovgu.de", password: "password-1234") { ok } }""")
        self.assertTrue(resp["data"]["login"]["ok"])
        after = client.get_cookie("session").value
        self.assertNotEqual(before, after)
        # the old session id is no longer valid
        old = self.app.test_client()
        old.set_cookie("session", before)
        self.assertFalse(self.gql(old, CHECK_SESSION)["data"]["checkSession"]["ok"])

    def test_a20_login_does_not_reveal_unknown_users(self):
        client = self.client_for()
        unknown = self.gql(client, """mutation { login(email: "nobody@ovgu.de", password: "x") { ok statusCode infoText } }""")
        wrong = self.gql(client, """mutation { login(email: "bob.a@ovgu.de", password: "x") { ok statusCode infoText } }""")
        self.assertEqual(unknown, wrong)
        self.assertEqual(wrong["data"]["login"]["statusCode"], 401)


class AD6MaxDeposit(SecurityTestCase):
    GET = """mutation($org: String!, $r: String!) {
      getMaxDeposit(organizationId: $org, userRight: $r) { ok statusCode maxDeposit } }"""

    def test_get_max_deposit_own_right_only(self):
        bob = self.client_for("bob")
        resp = self.gql(bob, self.GET, {"org": self.ids["org_a"], "r": "customer"})
        self.assertEqual(resp["data"]["getMaxDeposit"]["maxDeposit"], 30)
        self.assert_rejected(self.gql(bob, self.GET, {"org": self.ids["org_a"], "r": "member"}), "getMaxDeposit", 403)
        resp = self.gql(self.client_for("u"), self.GET, {"org": self.ids["org_a"], "r": "customer"})
        self.assertEqual(resp["data"]["getMaxDeposit"]["maxDeposit"], 30)
        resp = self.gql(self.client_for("ia_a"), self.GET, {"org": self.ids["org_a"], "r": "member"})
        self.assertEqual(resp["data"]["getMaxDeposit"]["maxDeposit"], 40)
        self.assert_rejected(self.gql(self.client_for(), self.GET, {"org": self.ids["org_a"], "r": "customer"}),
                             "getMaxDeposit", 419)


if __name__ == "__main__":
    unittest.main()

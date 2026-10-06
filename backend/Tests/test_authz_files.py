"""Authorization regression tests for file uploads, file edits and remaining mutations (QA, SEC-3)."""
import io
import json
import unittest

from Tests.security_fixture import SecurityTestCase
from models import File, PhysicalObject, Organization, User

UPLOAD = "mutation($f:Upload!,$p:String,$m:String,$g:String,$o:String){uploadFile(file:$f,physPictureId:$p,physManualId:$m,groupId:$g,organizationId:$o){ok statusCode file{fileId}}}"


class FileAuthz(SecurityTestCase):

    def upload(self, client, name="x.png", **target):
        variables = {"f": None, "p": target.get("p"), "m": target.get("m"), "g": target.get("g"), "o": target.get("o")}
        data = {
            "operations": json.dumps({"query": UPLOAD, "variables": variables}),
            "map": json.dumps({"0": ["variables.f"]}),
            "0": (io.BytesIO(b"%PDF-1.4" if name.endswith(".pdf") else b"\x89PNG\r\n"), name),
        }
        resp = client.post("/graphql", data=data, content_type="multipart/form-data")
        self.last_text = resp.get_data(as_text=True)
        return resp.get_json()

    def file_count(self):
        return File.query.count()

    def test_upload_requires_login_and_staff(self):
        before = self.file_count()
        self.assert_rejected(self.upload(self.client_for()), "uploadFile", 419)
        self.assert_rejected(self.upload(self.client_for("m_a")), "uploadFile", 403)
        self.assert_rejected(self.upload(self.client_for("u")), "uploadFile", 403)
        self.assertEqual(self.file_count(), before)

    def test_staff_unattached_upload_allowed(self):
        self.assert_ok(self.upload(self.client_for("ia_a")), "uploadFile")

    def test_upload_to_foreign_object_rejected(self):
        before = self.file_count()
        self.assert_rejected(self.upload(self.client_for("ia_a"), p=self.ids["obj_b"]), "uploadFile", 403)
        self.assert_rejected(self.upload(self.client_for("oa_b"), g=self.ids["group_a"]), "uploadFile", 403)
        self.assertEqual(self.file_count(), before)

    def test_upload_attached_to_own_object(self):
        """IA of org A may upload a picture directly attached to an org-A object."""
        resp = self.upload(self.client_for("ia_a"), p=self.ids["obj50"])
        self.assert_ok(resp, "uploadFile")
        file_id = resp["data"]["uploadFile"]["file"]["fileId"]
        self.assertEqual(File.query.get(file_id).picture_id, self.ids["obj50"])

    def test_upload_manual_and_group_picture_of_own_org(self):
        self.assert_ok(self.upload(self.client_for("ia_a"), name="m.pdf", m=self.ids["obj50"]), "uploadFile")
        self.assert_ok(self.upload(self.client_for("ia_a"), g=self.ids["group_a"]), "uploadFile")

    def test_agb_upload_needs_org_admin(self):
        before = self.file_count()
        self.assert_rejected(self.upload(self.client_for("ia_a"), name="agb.pdf", o=self.ids["org_a"]), "uploadFile", 403)
        self.assert_rejected(self.upload(self.client_for("oa_b"), name="agb.pdf", o=self.ids["org_a"]), "uploadFile", 403)
        self.assertEqual(self.file_count(), before)
        self.assert_ok(self.upload(self.client_for("oa_b"), name="agb.pdf", o=self.ids["org_b"]), "uploadFile")

    def test_update_and_delete_file_scoped_to_owner_org(self):
        q_upd = "mutation($f:String!){updateFile(fileId:$f,showIndex:5){ok statusCode}}"
        q_del = "mutation($f:String!){deleteFile(fileId:$f){ok statusCode}}"
        for who in ("oa_b", "m_a", "bob"):
            self.assert_rejected(self.gql(self.client_for(who), q_upd, {"f": self.ids["file_a"]}), "updateFile", 403)
            self.assert_rejected(self.gql(self.client_for(who), q_del, {"f": self.ids["file_a"]}), "deleteFile", 403)
        self.assert_rejected(self.gql(self.client_for(), q_del, {"f": self.ids["file_a"]}), "deleteFile", 419)
        self.assertIsNotNone(File.query.get(self.ids["file_a"]))
        self.assert_ok(self.gql(self.client_for("ia_a"), q_upd, {"f": self.ids["file_a"]}), "updateFile")
        self.assert_ok(self.gql(self.client_for("ia_a"), q_del, {"f": self.ids["file_a"]}), "deleteFile")

    def test_anonymous_filter_files_rejected(self):
        self.assert_query_rejected(self.gql(self.client_for(), "{filterFiles{fileId path}}"), "filterFiles")


class RemainingMutationAuthz(SecurityTestCase):

    def test_delete_physical_object_scoped(self):
        q = "mutation($p:String!){deletePhysicalObject(physId:$p){ok statusCode}}"
        for who in ("oa_b", "m_a", "bob"):
            self.assert_rejected(self.gql(self.client_for(who), q, {"p": self.ids["obj_a2"]}), "deletePhysicalObject", 403)
        self.assertIsNotNone(PhysicalObject.query.get(self.ids["obj_a2"]))
        self.assert_ok(self.gql(self.client_for("ia_a"), q, {"p": self.ids["obj_a2"]}), "deletePhysicalObject")

    def test_set_max_deposit_needs_org_admin(self):
        q = 'mutation($o:String!){setMaxDeposit(organizationId:$o,userRight:"customer",maxDeposit:1){ok statusCode}}'
        for who in ("ia_a", "oa_b", "bob"):
            self.assert_rejected(self.gql(self.client_for(who), q, {"o": self.ids["org_a"]}), "setMaxDeposit", 403)
        self.assertEqual(json.loads(Organization.query.get(self.ids["org_a"]).max_deposit)["customer"], 30)

    def test_delete_user_only_self(self):
        q = "mutation($u:String!){deleteUser(userId:$u){ok statusCode}}"
        self.assert_rejected(self.gql(self.client_for("oa_b"), q, {"u": self.ids["bob"]}), "deleteUser", 403)
        self.assert_rejected(self.gql(self.client_for(), q, {"u": self.ids["bob"]}), "deleteUser", 419)
        self.assertIsNotNone(User.query.get(self.ids["bob"]))


if __name__ == "__main__":
    unittest.main()

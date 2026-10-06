"""
GraphQL request limits: introspection, query depth and document size.

Run from backend/:
    testing_on=1 secret_key=test session_cookie_secure=0 python -m unittest discover -s Tests -p 'test_*.py' -v
"""
import os
import sys
import time
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

import app as app_module  # noqa: E402
from config import db, engine  # noqa: E402
from models import Base  # noqa: E402

# Deepest query the frontend sends (group-helpers.tsx GetAllGroups, depth 8)
GET_ALL_GROUPS = """query GetAllGroups {
  filterGroups { groupId name
    physicalobjects { edges { node { physId name
      pictures(first: 1) { edges { node { fileId path } } }
      tags { edges { node { tagId name } } }
      organization { organizationId name }
      manual { edges { node { path manualId } } } } } }
    organization { organizationId name }
    pictures { edges { node { fileId path } } } } }"""


class GraphQLLimitsTestCase(unittest.TestCase):

    def setUp(self):
        db.remove()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        app_module.ensure_root()
        self.client = app_module.app.test_client()
        self.addCleanup(db.remove)

    def post(self, query):
        response = self.client.post("/graphql", json={"query": query})
        return response.status_code, response.get_json()

    def assert_rejected(self, status, body):
        self.assertEqual(status, 400, body)
        self.assertIsNone(body.get("data"), body)
        self.assertTrue(body.get("errors"), body)

    def test_introspection_disabled(self):
        for query in ("{ __schema { types { name } } }",
                      '{ __type(name: "Query") { fields { name } } }',
                      "query { filterGroups { __schema { queryType { name } } } }"):
            status, body = self.post(query)
            self.assert_rejected(status, body)
            self.assertNotIn("filterGroups", str(body))

    def test_typename_still_allowed(self):
        status, body = self.post("{ __typename }")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["data"]["__typename"], "Query")

    def test_deepest_frontend_query_allowed(self):
        status, body = self.post(GET_ALL_GROUPS)
        self.assertEqual(status, 200, body)
        self.assertNotIn("errors", body)

    @staticmethod
    def chain(depth):
        """Valid query with depth levels of fields, the last one __typename."""
        cycle = ["physicalobjects", "edges", "node", "groups", "edges", "node"]
        fields = ["filterGroups"] + cycle * depth
        query = "__typename"
        for field in reversed(fields[:depth - 1]):
            query = "%s { %s }" % (field, query)
        return "{ %s }" % query

    def test_depth_limit(self):
        status, body = self.post(self.chain(11))
        self.assertEqual(status, 200, body)
        self.assertNotIn("errors", body)
        status, body = self.post(self.chain(12))
        self.assert_rejected(status, body)

    def test_fragment_depth_counted(self):
        status, body = self.post(
            "query { ...F } fragment F on Query " + self.chain(12))
        self.assert_rejected(status, body)

    def test_fragment_fan_out_validated_quickly(self):
        # each fragment spreads the next one twice: 2^24 paths in < 1 KB
        n = 24
        parts = ["query { ...F0 }"]
        parts += ["fragment F%d on Query { ...F%d ...F%d }" % (i, i + 1, i + 1)
                  for i in range(n)]
        parts.append("fragment F%d on Query { __typename }" % n)
        start = time.monotonic()
        status, body = self.post("\n".join(parts))
        self.assertLess(time.monotonic() - start, 2, body)
        self.assertEqual(status, 200, body)

    def test_very_deep_query_rejected_without_internal_error(self):
        query = "{ " + "filterGroups { " * 500 + "name" + " }" * 501
        status, body = self.post(query)
        self.assert_rejected(status, body)
        self.assertNotIn("Interner Fehler", str(body))

    def test_large_document_rejected(self):
        padding = "#" + "x" * 20_000 + "\n"
        status, body = self.post(padding + "{ __typename }")
        self.assert_rejected(status, body)

    def test_document_at_size_limit_allowed(self):
        query = "{ __typename }"
        padding = "#" + "x" * (20_000 - len(query) - 2) + "\n"
        self.assertEqual(len(padding + query), 20_000)
        status, body = self.post(padding + query)
        self.assertEqual(status, 200, body)


if __name__ == "__main__":
    unittest.main()

import unittest
import graphene
from graphene.test import Client

from models import *
from schema_queries import Query
from schema_mutations import Mutations
import Tests.filter_tests as filter
import Tests.mutation_tests as mutations

from Tests.db_test_setups import testDB_base

from config import engine as test_engine, db as test_db, testing_on

class Test(unittest.TestCase):
    def setUp(self):
        schema = graphene.Schema(query=Query, mutation=Mutations)
        
        Base.metadata.create_all(bind = test_engine)

        self.client = Client(schema)
        
        testDB_base(test_db)

    def test_tag_filter(self):
        filter.test_tag_filter(self.client, test_db)

    def test_physicalobject_filter(self):
        filter.test_physicalobject_filter(self.client, test_db)

    def test_order_filter(self):
        filter.test_order_filter(self.client, test_db)
    
    def test_user_filter(self):
        filter.test_user_filter(self.client, test_db)

    def test_group_filter(self):
        filter.test_group_filter(self.client, test_db)

    def test_organization_filter(self):
        filter.test_organization_filter(self.client, test_db)

    def test_mutation_create_user(self):
        mutations.test_create_user(self.client, test_db)

    def tearDown(self):
        # Drop all tables in the database
        Base.metadata.drop_all(test_engine)

if __name__ == '__main__':
    if (int)(testing_on):
        unittest.main()
    else:
        print("Not connected to test database. (Check config file)")
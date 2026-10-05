import os
import graphene
from sqlalchemy import inspect
from flask_graphql import GraphQLView
from flask import Flask, jsonify
from graphene_file_upload.flask import FileUploadGraphQLView as UploadView
from argon2 import PasswordHasher

from config import app, db, engine, application_root_user_name, application_root_user_password
from schema_queries import Query
from schema_mutations import Mutations
from models import Base, userRights
from schema import UserModel, OrganizationModel, Organization_UserModel

# Create tables if they don't exist
inspector = inspect(engine)
if not inspector.has_table('users'):
    print("Creating tables")
    Base.metadata.create_all(engine)

# check if root organization exists
root_organization = OrganizationModel.query.filter(OrganizationModel.name == "root_organization").first()
if (root_organization is None):
    root_organization = OrganizationModel(
        name = "root_organization",
        location = "application"
    )

    db.add(root_organization)
    db.commit()

# check if root user exists
root_user = UserModel.query.filter(UserModel.email == application_root_user_name).first()
if (root_user is None):
    ph = PasswordHasher()
    password_hashed = ph.hash(application_root_user_password)
    root_user = UserModel(
        first_name = "", 
        last_name = "", 
        email = application_root_user_name, 
        password_hash = password_hashed
    )

    db.add(root_user)
    db.commit()

# check if root user is in root organization
root_user_in_organization = Organization_UserModel.query.filter(Organization_UserModel.user == root_user and Organization_UserModel.organization == root_organization).first()
if (root_user_in_organization is None):
    root_user_in_organization = Organization_UserModel(
        organization_id = root_organization.organization_id,
        user_id = root_user.user_id,
        rights = userRights.system_admin
    )

    db.add(root_user_in_organization)
    db.commit()

if (root_user_in_organization.rights != userRights.system_admin):
    root_user_in_organization.rights = userRights.system_admin
    db.commit()

schema = graphene.Schema(query=Query, mutation=Mutations)

app.add_url_rule(
    '/graphql',
    view_func=UploadView.as_view(
        'graphql',
        schema=schema,
        graphiql=os.getenv('graphiql', '0') == '1'
    )
)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.remove()

def check_for_return_dates():
    pass

@app.route("/")
def hello():
    return "<h1>Hello World</h1>"

@app.route('/health')
def health():
    return jsonify(status="healthy"), 200

# for local testing
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

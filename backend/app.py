import os
import graphene
from flask import jsonify
from graphene_file_upload.flask import FileUploadGraphQLView as UploadView
from graphql.error import GraphQLError, format_error as default_format_error
from argon2 import PasswordHasher
from sqlalchemy import func

from config import app, db, engine, scheduler, testing_on, application_root_user_name, application_root_user_password
from schema_queries import Query
from schema_mutations import Mutations
from models import Base, userRights
from authz import AuthzError, PublicError, log
from schema import UserModel, OrganizationModel, Organization_UserModel

# create_all only creates missing tables (checkfirst) and leaves existing ones
# untouched, so new tables are added to existing installs on start
Base.metadata.create_all(engine)


def ensure_root():
    """Create the root organization, the root user and its system_admin membership if missing."""
    root_organization = OrganizationModel.query.filter(OrganizationModel.name == "root_organization").first()
    if root_organization is None:
        root_organization = OrganizationModel(name="root_organization", location="application")
        db.add(root_organization)
        db.commit()

    root_email = (application_root_user_name or "").strip().lower()
    root_user = UserModel.query.filter(func.lower(UserModel.email) == root_email).first()
    if root_user is None:
        root_user = UserModel(
            first_name="",
            last_name="",
            email=root_email,
            password_hash=PasswordHasher().hash(application_root_user_password)
        )
        db.add(root_user)
        db.commit()

    membership = Organization_UserModel.query.filter(
        Organization_UserModel.user_id == root_user.user_id,
        Organization_UserModel.organization_id == root_organization.organization_id).first()
    if membership is None:
        membership = Organization_UserModel(
            organization_id=root_organization.organization_id,
            user_id=root_user.user_id,
            rights=userRights.system_admin
        )
        db.add(membership)
    membership.rights = userRights.system_admin
    db.commit()


ensure_root()

if not testing_on:
    scheduler.start()

schema = graphene.Schema(query=Query, mutation=Mutations)


def safe_format_error(error):
    """Only public errors and GraphQL syntax/validation errors reach the client verbatim."""
    original = getattr(error, 'original_error', None)
    if isinstance(error, PublicError) or isinstance(original, PublicError):
        return default_format_error(error)
    if isinstance(original, AuthzError):
        formatted = default_format_error(error)
        formatted['message'] = original.message
        return formatted
    if isinstance(error, GraphQLError) and original is None:
        return default_format_error(error)
    log.error("unhandled GraphQL error", exc_info=(type(original or error), original or error,
                                                   getattr(original or error, '__traceback__', None)))
    formatted = {"message": "Interner Fehler"}
    if isinstance(error, GraphQLError):
        if error.locations is not None:
            formatted["locations"] = [{"line": loc.line, "column": loc.column} for loc in error.locations]
        if error.path is not None:
            formatted["path"] = error.path
    return formatted


class SafeGraphQLView(UploadView):
    format_error = staticmethod(safe_format_error)


app.add_url_rule(
    '/graphql',
    view_func=SafeGraphQLView.as_view(
        'graphql',
        schema=schema,
        graphiql=os.getenv('graphiql', '0') == '1'
    )
)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.remove()

@app.route("/")
def hello():
    return "<h1>Hello World</h1>"

@app.route('/health')
def health():
    return jsonify(status="healthy"), 200

# for local testing
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

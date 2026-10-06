from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from flask import current_app, session
import graphene
from sqlalchemy import func

from authz import guarded, viewer, reset_viewer
from config import db
from models import UserAuthEpoch
from schema import UserModel

LOGIN_FAILED = "Die Anmeldung ist fehlgeschlagen!"

# Verified against for unknown users so both failure paths cost the same
_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")

##################################
# Mutations for Users login      #
##################################
class login(graphene.Mutation):
    class Arguments:
        email       = graphene.String(required=True)
        password    = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, email, password):
        user = UserModel.query.filter(func.lower(UserModel.email) == (email or "").strip().lower()).first()

        try:
            _ph.verify(user.password_hash if user else _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            return login(ok=False, info_text=LOGIN_FAILED, status_code=401)
        if user is None:
            return login(ok=False, info_text=LOGIN_FAILED, status_code=401)

        if _ph.check_needs_rehash(user.password_hash):
            user.password_hash = _ph.hash(password)
            db.commit()

        epoch_row = db.query(UserAuthEpoch).get(user.user_id)

        # New session id on login (no session fixation)
        session.clear()
        session['user_id'] = user.user_id
        session['auth_epoch'] = epoch_row.epoch if epoch_row else 0
        current_app.session_interface.regenerate(session)
        reset_viewer()
        return login(ok=True, info_text="Die Anmeldung war erfolgreich!", status_code=200)

class check_session(graphene.Mutation):
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()
    user_id     = graphene.String()

    @staticmethod
    @guarded
    def mutate(root, info):
        user_id = viewer().user_id
        if user_id:
            return check_session(ok=True, info_text='Es liegt eine gültige Session vor.', user_id=user_id, status_code=200)
        else:
            return check_session(ok=False, info_text='Unautorisierter Zugriff.', user_id=None, status_code=404)

class logout(graphene.Mutation):
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info):
        logged_in = bool(session.get('user_id'))
        session.clear()
        reset_viewer()
        if logged_in:
            return logout(ok=True, info_text='Logout erfolgreich!', status_code=200)
        else:
            return logout(ok=False, info_text='User nicht angemeldet.', status_code=404)

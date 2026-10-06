from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from flask import session
import graphene
from sqlalchemy import func

from authz import (
    guarded,
    require_user,
    bump_auth_epoch,
    reset_viewer,
    Forbidden,
    NotFound,
)
from config import db
from schema import User, UserModel
from validation import validate_email, validate_password

EMAIL_IN_USE = "Die angegebene E-Mail wird bereits verwendet."
WRONG_PASSWORD = "Das aktuelle Passwort ist falsch."


def _email_taken(email, except_user_id=None):
    query = UserModel.query.filter(func.lower(UserModel.email) == email)
    if except_user_id:
        query = query.filter(UserModel.user_id != except_user_id)
    return query.first() is not None


OPTIONAL_FIELDS = ("country", "city", "postcode", "street", "house_number",
                   "phone_number", "matricle_number")


def _set_optional_fields(user, fields):
    for key in OPTIONAL_FIELDS:
        if fields.get(key):
            setattr(user, key, fields[key])


##################################
# Mutations for Users            #
##################################
class create_user(graphene.Mutation):
    """
    Creates a new user with the given parameters.
    """

    class Arguments:
        # Required user arguments
        email       = graphene.String(required=True)
        last_name   = graphene.String(required=True)
        first_name  = graphene.String(required=True)
        password    = graphene.String(required=True)

        # Optional user arguments
        country         = graphene.String(required=False)
        city            = graphene.String(required=False)
        postcode        = graphene.Int(required=False)
        street          = graphene.String(required=False)
        house_number    = graphene.Int(required=False)
        phone_number    = graphene.Int(required=False)
        matricle_number = graphene.Int(required=False)

    user        = graphene.Field(lambda: User)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(
        root,
        info,
        email,
        last_name,
        first_name,
        password,
        **optional,
    ):
        # optional: OPTIONAL_FIELDS (see Arguments)
        email = validate_email(email)
        validate_password(password)

        if _email_taken(email):
            return create_user(
                ok=False, info_text=EMAIL_IN_USE, status_code=409
            )

        user = UserModel(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=PasswordHasher().hash(password),
        )
        _set_optional_fields(user, optional)

        db.add(user)
        db.commit()
        return create_user(
            ok=True,
            info_text="Der Nutzer wurde erfolgreich angelegt.",
            user=user,
            status_code=200,
        )


class update_user(graphene.Mutation):
    """
    Updates content of the own user. Changing email or password requires
    current_password.
    """

    class Arguments:
        # Required user arguments
        user_id     = graphene.String(required=True)
        email       = graphene.String(required=False)
        last_name   = graphene.String(required=False)
        first_name  = graphene.String(required=False)
        password    = graphene.String(required=False)
        current_password = graphene.String(required=False)

        # Optional user arguments
        country         = graphene.String(required=False)
        city            = graphene.String(required=False)
        postcode        = graphene.Int(required=False)
        street          = graphene.String(required=False)
        house_number    = graphene.Int(required=False)
        phone_number    = graphene.Int(required=False)
        matricle_number = graphene.Int(required=False)

    user        = graphene.Field(lambda: User)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(
        root,
        info,
        user_id,
        email=None,
        last_name=None,
        first_name=None,
        password=None,
        current_password=None,
        **optional,
    ):
        # optional: OPTIONAL_FIELDS (see Arguments)
        v = require_user()
        if v.user_id != user_id:
            raise Forbidden()

        user = UserModel.query.filter(UserModel.user_id == user_id).first()
        if not user:
            raise NotFound("Nutzer nicht gefunden.")

        if email or password:
            try:
                PasswordHasher().verify(
                    user.password_hash, current_password or ""
                )
            except (VerificationError, InvalidHashError):
                raise Forbidden(WRONG_PASSWORD)

        if email:
            email = validate_email(email)
            if _email_taken(email, except_user_id=user.user_id):
                return update_user(
                    ok=False, info_text=EMAIL_IN_USE, status_code=409
                )
            user.email = email
        if password:
            validate_password(password)
            user.password_hash = PasswordHasher().hash(password)
            # invalidate all other sessions; keep the current one valid
            session['auth_epoch'] = bump_auth_epoch(user.user_id)
            reset_viewer()
        if last_name:
            user.last_name = last_name
        if first_name:
            user.first_name = first_name
        _set_optional_fields(user, optional)

        db.commit()
        return update_user(
            ok=True,
            info_text="User updated successfully",
            user=user,
            status_code=200,
        )


class delete_user(graphene.Mutation):
    """
    Deletes the own user.
    """

    class Arguments:
        user_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, user_id):
        v = require_user()
        if v.user_id != user_id:
            raise Forbidden()

        user = UserModel.query.filter(UserModel.user_id == user_id).first()
        if not user:
            raise NotFound("Nutzer konnte nicht entfernt werden.")
        db.delete(user)
        db.commit()
        session.clear()
        reset_viewer()
        return delete_user(
            ok=True, info_text="Nutzer erfolgreich entfernt.", status_code=200
        )

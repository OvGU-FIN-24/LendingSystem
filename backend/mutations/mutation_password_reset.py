import graphene

import password_reset
from authz import guarded, log
from config import db


##################################
# Mutations for password reset   #
##################################
class request_password_reset(graphene.Mutation):
    """
    Emails a single-use reset link if the account exists and mail is configured.
    The answer is the same in every case.
    """

    class Arguments:
        email = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, email):
        try:
            password_reset.request_reset(email)
        except Exception:
            # an error must not reveal whether the account exists
            db.rollback()
            log.exception("password reset request failed")
        return request_password_reset(ok=True, info_text=password_reset.REQUEST_INFO, status_code=200)


class confirm_password_reset(graphene.Mutation):
    """
    Sets a new password with a token from a reset link and signs out all sessions of the user.
    """

    class Arguments:
        token        = graphene.String(required=True)
        new_password = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, token, new_password):
        password_reset.confirm_reset(token, new_password)
        return confirm_password_reset(ok=True, info_text="Das Passwort wurde geändert.", status_code=200)

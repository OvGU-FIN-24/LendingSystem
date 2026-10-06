# Stub: replaced by the password reset implementation (request/confirm).
import graphene


class request_password_reset(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    def mutate(root, info, email):
        raise NotImplementedError


class confirm_password_reset(graphene.Mutation):
    class Arguments:
        token        = graphene.String(required=True)
        new_password = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    def mutate(root, info, token, new_password):
        raise NotImplementedError

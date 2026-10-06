import graphene

from authz import (guarded, require_user, require_sa, require_right, require_files_linkable,
                   check_grant, parse_right, clean_ids, reset_viewer, ROOT_ORGANIZATION,
                   Forbidden, NotFound, InvalidInput)
from config import db
from models import userRights
from schema import FileModel, Organization, OrganizationModel, Organization_User, Organization_UserModel, PhysicalObjectModel, UserModel


def _get_organization(organization_id):
    organization = db.query(OrganizationModel).get(organization_id) if organization_id else None
    if organization is None:
        raise NotFound("Organisation nicht gefunden.")
    return organization


def _get_user(user_id):
    user = db.query(UserModel).get(user_id) if user_id else None
    if user is None:
        raise NotFound("Benutzer existiert nicht.")
    return user


def _root_users():
    """Global system admins (system_admin members of root_organization)."""
    return (db.query(UserModel)
            .join(Organization_UserModel, Organization_UserModel.user_id == UserModel.user_id)
            .join(OrganizationModel, OrganizationModel.organization_id == Organization_UserModel.organization_id)
            .filter(OrganizationModel.name == ROOT_ORGANIZATION,
                    Organization_UserModel.rights == userRights.system_admin).all())


##################################
# Mutations for Organizations    #
##################################
class create_organization(graphene.Mutation):
    """
    Creates a new organization with the given parameters.
    For Connections to users and physical objects use array of their String uuid
    """

    class Arguments:
        # organization arguments
        name        = graphene.String(required=True)
        location    = graphene.String(required=True)

        # organization connections
        users           = graphene.List(graphene.String)
        physicalobjects = graphene.List(graphene.String)
        agb             = graphene.String()

    organization    = graphene.Field(lambda: Organization)
    ok              = graphene.Boolean()
    info_text       = graphene.String()
    status_code     = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, name, location, users=None, physicalobjects=None, agb=None):
        v = require_sa()

        organization = OrganizationModel(name=name, location=location)
        db.add(organization)

        if agb:
            db_agb = db.query(FileModel).get(agb)
            if db_agb is None:
                raise NotFound("Datei nicht gefunden.")
            organization.agb = [db_agb]
        phys_ids = clean_ids(physicalobjects)
        if phys_ids:
            organization.physicalobjects = db.query(PhysicalObjectModel).filter(
                PhysicalObjectModel.phys_id.in_(phys_ids)).all()
        db.flush()

        # global system admins get system_admin, listed users customer
        member_ids = set()
        for root_user in _root_users():
            db.add(Organization_UserModel(user_id=root_user.user_id, organization_id=organization.organization_id,
                                          rights=userRights.system_admin))
            member_ids.add(root_user.user_id)
        if v.user_id not in member_ids:
            db.add(Organization_UserModel(user_id=v.user_id, organization_id=organization.organization_id,
                                          rights=userRights.organization_admin))
            member_ids.add(v.user_id)
        for user in db.query(UserModel).filter(UserModel.user_id.in_(clean_ids(users))).all():
            if user.user_id not in member_ids:
                db.add(Organization_UserModel(user_id=user.user_id, organization_id=organization.organization_id,
                                              rights=userRights.customer))
                member_ids.add(user.user_id)

        db.commit()
        reset_viewer()
        return create_organization(ok=True, info_text="Organisation erfolgreich erstellt.", organization=organization, status_code=200)


class update_organization(graphene.Mutation):
    """
    Updates content of the organization with the given organization_id.
    For Connections to users and physical objects use array of their String uuid
    """

    class Arguments:
        # organization arguments
        organization_id     = graphene.String()
        name                = graphene.String()
        location            = graphene.String()

        # organization connections
        physicalobjects = graphene.List(graphene.String)
        agb             = graphene.String()

    organization    = graphene.Field(lambda: Organization)
    ok              = graphene.Boolean()
    info_text       = graphene.String()
    status_code     = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, organization_id=None, name=None, location=None, physicalobjects=None, agb=None):
        require_right(organization_id, userRights.organization_admin)
        organization = _get_organization(organization_id)

        # the root organisation name identifies global system admins
        if name and ROOT_ORGANIZATION in (organization.name, name):
            require_sa()
        phys_ids = clean_ids(physicalobjects)
        if phys_ids:
            # moving objects between organisations is reserved to system admins
            require_sa()
        db_agb = require_files_linkable([agb], organization_id) if agb else []

        if name:
            organization.name = name
        if location:
            organization.location = location
        if phys_ids:
            organization.physicalobjects = db.query(PhysicalObjectModel).filter(
                PhysicalObjectModel.phys_id.in_(phys_ids)).all()
        if db_agb:
            # reset user agreement
            organization.reset_user_agreement()
            organization.agb = db_agb

        db.commit()
        return update_organization(ok=True, info_text="Organisation erfolgreich aktualisiert.", organization=organization, status_code=200)


class add_user_to_organization(graphene.Mutation):
    """
    Adds the user with the given user_id to the organization with the given organization_id.
    """

    class Arguments:
        organization_id = graphene.String(required=True)
        user_id         = graphene.String(required=True)
        user_right      = graphene.String()

    organization_user   = graphene.List(lambda: Organization_User)
    ok                  = graphene.Boolean()
    info_text           = graphene.String()
    status_code         = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, user_id, organization_id, user_right="customer"):
        v = require_right(organization_id, userRights.organization_admin)
        right = parse_right(user_right)
        check_grant(v, organization_id, user_id, right)
        _get_organization(organization_id)
        _get_user(user_id)

        if db.query(Organization_UserModel).get((organization_id, user_id)) is not None:
            raise InvalidInput("Der Benutzer ist bereits Mitglied der Organisation.")

        organization_user = Organization_UserModel(user_id=user_id, organization_id=organization_id, rights=right)
        db.add(organization_user)
        db.commit()
        return add_user_to_organization(ok=True, info_text="User erfolgreich zur Organisation hinzugefügt.", organization_user=[organization_user], status_code=200)


class remove_user_from_organization(graphene.Mutation):
    """
    Removes the user with the given user_id from the organization with the given organization_id.
    """

    class Arguments:
        user_id         = graphene.String(required=True)
        organization_id = graphene.String(required=True)

    organization    = graphene.Field(lambda: Organization)
    ok              = graphene.Boolean()
    info_text       = graphene.String()
    status_code     = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, user_id, organization_id):
        v = require_right(organization_id, userRights.organization_admin)
        check_grant(v, organization_id, user_id)
        organization = _get_organization(organization_id)

        membership = db.query(Organization_UserModel).get((organization_id, user_id))
        if membership is None:
            raise NotFound("Der Benutzer ist kein Mitglied der Organisation.")
        db.delete(membership)
        db.commit()
        return remove_user_from_organization(ok=True, info_text="User erfolgreich aus der Organisation entfernt.", organization=organization, status_code=200)


class update_user_rights(graphene.Mutation):
    """
    Updates the rights for the given user in the organization (adds the user if not a member).
    """

    class Arguments:
        organization_id = graphene.String(required=True)
        user_id         = graphene.String(required=True)
        new_rights      = graphene.String(required=True)

    organization    = graphene.Field(lambda: Organization)
    ok              = graphene.Boolean()
    info_text       = graphene.String()
    status_code     = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, user_id, organization_id, new_rights):
        v = require_right(organization_id, userRights.organization_admin)
        right = parse_right(new_rights)
        check_grant(v, organization_id, user_id, right)
        organization = _get_organization(organization_id)
        _get_user(user_id)

        membership = db.query(Organization_UserModel).get((organization_id, user_id))
        if membership is None:
            db.add(Organization_UserModel(user_id=user_id, organization_id=organization_id, rights=right))
        else:
            membership.rights = right

        db.commit()
        return update_user_rights(ok=True, info_text="Rechte erfolgreich aktualisiert.", organization=organization, status_code=200)


class get_max_deposit(graphene.Mutation):
    """
    gets the max deposit for the given organization and user right
    """

    class Arguments:
        organization_id = graphene.String(required=True)
        user_right      = graphene.String(required=True)

    max_deposit = graphene.Int()
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, organization_id, user_right):
        v = require_user()
        right = parse_right(user_right)
        organization = db.query(OrganizationModel).get(organization_id) if organization_id else None
        if organization is None:
            raise Forbidden()
        # staff may read every limit; everyone else only the limit for their own right
        if not v.has(organization_id, userRights.inventory_admin):
            own_right = v.right_in(organization_id) or userRights.customer
            if right != own_right:
                raise Forbidden()
        return get_max_deposit(ok=True, info_text="Max Deposit erfolgreich abgefragt.",
                               max_deposit=organization.get_max_deposit(right), status_code=200)


class set_max_deposit(graphene.Mutation):
    """
    sets the max deposit for the given organization and user right
    """

    class Arguments:
        organization_id = graphene.String(required=True)
        user_right      = graphene.String(required=True)
        max_deposit     = graphene.Int(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, organization_id, user_right, max_deposit):
        require_right(organization_id, userRights.organization_admin)
        right = parse_right(user_right)
        organization = _get_organization(organization_id)
        try:
            organization.set_max_deposit(right.name, max_deposit)
        except KeyError:
            raise InvalidInput("Ungültiges Recht")

        db.commit()
        return set_max_deposit(ok=True, info_text="Max Deposit erfolgreich gesetzt.", status_code=200)


class delete_organization(graphene.Mutation):
    """
    Deletes the organization with the given organization_id.
    """

    class Arguments:
        organization_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, organization_id):
        require_sa()
        organization = db.query(OrganizationModel).get(organization_id) if organization_id else None
        if organization is None:
            raise NotFound("Organisation konnte nicht entfernt werden.")
        if organization.name == ROOT_ORGANIZATION:
            raise Forbidden()

        db.delete(organization)
        db.commit()
        reset_viewer()
        return delete_organization(ok=True, info_text="Organisation erfolgreich entfernt.", status_code=200)

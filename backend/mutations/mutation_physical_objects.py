import graphene

from authz import (
    guarded,
    require_user,
    require_right,
    require_files_linkable,
    require_linkable,
    clean_ids,
    org_of_phys,
    InvalidInput,
    NotFound,
)
from config import db
from models import userRights
from schema import GroupModel, PhysicalObject, PhysicalObjectModel, TagModel

##################################
# Mutations for Physical Objects #
##################################

def _tags(ids):
    ids = clean_ids(ids)
    return (
        db.query(TagModel).filter(TagModel.tag_id.in_(ids)).all()
        if ids
        else []
    )


def _update_fields(physical_object, fields):
    """Sets the given non-empty fields; borrowable may also be set to
    False."""
    for key, value in fields.items():
        if value or (key == "borrowable" and value is not None):
            setattr(physical_object, key, value)


class create_physical_object(graphene.Mutation):
    """
    Creates a new physical object with the given parameters.
    For Connections to tags, orders, groups and organizations use array of their String uuid
    """

    class Arguments:
        # physical objects arguments
        inv_num_internal    = graphene.Int(required=True)
        inv_num_external    = graphene.Int(required=True)
        deposit             = graphene.Int(required=True)
        storage_location    = graphene.String(required=True)
        storage_location2   = graphene.String(required=True)
        faults              = graphene.String()
        name                = graphene.String(required=True)
        description         = graphene.String()
        borrowable          = graphene.Boolean(required=True)
        lending_comment     = graphene.String()
        return_comment      = graphene.String()
        organization_id     = graphene.String(required=True)  # ein Objekt ist immer genau einer Organisation zugeordnet

        # physical objects connections
        pictures    = graphene.List(graphene.String)
        manual      = graphene.List(graphene.String)
        tags        = graphene.List(graphene.String)
        orders      = graphene.List(graphene.String)
        groups      = graphene.List(graphene.String)

    physical_object     = graphene.Field(lambda: PhysicalObject)
    ok                  = graphene.Boolean()
    info_text           = graphene.String()
    status_code         = graphene.Int()

    @staticmethod
    @guarded
    def mutate(
        root,
        info,
        organization_id,
        tags=None,
        pictures=None,
        manual=None,
        orders=None,
        groups=None,
        **fields,
    ):
        # fields: the scalar arguments of the object (see Arguments)
        require_right(organization_id, userRights.inventory_admin)
        if clean_ids(orders):
            raise InvalidInput(
                "Neue Objekte können keinen Bestellungen zugeordnet werden."
            )
        db_pictures = require_files_linkable(pictures, organization_id)
        db_manual = require_files_linkable(manual, organization_id)
        db_groups = require_linkable(GroupModel, groups, organization_id)

        physical_object = PhysicalObjectModel(
            organization_id=organization_id, **fields
        )
        if db_pictures:
            physical_object.pictures = db_pictures
        if db_manual:
            physical_object.manual = db_manual
        if db_groups:
            physical_object.groups = db_groups
        if clean_ids(tags):
            physical_object.tags = _tags(tags)

        db.add(physical_object)
        db.commit()
        return create_physical_object(
            ok=True,
            info_text="Objekt erfolgreich erstellt.",
            physical_object=physical_object,
            status_code=200,
        )


class update_physical_object(graphene.Mutation):
    """
    Updates content of the physical object with the given phys_id.
    For Connections to tags, orders, groups and organizations use array of their String uuid
    """

    class Arguments:
        # physical object arguments
        phys_id             = graphene.String(required=True)
        inv_num_internal    = graphene.Int()
        inv_num_external    = graphene.Int()
        deposit             = graphene.Int()
        borrowable          = graphene.Boolean()
        storage_location    = graphene.String()
        storage_location2   = graphene.String()
        faults              = graphene.String()
        name                = graphene.String()
        description         = graphene.String()
        organization_id     = graphene.String()

        # physical object connections
        pictures    = graphene.List(graphene.String, description="List of picture file ids; Override existing pictures")
        manual      = graphene.List(graphene.String, description="List of manual file ids; Override existing manual")
        tags        = graphene.List(graphene.String, description="List of tag ids; Override existing tags")
        orders = graphene.List(
            graphene.String,
            description="Not supported; orders are managed through "
            "order mutations",
        )
        groups      = graphene.List(graphene.String, description="List of group ids; Override existing groups")

    physical_object = graphene.Field(lambda: PhysicalObject)
    ok              = graphene.Boolean()
    info_text       = graphene.String()
    status_code     = graphene.Int()

    @staticmethod
    @guarded
    def mutate(
        root,
        info,
        phys_id,
        organization_id=None,
        pictures=None,
        manual=None,
        tags=None,
        orders=None,
        groups=None,
        **fields,
    ):
        # fields: the scalar arguments of the object (see Arguments)
        org_id = org_of_phys(phys_id)
        require_right(org_id, userRights.inventory_admin)
        physical_object = db.query(PhysicalObjectModel).get(phys_id)
        if not physical_object:
            raise NotFound("Objekt nicht gefunden.")

        if clean_ids(orders):
            raise InvalidInput(
                "Bestellungen können hier nicht geändert werden."
            )
        target_org = org_id
        if organization_id and organization_id != org_id:
            # moving an object requires inventory rights in both organisations
            require_right(organization_id, userRights.inventory_admin)
            target_org = organization_id
        db_pictures = require_files_linkable(pictures, target_org)
        db_manual = require_files_linkable(manual, target_org)
        db_groups = require_linkable(GroupModel, groups, target_org)

        if target_org != org_id:
            physical_object.organization_id = target_org
        _update_fields(physical_object, fields)

        if db_pictures:
            physical_object.pictures = db_pictures
        if db_manual:
            physical_object.manual = db_manual
        if clean_ids(tags):
            physical_object.tags = _tags(tags)
        if db_groups:
            physical_object.groups = db_groups

        db.commit()
        return update_physical_object(
            ok=True,
            info_text="Objekt erfolgreich aktualisiert.",
            physical_object=physical_object,
            status_code=200,
        )


class delete_physical_object(graphene.Mutation):
    """
    Deletes the physical object with the given phys_id.
    """

    class Arguments:
        phys_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, phys_id):
        require_right(org_of_phys(phys_id), userRights.inventory_admin)
        physical_object = db.query(PhysicalObjectModel).get(phys_id)
        db.delete(physical_object)
        db.commit()
        return delete_physical_object(
            ok=True, info_text="Objekt erfolgreich entfernt.", status_code=200
        )


class is_physical_object_available(graphene.Mutation):
    """
    Checks if the physical object with the given phys_id is available.
    """

    class Arguments:
        phys_id     = graphene.String(required=True)

        start_date  = graphene.Date(required=True)
        end_date    = graphene.Date(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()
    is_available = graphene.Boolean()

    @staticmethod
    @guarded
    def mutate(root, info, phys_id, start_date, end_date):
        require_user()
        physical_object = db.query(PhysicalObjectModel).get(phys_id)
        if not physical_object:
            raise NotFound("Objekt nicht gefunden.")

        for phys_order in physical_object.orders:
            order = phys_order.order
            if (
                order.from_date.date() <= end_date
                and order.till_date.date() >= start_date
            ):
                return is_physical_object_available(ok=True, info_text="Objekt nicht verfügbar.", is_available=False, status_code=200)

        return is_physical_object_available(ok=True, info_text="Objekt verfügbar.", is_available=True, status_code=200)

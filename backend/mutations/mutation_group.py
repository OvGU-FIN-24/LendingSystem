import graphene

from authz import (guarded, require_right, require_files_linkable, require_linkable,
                   clean_ids, org_of_group, NotFound)
from config import db
from models import userRights
from schema import Group, GroupModel, OrganizationModel, PhysicalObjectModel, TagModel


def _tags(ids):
    ids = clean_ids(ids)
    return db.query(TagModel).filter(TagModel.tag_id.in_(ids)).all() if ids else []


##################################
# Mutations for Groups           #
##################################
class create_group(graphene.Mutation):
    """
    Creates a new group with the given parameters.
    For Connections to physical objects use array of their String uuid
    """

    class Arguments:
        name            = graphene.String(required=True)
        organization_id = graphene.String(required=True)
        description     = graphene.String()

        pictures        = graphene.List(graphene.String)
        physicalobjects = graphene.List(graphene.String)
        tags            = graphene.List(graphene.String)


    group       = graphene.Field(lambda: Group)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, name, organization_id, description=None, pictures=None, physicalobjects=None, tags=None):
        require_right(organization_id, userRights.inventory_admin)
        organization = db.query(OrganizationModel).get(organization_id)
        if organization is None:
            raise NotFound("Organisation nicht gefunden.")
        db_pictures = require_files_linkable(pictures, organization_id)
        db_physicalobjects = require_linkable(PhysicalObjectModel, physicalobjects, organization_id)

        group = GroupModel(name=name, organization=organization)
        if description:
            group.description = description
        if db_pictures:
            group.pictures = db_pictures
        if db_physicalobjects:
            group.physicalobjects = db_physicalobjects
        if clean_ids(tags):
            group.tags = _tags(tags)

        db.add(group)
        db.commit()
        return create_group(ok=True, info_text="Gruppe erfolgreich erstellt.", group=group, status_code=200)


class update_group(graphene.Mutation):
    """
    Updates content of the group with the given group_id.
    For Connections to physical objects use array of their String uuid
    """
    class Arguments:
        group_id        = graphene.String(required=True)
        name            = graphene.String()
        description     = graphene.String()

        physicalobjects = graphene.List(graphene.String)
        pictures        = graphene.List(graphene.String)
        tags            = graphene.List(graphene.String)

    group       = graphene.Field(lambda: Group)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, group_id, name=None, description=None, physicalobjects=None, pictures=None, tags=None):
        org_id = org_of_group(group_id)
        require_right(org_id, userRights.inventory_admin)
        group = db.query(GroupModel).get(group_id)
        db_pictures = require_files_linkable(pictures, org_id)
        db_physicalobjects = require_linkable(PhysicalObjectModel, physicalobjects, org_id)

        if db_physicalobjects:
            group.physicalobjects = db_physicalobjects
        if name:
            group.name = name
        if description:
            group.description = description
        if db_pictures:
            group.pictures = db_pictures
        if clean_ids(tags):
            group.tags = _tags(tags)

        db.commit()
        return update_group(ok=True, info_text="Gruppe erfolgreich aktualisiert.", group=group, status_code=200)


class delete_group(graphene.Mutation):
    """
    Deletes the group with the given group_id.
    """

    class Arguments:
        group_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, group_id):
        require_right(org_of_group(group_id), userRights.inventory_admin)
        group = db.query(GroupModel).get(group_id)
        db.delete(group)
        db.commit()
        return delete_group(ok=True, info_text="Gruppe erfolgreich entfernt.", status_code=200)

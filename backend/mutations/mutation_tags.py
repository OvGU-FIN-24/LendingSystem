import graphene

from authz import guarded, require_user, require_staff_anywhere, require_tag_edit, clean_ids, Forbidden
from config import db
from models import userRights
from schema import GroupModel, PhysicalObjectModel, Tag, TagModel


def _linkable_for_tag(v, model, ids):
    """Every referenced object or group must exist and the caller needs IA+ in its org."""
    objs = []
    for ident in clean_ids(ids):
        obj = db.query(model).get(ident)
        if obj is None or not v.has(obj.organization_id, userRights.inventory_admin):
            raise Forbidden()
        objs.append(obj)
    return objs


##################################
# Mutations for Tags             #
##################################
class create_tag(graphene.Mutation):
    """
    Creates a new tag with the given parameters.
    For Connections to physical objects use array of their String uuid
    """

    class Arguments:
        name            = graphene.String(required=True)

        physicalobjects = graphene.List(graphene.String)
        groups          = graphene.List(graphene.String)

    tag         = graphene.Field(lambda: Tag)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, name, physicalobjects=None, groups=None):
        v = require_staff_anywhere()
        db_physicalobjects = _linkable_for_tag(v, PhysicalObjectModel, physicalobjects)
        db_groups = _linkable_for_tag(v, GroupModel, groups)

        tag = TagModel(name=name)
        if db_physicalobjects:
            tag.physicalobjects = db_physicalobjects
        if db_groups:
            tag.groups = db_groups

        db.add(tag)
        db.commit()
        return create_tag(ok=True, info_text="Tag erfolgreich erstellt.", tag=tag, status_code=200)


class update_tag(graphene.Mutation):
    """
    Updates content of the tag with the given tag_id.
    For Connections to physical objects use array of their String uuid
    """

    class Arguments:
        tag_id          = graphene.String(required=True)
        name            = graphene.String()

        physicalobjects = graphene.List(graphene.String)
        groups          = graphene.List(graphene.String)

    tag         = graphene.Field(lambda: Tag)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, tag_id, name=None, physicalobjects=None, groups=None):
        tag = require_tag_edit(tag_id)
        v = require_user()
        db_physicalobjects = _linkable_for_tag(v, PhysicalObjectModel, physicalobjects)
        db_groups = _linkable_for_tag(v, GroupModel, groups)

        if db_physicalobjects:
            tag.physicalobjects = db_physicalobjects
        if db_groups:
            tag.groups = db_groups
        if name:
            tag.name = name

        db.commit()
        return update_tag(ok=True, info_text="Tag erfolgreich aktualisiert.", tag=tag, status_code=200)


class delete_tag(graphene.Mutation):
    """
    Deletes the tag with the given tag_id.
    """

    class Arguments:
        tag_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, tag_id):
        tag = require_tag_edit(tag_id)
        db.delete(tag)
        db.commit()
        return delete_tag(ok=True, info_text="Tag erfolgreich entfernt.", status_code=200)

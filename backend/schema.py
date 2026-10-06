import graphene
from graphene import relay
from graphene_sqlalchemy import SQLAlchemyObjectType

from authz import viewer, order_visible, user_level, LEVEL_CONTACT, LEVEL_FULL
from models import (PhysicalObject as PhysicalObjectModel,
                    Tag as TagModel,
                    Organization as OrganizationModel,
                    Order as OrderModel,
                    Group as GroupModel,
                    User as UserModel,
                    Organization_User as Organization_UserModel,
                    File as FileModel,
                    PhysicalObject_Order as PhysicalObject_OrderModel,
                    userRights,
                    )

# Field-level access control: edges that are not visible return [] (never None,
# because graphene-sqlalchemy falls back to an unfiltered query for None).

class PhysicalObject(SQLAlchemyObjectType):
    class Meta:
        model = PhysicalObjectModel
        interfaces = (relay.Node, )
        description = PhysicalObjectModel.__doc__

    def resolve_orders(self, info, **kwargs):
        v = viewer()
        return [po for po in self.orders if order_visible(v, po.order)]

class Tag(SQLAlchemyObjectType):
    class Meta:
        model = TagModel
        interfaces = (relay.Node, )
        description = TagModel.__doc__

class Organization(SQLAlchemyObjectType):
    class Meta:
        model = OrganizationModel
        interfaces = (relay.Node, )
        description = OrganizationModel.__doc__

    max_deposit = graphene.String()

    def resolve_users(self, info, **kwargs):
        if viewer().has(self.organization_id, userRights.organization_admin):
            return list(self.users)
        return []

    def resolve_orders(self, info, **kwargs):
        v = viewer()
        return [o for o in self.orders if order_visible(v, o)]

    def resolve_max_deposit(self, info):
        if viewer().has(self.organization_id, userRights.organization_admin):
            return self.max_deposit
        return None

class Order(SQLAlchemyObjectType):
    class Meta:
        model = OrderModel
        interfaces = (relay.Node, )
        description = OrderModel.__doc__

    def resolve_users(self, info, **kwargs):
        v = viewer()
        if v.has(self.organization_id, userRights.inventory_admin):
            return list(self.users)
        return [
            u
            for u in self.users
            if v.user_id is not None and u.user_id == v.user_id
        ]

class User(SQLAlchemyObjectType):
    class Meta:
        model = UserModel
        exclude_fields = ('password_hash', 'reset_tokens', 'auth_epoch')
        interfaces = (relay.Node, )
        description = UserModel.__doc__

    email       = graphene.String()
    first_name  = graphene.String()
    last_name   = graphene.String()

    def _field(self, name, level):
        return (
            getattr(self, name)
            if user_level(viewer(), self) >= level
            else None
        )

    def resolve_email(self, info):
        return User._field(self, 'email', LEVEL_CONTACT)

    def resolve_first_name(self, info):
        return User._field(self, 'first_name', LEVEL_CONTACT)

    def resolve_last_name(self, info):
        return User._field(self, 'last_name', LEVEL_CONTACT)

    def resolve_phone_number(self, info):
        return User._field(self, 'phone_number', LEVEL_FULL)

    def resolve_matricle_number(self, info):
        return User._field(self, 'matricle_number', LEVEL_FULL)

    def resolve_country(self, info):
        return User._field(self, 'country', LEVEL_FULL)

    def resolve_postcode(self, info):
        return User._field(self, 'postcode', LEVEL_FULL)

    def resolve_city(self, info):
        return User._field(self, 'city', LEVEL_FULL)

    def resolve_street(self, info):
        return User._field(self, 'street', LEVEL_FULL)

    def resolve_house_number(self, info):
        return User._field(self, 'house_number', LEVEL_FULL)

    def resolve_orders(self, info, **kwargs):
        v = viewer()
        return [o for o in self.orders if order_visible(v, o)]

    def resolve_organizations(self, info, **kwargs):
        v = viewer()
        if v.user_id is None:
            return []
        if v.is_sa or v.user_id == self.user_id:
            return list(self.organizations)
        oa_orgs = v.orgs_with(userRights.organization_admin)
        return [m for m in self.organizations if m.organization_id in oa_orgs]

class Group(SQLAlchemyObjectType):
    class Meta:
        model = GroupModel
        interfaces = (relay.Node,)
        description = GroupModel.__doc__

class Organization_User(SQLAlchemyObjectType):
    class Meta:
        model = Organization_UserModel
        interfaces = (relay.Node,)
        description = Organization_UserModel.__doc__

class File(SQLAlchemyObjectType):
    class Meta:
        model = FileModel
        interfaces = (relay.Node,)
        description = FileModel.__doc__

class PhysicalObject_Order(SQLAlchemyObjectType):
    class Meta:
        model = PhysicalObject_OrderModel
        interfaces = (relay.Node,)
        description = PhysicalObject_OrderModel.__doc__

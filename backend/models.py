import enum
import uuid

import graphene
import json

from config import db, engine
from sqlalchemy import *
from sqlalchemy.orm import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator, VARCHAR, INTEGER

# standard, something for querying
Base = declarative_base()

USER_ID_FK = 'user.user_id'
Base.query = db.query_property()

class userRights(enum.Enum):
    """
    Enum for different rights a user can have inside his organization
    rights are organized in a hierarchy
    """
    system_admin        = 0 # kann Organisationen erstellen
    organization_admin  = 1 # dürfen innerhalb ihrer Organisation alles
    inventory_admin     = 2 # dürfen Objekte und Groups der eigenen Organisation verwalten und Tags
    member              = 3 # dürfen Order erstellen
    customer            = 4 # können nur bestellen, abholen, zurückgeben
    watcher             = 5 # können nur gucken

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented
    
    def __eq__(self, other):
        if self.__class__ is other.__class__:
            return self.value == other.value
        return NotImplemented
    
    def __hash__(self):
        return hash(self.name)

class orderStatus(enum.Enum):
    """
    Enum for the status of an order
    """
    pending  = 1
    reserved = 2
    accepted = 3
    picked   = 4
    rejected = 5
    returned = 6


# m:n Relations go here ...

physicalobject_tag = Table (
    'physicalobject_tag',
    Base.metadata,
    Column('phys_id',           ForeignKey('physicalobject.phys_id'),       primary_key=True),
    Column('tag_id',            ForeignKey('tag.tag_id'),                   primary_key=True),
    extend_existing = True
)

group_tag = Table (
    'group_tag',
    Base.metadata,
    Column('group_id',          ForeignKey('group.group_id'),                primary_key=True),
    Column('tag_id',            ForeignKey('tag.tag_id'),                    primary_key=True),
    extend_existing = True
)

user_order = Table (
    'user_order',
    Base.metadata,
    Column('user_id', ForeignKey(USER_ID_FK), primary_key=True),
    Column('order_id',          ForeignKey('order.order_id'),               primary_key=True),
    extend_existing = True,
)

group_physicalobject = Table (
    'group_physicalobject',
    Base.metadata,
    Column('group_id',          ForeignKey('group.group_id'),               primary_key=True),
    Column('phys_id',           ForeignKey('physicalobject.phys_id'),       primary_key=True),
    extend_existing = True,
)

physicalobject_organization = Table (
    'physicalobject_organization',
    Base.metadata,
    Column('phys_id',           ForeignKey('physicalobject.phys_id'),       primary_key=True),
    Column('organization_id',   ForeignKey('organization.organization_id'), primary_key=True),
    extend_existing = True,
)

class Organization_User(Base):
    """
    m:n relation between organization and user
    additionally holds the rights a user has in an organization
    """
    __tablename__       = "organization_user"
    organization_id     = Column(String(36),        ForeignKey('organization.organization_id'), primary_key=True)
    user_id = Column(String(36), ForeignKey(USER_ID_FK), primary_key=True)
    rights              = Column(Enum(userRights),  nullable = False, default = userRights.customer)
    # User want to see agb only after a change
    # Should be automatically false if agb changes (irgendwo in Mutations)
    agb_dont_show       = Column(Boolean,       nullable = False, default = False)

    organization        = relationship("Organization", back_populates = "users")
    user                = relationship("User", back_populates = "organizations")

    def __repr__(self):
        return "Organization ID: " + str(self.organization_id) + "; User ID: " + str(self.user_id) + "; Rights: " + str(self.rights)

class PhysicalObject_Order(Base):
    """
    m:n relation between physicalObject and order
    additionally holds the orderStatus a physicalobject has in an order
    """
    __tablename__       = "physicalobject_order"
    phys_id             = Column(String(36),            ForeignKey('physicalobject.phys_id'),   primary_key=True)
    order_id            = Column(String(36),            ForeignKey('order.order_id'),           primary_key=True)
    order_status        = Column(Enum(orderStatus),     nullable = False, default = 'pending')
    return_date         = Column(DateTime,              nullable = True)
    return_notes        = Column(String(600),           nullable = True)

    physicalobject      = relationship("PhysicalObject",    back_populates = "orders")
    order               = relationship("Order",             back_populates = "physicalobjects")

    def __repr__(self):
        return "Physical Object ID: " + str(self.phys_id) + "; Order ID: " + str(self.order_id) + "; Status: " + str(self.order_status) + "; Return Note: " + str(self.return_notes)


# Classes go here ...

class Tag(Base):
    """
    physical objects get tags attached to them for better filtering options
    """
    __tablename__       = "tag"
    tag_id              = Column(String(36),        primary_key = True, default=lambda: str(uuid.uuid4()))
    name                = Column(String(60),    unique = True, nullable = False)

    physicalobjects     = relationship("PhysicalObject", secondary = physicalobject_tag, back_populates = "tags")
    groups              = relationship("Group", secondary = group_tag, back_populates = "tags")

    def __repr__(self):
        return "Tag ID: " + str(self.tag_id) + "; Name: " + self.name

class PhysicalObject(Base):
    """
    Physical Objects are the real objects which get grouped later on for borrowing
    """
    __tablename__       = "physicalobject"
    phys_id             = Column(String(36),            unique = True,  primary_key = True, default=lambda: str(uuid.uuid4()))
    inv_num_internal    = Column(Integer,               unique = False, nullable = False) # unique?
    inv_num_external    = Column(Integer,               unique = False, nullable = False)
    deposit             = Column(Integer,               unique = False, nullable = False)
    storage_location    = Column(String(60),            unique = False, nullable = False)
    storage_location2   = Column(String(60),            unique = False, nullable = True)
    faults              = Column(String(600),           unique = False, nullable = True)
    name                = Column(String(60),            unique = False, nullable = False)
    description         = Column(String(600),           unique = False, nullable = True)
    borrowable          = Column(Boolean,               unique = False, nullable = False, default = True)
    lending_comment     = Column(String(600),           unique = False, nullable = True)
    return_comment      = Column(String(600),           unique = False, nullable = True)
    organization_id     = Column(String(36), ForeignKey('organization.organization_id'), nullable=False)

    organization        = relationship("Organization",                                              back_populates="physicalobjects")
    pictures            = relationship("File",          foreign_keys='File.picture_id',             back_populates = "physicalobject_picture")
    manual              = relationship("File",          foreign_keys='File.manual_id',              back_populates = "physicalobject_manual")
    tags                = relationship("Tag",           secondary = physicalobject_tag,             back_populates = "physicalobjects")
    orders              = relationship("PhysicalObject_Order",                                      back_populates = "physicalobject", cascade="all, delete-orphan")
    groups              = relationship("Group",         secondary = group_physicalobject,           back_populates = "physicalobjects")

    def __repr__(self):
        return "Physical Object ID: " + str(self.phys_id) + "; Name: " + self.name

class File(Base):
    """
    Stores the location of a file for pictures an pdf's to use in PhysicalObjects, groups and Organizations
    """
    class FileType(enum.Enum):
        """
        Enum for the type of the file
        """
        picture = 0
        pdf     = 1
        other   = 2

    __tablename__       = "file"
    file_id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    picture_id          = Column(String(36),       ForeignKey('physicalobject.phys_id'),        nullable = True)
    manual_id           = Column(String(36),       ForeignKey('physicalobject.phys_id'),        nullable = True)
    organization_id     = Column(String(36),       ForeignKey('organization.organization_id'),  nullable = True)
    group_id            = Column(String(36),       ForeignKey('group.group_id'),                nullable = True)
    # String name for the file location
    path                = Column(String(600),       unique = True, nullable = False)
    file_type           = Column(Enum(FileType),    nullable = False, default = 'other')
    show_index          = Column(Integer,           nullable = True)

    physicalobject_picture  = relationship("PhysicalObject",    back_populates = "pictures",    foreign_keys=[picture_id])
    physicalobject_manual   = relationship("PhysicalObject",    back_populates = "manual",      foreign_keys=[manual_id])
    group                   = relationship("Group",             back_populates = "pictures")
    organization            = relationship("Organization",      back_populates = "agb")

class Order(Base):
    """
    Orders are the actual borrowings of physical objects for a specific time
    """
    __tablename__       = "order"
    order_id            = Column(String(36),        primary_key = True, default=lambda: str(uuid.uuid4()))
    creation_date       = Column(DateTime,          unique = False, nullable = False)
    from_date           = Column(DateTime,          unique = False, nullable = False)
    till_date           = Column(DateTime,          unique = False, nullable = False)
    deposit             = Column(Float,             unique = False, nullable = True)
    organization_id     = Column(String(36),        ForeignKey('organization.organization_id'), nullable=False)

    physicalobjects     = relationship("PhysicalObject_Order",                                  back_populates = "order", cascade="all, delete-orphan")
    users               = relationship("User",              secondary = user_order,             back_populates = "orders")
    organization        = relationship("Organization",                                          back_populates = "orders")

    def addPhysicalObject(self, physicalobject, order_status = orderStatus.pending):
        """
        adds a physicalObject to the order
        """
        tmp = PhysicalObject_Order(order = self, physicalobject = physicalobject, order_status = order_status)
        self.physicalobjects.append(tmp)
        physicalobject.orders.append(tmp)

    def removePhysicalObject(self, physicalobject):
        """
        removes a physicalObject from the order
        """
        for physicalobject_order in self.physicalobjects:
            if physicalobject_order.physicalobject == physicalobject:
                db.delete(physicalobject_order)

    def removeAllPhysicalObjects(self):
        """
        removes all physicalObjects from the order
        """
        for physicalobject_order in self.physicalobjects:
            db.delete(physicalobject_order)

    def __repr__(self):
        return "Order ID: " + str(self.order_id) + "; From: " + str(self.from_date) + "; Till: " + str(self.till_date)

class User(Base):
    """
    Users can be in organizations but don't have to
    """
    __tablename__       = "user"

    user_id             = Column(String(36),    primary_key = True, default=lambda: str(uuid.uuid4()))
    first_name          = Column(String(30),    unique = False, nullable = False)
    last_name           = Column(String(30),    unique = False, nullable = False)

    email               = Column(String(60),    unique = True,  nullable = False)
    password_hash       = Column(String(120),   unique = False, nullable = False) # hashed

    country             = Column(String(60),    unique = False, nullable = True)
    postcode            = Column(Integer,       unique = False, nullable = True)
    city                = Column(String(60),    unique = False, nullable = True)
    street              = Column(String(60),    unique = False, nullable = True)
    house_number        = Column(String(10),    unique = False, nullable = True)

    phone_number        = Column(Integer, unique = True, nullable = True)
    matricle_number     = Column(Integer, unique = True, nullable = True)

    organizations       = relationship("Organization_User",                                back_populates = "user", cascade="all, delete-orphan")
    orders              = relationship("Order",             secondary = user_order,        back_populates = "users")
    reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    auth_epoch = relationship(
        "UserAuthEpoch",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return "User ID: " + str(self.user_id) + "; Name: " + self.first_name + " " + self.last_name

class PasswordResetToken(Base):
    """
    Single-use password reset token; only the sha256 hash of the token is stored
    """
    __tablename__       = "password_reset_token"
    token_hash          = Column(String(64),    primary_key = True)
    user_id = Column(
        String(36), ForeignKey(USER_ID_FK), nullable=False, index=True
    )
    expires_at          = Column(DateTime,      nullable = False)   # naive UTC

    user                = relationship("User", back_populates = "reset_tokens")

class UserAuthEpoch(Base):
    """
    Per-user counter; sessions carrying an older epoch are invalid
    (password change)
    """
    __tablename__       = "user_auth_epoch"
    user_id = Column(String(36), ForeignKey(USER_ID_FK), primary_key=True)
    epoch               = Column(Integer,       nullable = False, default = 0)

    user                = relationship("User", back_populates = "auth_epoch")

class Group(Base):
    """
    Group contains physical objects or groups
    Groups have to be borrowed as a whole
    """
    __tablename__       = "group"
    group_id            = Column(String(36),    primary_key = True, default=lambda: str(uuid.uuid4()))
    name                = Column(String(60),    unique = True, nullable = False)
    organization_id     = Column(String(36),    ForeignKey('organization.organization_id'), nullable=False)
    description         = Column(String(600),   unique = False, nullable = True)

    physicalobjects     = relationship("PhysicalObject", secondary = group_physicalobject, back_populates = "groups")
    pictures            = relationship("File",                                             back_populates = "group")
    organization        = relationship("Organization",                                     back_populates = "groups")
    tags                = relationship("Tag",           secondary = group_tag,             back_populates = "groups")

class Organization(Base):
    """
    Organization is a group of members
    equivalent to FARAS
    """
    __tablename__       = "organization"
    organization_id     = Column(String(36),    primary_key = True, default=lambda: str(uuid.uuid4()))
    name                = Column(String(60),    unique = True,  nullable = False)
    location            = Column(String(60),    unique = False, nullable = False)
    # String name for the agb file location
    agb                 = relationship("File",              back_populates = "organization", cascade="all, delete-orphan")
    # List for the max deposit for each user right
    max_deposit         = Column(String(120),    unique = False, nullable = False, 
                                 default = json.dumps(
                                     {
                                         userRights.customer.name: 0, 
                                         userRights.member.name: 0, 
                                         userRights.inventory_admin.name: 0, 
                                         userRights.organization_admin.name: 0, 
                                         userRights.system_admin.name: 0
                                    }))

    users               = relationship("Organization_User", back_populates = "organization", cascade="all, delete-orphan")
    physicalobjects     = relationship("PhysicalObject",    back_populates = "organization")
    groups              = relationship("Group",             back_populates = "organization")
    orders              = relationship("Order",             back_populates = "organization")

    def has_user(self, user_id):
        """
        checks if a user is in the organization
        """
        for user in self.users:
            if user.user_id == user_id:
                return True
        return False

    def add_user(self, user, rights = userRights.customer):
        """
        adds a user to the organization
        """
        tmp = Organization_User(organization = self, user = user, rights = rights)
        self.users.append(tmp)
        user.organizations.append(tmp)

    def remove_user(self, user):
        """
        removes a user from the organization
        """
        print(user)
        print(self.users)
        connection = None
        for orga_user in self.users:
            if orga_user.user_id == user.user_id:
                connection = orga_user
                break
        
        print(connection)
        self.users.remove(connection)
        user.organizations.remove(connection)

    def set_user_right(self, user_id, right):
        """
        sets the right of a user in the organization
        """
        for user in self.users:
            if user.user_id == user_id:
                user.rights = right
                return

    def reset_user_agreement(self):
        """
        resets the agb agreement for all users in the organization
        """
        for user in self.users:
            user.agb_dont_show = False

    def get_max_deposit(self, right):
        """
        returns the max deposit for a specific right
        """
        print(json.loads(self.max_deposit))
        return json.loads(self.max_deposit).get(right.name, 0)
    
    def set_max_deposit(self, right, deposit):
        """
        sets the max deposit for a specific right
        """
        tmp = json.loads(self.max_deposit)
        if right in tmp:
            tmp[right] = deposit
        else:
            raise KeyError(f"Invalid right: {right}")
        self.max_deposit = json.dumps(tmp)

    def get_user_right(self, user_id):
        """
        returns the right of a user in the organization
        """
        for user in self.users:
            if user.user_id == user_id:
                return user.rights
        return None

    def __repr__(self):
        return ("Organization ID: " + str(self.organization_id)
                + "; Name: " + self.name)

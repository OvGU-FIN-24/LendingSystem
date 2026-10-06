"""
Central authorization module.

All authorization decisions live here. Guards raise AuthzError subclasses and
never return False; mutations are wrapped with @guarded, which turns these
errors into the {ok, infoText, statusCode} payload contract.
"""
from dataclasses import dataclass, field
from functools import wraps
import logging
import sys
from uuid import uuid4

from flask import g, has_request_context, session
from graphql import GraphQLError

from config import db
from models import (userRights, orderStatus, User, UserAuthEpoch, Organization,
                    Organization_User, PhysicalObject, Group, Order, File, Tag)

log = logging.getLogger("lending")
if not log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

ROOT_ORGANIZATION = "root_organization"


##################################
# Errors (error contract)        #
##################################
class AuthzError(Exception):
    status = 500
    message = "Interner Fehler"

    def __init__(self, message=None):
        if message:
            self.message = message
        super().__init__(self.message)


class NotAuthenticated(AuthzError):
    status = 419
    message = "Keine valide session vorhanden"


class Forbidden(AuthzError):
    status = 403
    message = "Sie sind nicht autorisiert diese Aktion auszuführen"


class InvalidInput(AuthzError):
    status = 400
    message = "Ungültige Eingabe"


class NotFound(AuthzError):
    status = 404
    message = "Nicht gefunden"


class PublicError(GraphQLError):
    """Query-side error whose message may be shown to the client."""


NOT_LOGGED_IN = "Nicht angemeldet"
NOT_AUTHORIZED = "Nicht autorisiert"


##################################
# Viewer                         #
##################################
@dataclass(frozen=True)
class Viewer:
    user_id: object = None
    rights: dict = field(default_factory=dict)   # org_id -> userRights
    is_sa: bool = False

    def right_in(self, org_id):
        if self.is_sa:
            return userRights.system_admin
        return self.rights.get(org_id)

    def has(self, org_id, required):
        if self.is_sa:
            return True
        r = self.rights.get(org_id)
        return r is not None and r <= required

    def orgs_with(self, required):
        return {org_id for org_id in self.rights if self.has(org_id, required)}

    def is_staff_anywhere(self):
        return self.is_sa or bool(self.orgs_with(userRights.inventory_admin))


ANONYMOUS = Viewer()


def _current_epoch(user_id):
    row = db.query(UserAuthEpoch).get(user_id)
    return row.epoch if row else 0


def is_global_sa(user_id):
    """Global system admin: system_admin membership in root_organization (only
    source)."""
    row = (
        db.query(Organization_User)
        .join(
            Organization,
            Organization.organization_id == Organization_User.organization_id,
        )
        .filter(
            Organization.name == ROOT_ORGANIZATION,
            Organization_User.user_id == user_id,
        )
        .first()
    )
    return row is not None and row.rights == userRights.system_admin


def _compute_viewer():
    user_id = session.get('user_id')
    if not user_id:
        return ANONYMOUS
    user = db.query(User).get(user_id)
    if user is None or session.get('auth_epoch', 0) != _current_epoch(user_id):
        session.clear()
        return ANONYMOUS
    rights = {
        ou.organization_id: ou.rights
        for ou in db.query(Organization_User).filter(
            Organization_User.user_id == user_id
        )
    }
    return Viewer(user_id=user_id, rights=rights, is_sa=is_global_sa(user_id))


def viewer():
    """Viewer of the current request, computed once and cached in flask.g."""
    if not has_request_context():
        return ANONYMOUS
    v = g.get('authz_viewer')
    if v is None:
        v = _compute_viewer()
        g.authz_viewer = v
    return v


def reset_viewer():
    """Drop the cached viewer (after login/logout/membership changes)."""
    if has_request_context():
        g.pop('authz_viewer', None)


def bump_auth_epoch(user_id):
    """Invalidate all sessions of the user. Does not commit; returns the new
    epoch."""
    row = db.query(UserAuthEpoch).get(user_id)
    if row is None:
        row = UserAuthEpoch(user_id=user_id, epoch=0)
        db.add(row)
    row.epoch = (row.epoch or 0) + 1
    db.flush()
    return row.epoch


##################################
# Guards                         #
##################################
def require_user():
    v = viewer()
    if v.user_id is None:
        raise NotAuthenticated()
    return v


def require_right(org_id, required):
    v = require_user()
    if not org_id or not v.has(org_id, required):
        raise Forbidden()
    return v


def require_sa():
    v = require_user()
    if not v.is_sa:
        raise Forbidden()
    return v


def require_staff_anywhere():
    v = require_user()
    if not v.is_staff_anywhere():
        raise Forbidden()
    return v


def query_viewer():
    """For query resolvers: anonymous callers get a public GraphQL error."""
    v = viewer()
    if v.user_id is None:
        raise PublicError(NOT_LOGGED_IN)
    return v


def _get_or_forbidden(model, ident):
    obj = db.query(model).get(ident) if ident else None
    if obj is None:
        # unknown entities are denied, never allowed (deny by default)
        raise Forbidden()
    return obj


def org_of_phys(phys_id):
    return _get_or_forbidden(PhysicalObject, phys_id).organization_id


def org_of_group(group_id):
    return _get_or_forbidden(Group, group_id).organization_id


def org_of_order(order_id):
    return _get_or_forbidden(Order, order_id).organization_id


def org_of_file(file):
    """Owning organisation of a file, or None if it is not attached yet."""
    for phys_id in (file.picture_id, file.manual_id):
        if phys_id:
            phys = db.query(PhysicalObject).get(phys_id)
            return phys.organization_id if phys else None
    if file.group_id:
        group = db.query(Group).get(file.group_id)
        return group.organization_id if group else None
    if file.organization_id:
        return file.organization_id
    return None


def is_agb_file(file):
    return bool(file.organization_id) and not (
        file.picture_id or file.manual_id or file.group_id
    )


def require_file_edit(file):
    """Attached: IA in the owning org (AGB: OA). Unattached: staff anywhere."""
    org_id = org_of_file(file)
    if org_id is None:
        return require_staff_anywhere()
    required = (
        userRights.organization_admin
        if is_agb_file(file)
        else userRights.inventory_admin
    )
    return require_right(org_id, required)


def orgs_of_tag(tag):
    return ({p.organization_id for p in tag.physicalobjects}
            | {gr.organization_id for gr in tag.groups})


def require_tag_edit(tag_id):
    """Empty tag: SA only. Otherwise IA+ in every org using the tag. Returns
    the tag."""
    v = require_user()
    tag = _get_or_forbidden(Tag, tag_id)
    orgs = orgs_of_tag(tag)
    if not orgs:
        if not v.is_sa:
            raise Forbidden()
    elif not all(v.has(o, userRights.inventory_admin) for o in orgs):
        raise Forbidden()
    return tag


def require_order_staff(order):
    return require_right(order.organization_id, userRights.inventory_admin)


def require_order_edit(order):
    """Staff (IA+) of the order org in any status, or a borrower while all
    positions are pending."""
    v = require_user()
    if v.has(order.organization_id, userRights.inventory_admin):
        return v
    is_borrower = any(u.user_id == v.user_id for u in order.users)
    all_pending = all(
        po.order_status == orderStatus.pending for po in order.physicalobjects
    )
    if is_borrower and all_pending:
        return v
    raise Forbidden()


def clean_ids(ids):
    """Id lists from the frontend may contain "" entries; they are ignored."""
    return [i for i in (ids or []) if i]


def require_linkable(model, ids, org_id):
    """Each referenced entity exists and belongs to org_id. Returns the
    entities."""
    objs = []
    for ident in clean_ids(ids):
        obj = _get_or_forbidden(model, ident)
        if obj.organization_id != org_id:
            raise Forbidden()
        objs.append(obj)
    return objs


def require_files_linkable(file_ids, org_id):
    """Each file is unattached or already belongs to org_id. Returns the
    files."""
    files = []
    for ident in clean_ids(file_ids):
        f = _get_or_forbidden(File, ident)
        owner = org_of_file(f)
        if owner is not None and owner != org_id:
            raise Forbidden()
        files.append(f)
    return files


def check_grant(v, org_id, target_user_id, new_right=None):
    """
    Bounds for granting rights:
    - system_admin is never grantable through the API (also not by SA)
    - SA may do everything else
    - OA of the org may grant up to organization_admin, but only to targets
      whose current right is strictly lower than their own, and never to a
      global SA
    """
    if new_right == userRights.system_admin:
        raise Forbidden()
    if v.is_sa:
        return
    caller_right = v.rights.get(org_id)
    if (
        caller_right is None
        or not caller_right <= userRights.organization_admin
    ):
        raise Forbidden()
    if new_right is not None and new_right < userRights.organization_admin:
        raise Forbidden()
    if is_global_sa(target_user_id):
        raise Forbidden()
    membership = db.query(Organization_User).get((org_id, target_user_id))
    if membership is not None and not membership.rights > caller_right:
        raise Forbidden()


def parse_right(s):
    try:
        return userRights[s.strip().lower()]
    except (KeyError, AttributeError):
        raise InvalidInput("Ungültiges Recht")


def parse_status(s):
    try:
        return orderStatus[s.strip().lower()]
    except (KeyError, AttributeError):
        raise InvalidInput("Ungültiger Status")


##################################
# Mutation wrapper               #
##################################
def guarded(mutate):
    """Maps AuthzError to the payload contract; masks all other exceptions."""
    @wraps(mutate)
    def wrapper(root, info, **kwargs):
        payload = info.return_type.graphene_type
        try:
            return mutate(root, info, **kwargs)
        except AuthzError as e:
            db.rollback()
            return payload(ok=False, info_text=e.message, status_code=e.status)
        except Exception:
            db.rollback()
            ref = uuid4().hex[:8]
            log.exception("mutation %s failed ref=%s", info.field_name, ref)
            return payload(
                ok=False,
                info_text=f"Interner Fehler (Ref: {ref})",
                status_code=500,
            )
    return wrapper


##################################
# Visibility (queries and types) #
##################################
def order_visible(v, order):
    """Borrowers see their own orders, staff (IA+) the orders of their
    organisation, SA all."""
    if v.user_id is None or order is None:
        return False
    if v.has(order.organization_id, userRights.inventory_admin):
        return True
    return any(u.user_id == v.user_id for u in order.users)


def visible_orders_clause(v):
    """SQL predicate on Order for the orders visible to v (None for SA = no
    restriction)."""
    if v.is_sa:
        return None
    from sqlalchemy import or_
    return or_(
        Order.users.any(User.user_id == v.user_id),
        Order.organization_id.in_(v.orgs_with(userRights.inventory_admin)),
    )


LEVEL_NONE, LEVEL_CONTACT, LEVEL_FULL = 0, 1, 2


def user_level(v, user):
    """How much of a user record v may see: full (self, SA, OA of a shared
    org), contact (staff), none."""
    if v.user_id is None or user is None:
        return LEVEL_NONE
    if v.is_sa or v.user_id == user.user_id:
        return LEVEL_FULL
    oa_orgs = v.orgs_with(userRights.organization_admin)
    if oa_orgs and any(
        m.organization_id in oa_orgs for m in user.organizations
    ):
        return LEVEL_FULL
    if v.is_staff_anywhere():
        return LEVEL_CONTACT
    return LEVEL_NONE

import datetime
import graphene

from authz import (guarded, require_user, require_order_edit, require_order_staff, parse_status,
                   clean_ids, reset_viewer, log, Forbidden, InvalidInput, NotFound)
from config import db, timezone
from models import userRights, orderStatus
from scheduler import AddJob, CancelJob, status_change
from schema import Order, OrderModel, OrganizationModel, Organization_UserModel, PhysicalObjectModel, PhysicalObject_Order, PhysicalObject_OrderModel, UserModel


def compute_deposit(organization, phys_objects, borrower_id):
    """Sum of the object deposits, capped by the organisation's limit for the borrower's right."""
    right = organization.get_user_right(borrower_id) or userRights.customer
    return min(sum(o.deposit or 0 for o in phys_objects), organization.get_max_deposit(right))


def _notify(func, *args):
    """Reminder and status mails must not fail the order change itself."""
    try:
        func(*args)
    except Exception:
        log.exception("scheduling order mail failed")


def _get_order(order_id):
    order = db.query(OrderModel).get(order_id) if order_id else None
    if order is None:
        # unknown orders are treated like foreign ones
        require_user()
        raise Forbidden()
    return order


def _recompute_deposit(order):
    borrower_id = order.users[0].user_id if order.users else None
    order.deposit = compute_deposit(order.organization,
                                    [po.physicalobject for po in order.physicalobjects], borrower_id)


##################################
# Mutations for orders           #
##################################
class create_order(graphene.Mutation):
    """
    Creates a new order with the given parameters.
    For Connections to users and physical objects use array of their String uuid
    """

    class Arguments:
        # order arguments
        from_date       = graphene.DateTime(required=True)
        till_date       = graphene.DateTime(required=True)
        deposit         = graphene.Int()

        # order connections
        physicalobjects = graphene.List(graphene.String, required=True)

    order       = graphene.Field(lambda: Order)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, from_date, till_date, physicalobjects, deposit=None):
        v = require_user()

        ids = clean_ids(physicalobjects)
        db_physicalobjects = db.query(PhysicalObjectModel).filter(PhysicalObjectModel.phys_id.in_(ids)).all() if ids else []
        if not db_physicalobjects or len(db_physicalobjects) != len(set(ids)):
            raise NotFound("Physical Objects not found.")

        # Check if all physical objects are from the same organization
        organization_id = db_physicalobjects[0].organization_id
        if len({phys_obj.organization_id for phys_obj in db_physicalobjects}) > 1:
            raise InvalidInput("Alle Objekte müssen der selben Organisation angehören.")
        organization = db.query(OrganizationModel).get(organization_id)
        executive_user = db.query(UserModel).get(v.user_id)

        # any university user may borrow: join the organisation as customer on the first order
        if v.right_in(organization_id) is None:
            db.add(Organization_UserModel(organization_id=organization_id, user_id=v.user_id,
                                          rights=userRights.customer))
            db.flush()
            db.refresh(organization)
            reset_viewer()

        order = OrderModel(
            creation_date=datetime.datetime.now(timezone),
            from_date=from_date,
            till_date=till_date,
            users=[executive_user],
            organization=organization
        )
        for physicalobject in db_physicalobjects:
            order.addPhysicalObject(physicalobject)

        # the client-supplied deposit is only honoured for staff of the organisation
        if deposit is not None and v.has(organization_id, userRights.inventory_admin):
            order.deposit = deposit
        else:
            order.deposit = compute_deposit(organization, db_physicalobjects, v.user_id)

        db.add(order)
        db.commit()

        # Add jobs for email reminders for this order
        _notify(AddJob, order.order_id)
        return create_order(ok=True, info_text="Order erfolgreich erstellt.", order=order, status_code=200)


class update_order(graphene.Mutation):
    """
    Updates content of the order with the given order_id.
    """

    class Arguments:
        # order arguments
        order_id    = graphene.String(required=True)
        from_date   = graphene.Date()
        till_date   = graphene.Date()
        deposit     = graphene.Int()

        # order connections
        users = graphene.List(graphene.String)

    order       = graphene.Field(lambda: Order)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, order_id, from_date=None, till_date=None, users=None, deposit=None):
        order = _get_order(order_id)
        require_order_edit(order)
        user_ids = clean_ids(users)
        if deposit is not None or user_ids:
            require_order_staff(order)

        db_users = []
        if user_ids:
            db_users = db.query(UserModel).filter(UserModel.user_id.in_(user_ids)).all()
            if len(db_users) != len(set(user_ids)):
                raise NotFound("Benutzer nicht gefunden.")

        # dates arrive as Date; stored as midnight DateTime (same as before on MySQL)
        if from_date:
            order.from_date = datetime.datetime.combine(from_date, datetime.time())
        if till_date:
            order.till_date = datetime.datetime.combine(till_date, datetime.time())
        if db_users:
            order.users = db_users
        if deposit is not None:
            order.deposit = deposit

        db.commit()

        # replace the email reminders for the modified order
        _notify(CancelJob, order_id)
        _notify(AddJob, order_id)
        _notify(status_change, order)

        return update_order(ok=True, info_text="OrderStatus aktualisiert.", order=order, status_code=200)


class update_order_status(graphene.Mutation):
    """
    Updates the status for the given physical objects in the order.
    """

    class Arguments:
        order_id            = graphene.String(required=True)
        physical_objects    = graphene.List(graphene.String, required=True)

        return_date     = graphene.Date()
        status          = graphene.String()
        return_notes    = graphene.String()

    phys_order  = graphene.List(lambda: PhysicalObject_Order)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, order_id, physical_objects, return_date=None, status=None, return_notes=None):
        order = _get_order(order_id)
        require_order_staff(order)
        new_status = parse_status(status) if status else None

        phys_order = db.query(PhysicalObject_OrderModel).filter(
            PhysicalObject_OrderModel.order_id == order_id,
            PhysicalObject_OrderModel.phys_id.in_(clean_ids(physical_objects))).all()
        if len(phys_order) == 0:
            raise NotFound("Order nicht gefunden.")

        for position in phys_order:
            if return_date:
                position.return_date = return_date
            if new_status:
                position.order_status = new_status
            if return_notes:
                position.return_notes = return_notes

        db.commit()
        _notify(status_change, order)
        return update_order_status(ok=True, info_text="OrderStatus aktualisiert.", phys_order=phys_order, status_code=200)


class add_physical_object_to_order(graphene.Mutation):
    """
    Adds the given list of physical objects to the order with the given order_id.
    Use List of string uuids for physical objects.
    """

    class Arguments:
        order_id        = graphene.String(required=True)
        physicalObjects = graphene.List(graphene.String, required=True)

    phys_order  = graphene.List(lambda: PhysicalObject_Order)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, order_id, physicalObjects):
        order = _get_order(order_id)
        require_order_edit(order)

        ids = clean_ids(physicalObjects)
        db_physicalobjects = db.query(PhysicalObjectModel).filter(PhysicalObjectModel.phys_id.in_(ids)).all() if ids else []
        if not db_physicalobjects or len(db_physicalobjects) != len(set(ids)):
            raise NotFound("Physical Objects not found.")
        for phys_obj in db_physicalobjects:
            if phys_obj.organization_id != order.organization_id:
                raise InvalidInput("Physical Objects not in the same organization as the order.")

        already = {po.phys_id for po in order.physicalobjects}
        for phys_obj in db_physicalobjects:
            if phys_obj.phys_id not in already:
                order.addPhysicalObject(phys_obj)

        db.flush()
        _recompute_deposit(order)
        db.commit()
        _notify(status_change, order)
        return add_physical_object_to_order(ok=True, info_text="Physical Objects added to Order.", phys_order=order.physicalobjects, status_code=200)


class remove_physical_object_from_order(graphene.Mutation):
    """
    Removes the given list of physical objects from the order with the given order_id.
    Use List of string uuids for physical objects.
    """

    class Arguments:
        order_id        = graphene.String(required=True)
        physicalObjects = graphene.List(graphene.String, required=True)

    phys_order  = graphene.List(lambda: PhysicalObject_Order)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, order_id, physicalObjects):
        order = _get_order(order_id)
        require_order_edit(order)

        ids = set(clean_ids(physicalObjects))
        for position in list(order.physicalobjects):
            if position.phys_id in ids:
                order.physicalobjects.remove(position)

        db.flush()
        _recompute_deposit(order)
        db.commit()
        _notify(status_change, order)
        return remove_physical_object_from_order(ok=True, info_text="Physical Objects removed from Order.",
                                                 phys_order=order.physicalobjects, status_code=200)


class delete_order(graphene.Mutation):
    """
    Deletes the order with the given order_id.
    """

    class Arguments:
        order_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, order_id):
        order = _get_order(order_id)
        require_order_edit(order)

        order.removeAllPhysicalObjects()
        db.delete(order)
        db.commit()

        # remove email reminders for deleted order
        _notify(CancelJob, order_id)
        return delete_order(ok=True, info_text="Order erfolgreich entfernt.", status_code=200)

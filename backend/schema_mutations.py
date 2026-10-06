import graphene

import sys
sys.path.append("./mutations")
from mutation_files import upload_file, update_file, delete_file
from mutation_group import create_group, update_group, delete_group
from mutation_login import login, logout, check_session
from mutation_orders import create_order, update_order, update_order_status, add_physical_object_to_order, remove_physical_object_from_order, delete_order
from mutation_organizations import create_organization, update_organization, delete_organization, add_user_to_organization, remove_user_from_organization, get_max_deposit, set_max_deposit, update_user_rights
from mutation_physical_objects import create_physical_object, update_physical_object, delete_physical_object, is_physical_object_available
from mutation_tags import create_tag, update_tag, delete_tag
from mutation_users import create_user, update_user, delete_user
from mutation_password_reset import (
    request_password_reset,
    confirm_password_reset,
)

class Mutations(graphene.ObjectType):
    login = login.Field()
    logout = logout.Field()
    checkSession = check_session.Field()

    create_physical_object = create_physical_object.Field()
    update_physical_object = update_physical_object.Field()
    delete_physical_object = delete_physical_object.Field()
    is_physical_object_available = is_physical_object_available.Field()

    upload_file = upload_file.Field()
    update_file = update_file.Field()
    delete_file = delete_file.Field()

    create_order                        = create_order.Field()
    update_order                        = update_order.Field()
    update_order_status                 = update_order_status.Field()
    add_physical_object_to_order        = add_physical_object_to_order.Field()
    remove_physical_object_from_order   = remove_physical_object_from_order.Field()
    delete_order                        = delete_order.Field()

    create_tag = create_tag.Field()
    update_tag = update_tag.Field()
    delete_tag = delete_tag.Field()

    create_group = create_group.Field()
    update_group = update_group.Field()
    delete_group = delete_group.Field()

    create_organization             = create_organization.Field()
    update_organization             = update_organization.Field()
    delete_organization             = delete_organization.Field()
    add_user_to_organization        = add_user_to_organization.Field()
    remove_user_from_organization   = remove_user_from_organization.Field()
    get_max_deposit                 = get_max_deposit.Field()
    set_max_deposit                 = set_max_deposit.Field()
    update_user_rights              = update_user_rights.Field()

    create_user     = create_user.Field()
    update_user     = update_user.Field()
    delete_user     = delete_user.Field()

    request_password_reset  = request_password_reset.Field()
    confirm_password_reset  = confirm_password_reset.Field()

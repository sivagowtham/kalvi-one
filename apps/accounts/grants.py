from .permissions import register
from .roles import Role

register("accounts.view_user", [Role.PRINCIPAL, Role.HOD, Role.OFFICE], "See user accounts")
register("accounts.add_user", [Role.PRINCIPAL, Role.OFFICE], "Create user accounts")
register("accounts.change_user", [Role.PRINCIPAL, Role.OFFICE], "Edit user accounts")
register("accounts.view_roleassignment", [Role.PRINCIPAL, Role.OFFICE], "See role assignments")
register("accounts.add_roleassignment", [Role.PRINCIPAL], "Give a user a role")
register("accounts.change_roleassignment", [Role.PRINCIPAL], "Change a role assignment")
register("accounts.delete_roleassignment", [Role.PRINCIPAL], "Take a role away")

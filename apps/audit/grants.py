from apps.accounts.permissions import register
from apps.accounts.roles import Role

register("audit.view_auditevent", [Role.PRINCIPAL], "Read the college's audit log")

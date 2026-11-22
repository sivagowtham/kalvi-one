from apps.accounts.permissions import register
from apps.accounts.roles import Role

CLERKS = [Role.PRINCIPAL, Role.OFFICE]

register("admissions.view_intake", [*CLERKS, Role.HOD], "See seats per quota")
for action in ["add", "change", "delete"]:
    register(f"admissions.{action}_intake", [Role.PRINCIPAL], f"{action} seats per quota")

register(
    "admissions.view_application",
    [*CLERKS, Role.HOD, Role.ACCOUNTS],
    "See applications (without sensitive fields)",
)
register("admissions.add_application", CLERKS, "Enter applications")
register("admissions.change_application", CLERKS, "Edit applications and change their status")
register("admissions.enrol_application", CLERKS, "Enrol a confirmed application as a student")
register(
    "admissions.view_merit_list",
    [*CLERKS, Role.HOD],
    "See and download rank lists",
)
# No delete: applications are rejected or withdrawn instead.

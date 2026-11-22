from apps.accounts.permissions import register
from apps.accounts.roles import Role

READERS = [Role.PRINCIPAL, Role.HOD, Role.FACULTY, Role.OFFICE, Role.EXAM_CELL]

for model in ["department", "programme", "course", "academicyear", "semester"]:
    register(f"academics.view_{model}", READERS, f"See {model} records")

# College-wide structure: principal only.
for model in ["academicyear", "semester"]:
    for action in ["add", "change", "delete"]:
        register(f"academics.{action}_{model}", [Role.PRINCIPAL], f"{action} {model}")
register("academics.add_department", [Role.PRINCIPAL], "Create departments")
register("academics.delete_department", [Role.PRINCIPAL], "Delete departments")
register("academics.add_programme", [Role.PRINCIPAL], "Create programmes")
register("academics.delete_programme", [Role.PRINCIPAL], "Delete programmes")

# Department-level: HODs may act, but only inside their own department (D14).
register(
    "academics.change_department",
    [Role.PRINCIPAL, Role.HOD],
    "Edit a department",
    department_scoped=True,
)
register(
    "academics.change_programme",
    [Role.PRINCIPAL, Role.HOD],
    "Edit a programme",
    department_scoped=True,
)
for action in ["add", "change", "delete"]:
    register(
        f"academics.{action}_course",
        [Role.PRINCIPAL, Role.HOD],
        f"{action} courses",
        department_scoped=True,
    )

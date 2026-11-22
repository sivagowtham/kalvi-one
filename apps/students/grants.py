from apps.accounts.permissions import register
from apps.accounts.roles import Role

READERS = [
    Role.PRINCIPAL,
    Role.HOD,
    Role.FACULTY,
    Role.OFFICE,
    Role.EXAM_CELL,
    Role.ACCOUNTS,
]

for model in ["batch", "section"]:
    register(f"students.view_{model}", READERS, f"See {model} records")
    # HODs act only inside their own department (D14). Office staff set up sections
    # when they enrol students, so they share add and change, college-wide.
    for action in ["add", "change"]:
        register(
            f"students.{action}_{model}",
            [Role.PRINCIPAL, Role.HOD, Role.OFFICE],
            f"{action} {model}",
            department_scoped=True,
        )
    register(f"students.delete_{model}", [Role.PRINCIPAL], f"Delete an empty {model}")

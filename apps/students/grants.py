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

STAFF_READERS = READERS
CLERKS = [Role.PRINCIPAL, Role.OFFICE]

register("students.view_student", STAFF_READERS, "See student records (without sensitive fields)")
register("students.add_student", CLERKS, "Add students")
# The exam cell edits only register numbers; the admin makes every other field read-only
# for users without students.edit_student_details.
register("students.change_student", [*CLERKS, Role.EXAM_CELL], "Change students")
register("students.edit_student_details", CLERKS, "Change any field of a student record")
register(
    "students.view_sensitive",
    CLERKS,
    "See community, caste, guardians and income, and reveal Aadhaar (D18, D19)",
)
for model in ["guardian", "consent"]:
    for action in ["view", "add", "change"]:
        register(f"students.{action}_{model}", CLERKS, f"{action} {model} records")
# No delete permissions for students, guardians or consent: records change status instead.

register("students.view_studentsemester", STAFF_READERS, "See which section and semester")
for action in ["add", "change"]:
    register(
        f"students.{action}_studentsemester",
        [Role.PRINCIPAL, Role.HOD, Role.OFFICE],
        f"{action} a student's section and semester for a term",
        department_scoped=True,
    )
register(
    "students.promote_batch",
    [Role.PRINCIPAL, Role.HOD, Role.OFFICE],
    "Promote a batch to the next term",
    department_scoped=True,
)

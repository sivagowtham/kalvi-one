from apps.accounts.permissions import register
from apps.accounts.roles import Role

# The exam cell and the principal set up assessment schemes and grade scales (D51). Everyone
# who teaches or answers questions about marks can read them.
SETUP = [Role.PRINCIPAL, Role.EXAM_CELL]
READERS = [*SETUP, Role.HOD, Role.FACULTY, Role.OFFICE]

for model, label in [
    ("gradescale", "grade scales"),
    ("gradeband", "grade bands"),
    ("assessmentscheme", "assessment schemes"),
    ("schemecomponent", "assessment scheme components"),
]:
    register(f"exams.view_{model}", READERS, f"See {label}")
    register(f"exams.add_{model}", SETUP, f"Add {label}")
    register(f"exams.change_{model}", SETUP, f"Change {label} that are not yet in use")
    # Protected foreign keys and the lock stop anything that is in use from being deleted.
    register(f"exams.delete_{model}", SETUP, f"Delete unused {label}")

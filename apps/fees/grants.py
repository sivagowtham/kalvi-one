from apps.accounts.permissions import register
from apps.accounts.roles import Role

# The accounts office sets up fees and the principal oversees them (D26). Office staff and
# HODs can see the set-up, so they can answer questions from students and parents.
SETUP = [Role.PRINCIPAL, Role.ACCOUNTS]
READERS = [*SETUP, Role.OFFICE, Role.HOD]

for model, label in [
    ("feehead", "fee heads"),
    ("paymentaccount", "payment accounts"),
    ("feestructure", "fee structures"),
    ("instalment", "fee instalments"),
    ("feestructureline", "fee structure amounts"),
]:
    register(f"fees.view_{model}", READERS, f"See {label}")
    register(f"fees.add_{model}", SETUP, f"Add {label}")
    register(f"fees.change_{model}", SETUP, f"Change {label}")
    # Protected foreign keys stop anything that is in use from being deleted.
    register(f"fees.delete_{model}", SETUP, f"Delete unused {label}")

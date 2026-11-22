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

# Concessions: the accounts office and office staff enter them; only the principal decides.
register("fees.view_concession", READERS, "See concessions and scholarships")
for action in ["add", "change"]:
    register(
        f"fees.{action}_concession",
        [*SETUP, Role.OFFICE],
        f"{action} concessions waiting for approval",
    )
register("fees.approve_concession", [Role.PRINCIPAL], "Approve, reject or withdraw concessions")
# No delete: a concession is rejected or withdrawn instead, so the decision stays on record.

register("fees.view_studentdue", READERS, "See student dues")
register("fees.raise_dues", SETUP, "Raise a batch's dues from its fee structure")
# Dues are never added, changed or deleted by hand: they come from the structure, concessions
# and receipts.

# Receipts (D29): the accounts office takes payments; only the principal cancels.
register("fees.view_receipt", READERS, "See and print fee receipts")
register("fees.collect", SETUP, "Take fee payments and issue receipts")
register("fees.cancel_receipt", [Role.PRINCIPAL], "Cancel a fee receipt")
register("fees.view_receiptline", READERS, "See the fee heads a receipt paid")

# Reports (D30): everyone who can see dues can see the reports and download them.
register("fees.view_reports", READERS, "See and download dues and collection reports")

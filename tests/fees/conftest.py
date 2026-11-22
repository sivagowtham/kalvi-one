import datetime as dt
from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.fees.models import FeeHead, FeeStructure, FeeStructureLine, Instalment, PaymentAccount
from apps.tenancy.context import college_context
from tests.students.conftest import build_batches


def build_fees(college, prefix=""):
    """The students' core plus fee heads, payment accounts and one structure (D10: fake)."""
    core = build_batches(college, prefix)
    with college_context(college):
        core["tuition"] = FeeHead.objects.create(
            code="TUITION", name="Tuition fee", tally_ledger="Tuition Fees", sort_order=1
        )
        core["exam"] = FeeHead.objects.create(
            code="EXAM", name="Exam fee", tally_ledger="Exam Fees", sort_order=2
        )
        core["cash"] = PaymentAccount.objects.create(
            name="Cash counter", kind="cash", tally_ledger="Cash"
        )
        core["bank"] = PaymentAccount.objects.create(
            name="Fake Bank current account", kind="bank", tally_ledger="Fake Bank A/c"
        )
        structure = FeeStructure.objects.create(
            batch=core["be_cse_batch"], academic_year=core["year"]
        )
        Instalment.objects.create(
            structure=structure, number=1, label="Semester 1", due_date=dt.date(2026, 7, 15)
        )
        Instalment.objects.create(
            structure=structure, number=2, label="Semester 2", due_date=dt.date(2026, 12, 15)
        )
        for number in (1, 2):
            FeeStructureLine.objects.create(
                structure=structure,
                instalment_number=number,
                head=core["tuition"],
                amount=Decimal("25000"),
            )
        FeeStructureLine.objects.create(
            structure=structure, instalment_number=1, head=core["exam"], amount=Decimal("1500")
        )
        core["structure"] = structure
    return core


@pytest.fixture
def core_a(college_a):
    return build_fees(college_a, "Alpha ")


@pytest.fixture
def core_b(college_b):
    return build_fees(college_b, "Beta ")


@pytest.fixture
def accountant(college_a, make_user):
    return make_user(college_a, "accounts", roles=[Role.ACCOUNTS])


@pytest.fixture
def office(college_a, make_user):
    return make_user(college_a, "office", roles=[Role.OFFICE])

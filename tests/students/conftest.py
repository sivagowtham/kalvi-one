import pytest

from apps.students.models import Batch, Section
from apps.tenancy.context import college_context
from tests.academics.conftest import build_core


def build_batches(college, prefix=""):
    """The academic core plus one 2026 batch per programme, each with sections A and B."""
    core = build_core(college, prefix)
    with college_context(college):
        for key in ["be_cse", "be_ece"]:
            batch = Batch.objects.create(programme=core[key], admission_year=core["year"])
            core[f"{key}_batch"] = batch
            core[f"{key}_a"] = Section.objects.create(batch=batch, name="A", capacity=60)
            core[f"{key}_b"] = Section.objects.create(batch=batch, name="B")
    return core


@pytest.fixture
def core_a(college_a):
    return build_batches(college_a, "Alpha ")


@pytest.fixture
def core_b(college_b):
    return build_batches(college_b, "Beta ")


@pytest.fixture
def make_student():
    """make_student(core, "26CSE001", batch_key="be_cse_batch", **fields)"""
    from apps.students.models import Student

    def _make(core, roll, *, batch_key="be_cse_batch", **fields):
        batch = core[batch_key]
        defaults = {
            "admission_number": f"ADM{roll}",
            "name": f"Student {roll}",
            "gender": "female",
            "community": "BC",
            "quota": "GOVT",
        }
        with college_context(batch.college):
            return Student.objects.create(batch=batch, roll_number=roll, **(defaults | fields))

    return _make

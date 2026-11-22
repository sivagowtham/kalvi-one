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

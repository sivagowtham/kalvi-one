"""Number patterns (D20, D21)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.students import numbering
from apps.students.models import NumberCounter
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db


def test_default_roll_number_pattern_counts_per_prefix(college_a, core_a):
    with college_context(college_a):
        assert numbering.roll_number(core_a["be_cse_batch"]) == "26CSE001"
        assert numbering.roll_number(core_a["be_cse_batch"]) == "26CSE002"
        assert numbering.roll_number(core_a["be_ece_batch"]) == "26ECE001"
        assert NumberCounter.objects.count() == 2
        assert str(NumberCounter.objects.first()).endswith(": 2")


def test_custom_pattern_with_programme_and_suffix(college_a, core_a):
    college_a.config = {"students": {"roll_number_pattern": "{prog}/{yy}/{seq:02}X"}}
    college_a.save()
    batch = core_a["be_cse_batch"]
    batch.college.refresh_from_db()
    with college_context(college_a):
        assert numbering.roll_number(batch) == "BECSE/26/01X"


@pytest.mark.parametrize("pattern", ["{yy}{dept}", "{yy}{nope}{seq}"])
def test_bad_patterns_fail_loudly(college_a, core_a, pattern):
    college_a.config = {"students": {"roll_number_pattern": pattern}}
    college_a.save()
    batch = core_a["be_cse_batch"]
    batch.college.refresh_from_db()
    with college_context(college_a), pytest.raises(ImproperlyConfigured):
        numbering.roll_number(batch)


def test_counters_are_isolated(college_a, college_b, core_a, core_b):
    with college_context(college_a):
        numbering.roll_number(core_a["be_cse_batch"])
    with college_context(college_b):
        assert numbering.roll_number(core_b["be_cse_batch"]) == "26CSE001"

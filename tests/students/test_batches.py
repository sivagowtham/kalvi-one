"""Batches and sections: isolation, defaults and constraints (D4, D12, D17)."""

import datetime as dt

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction

from apps.academics.models import AcademicYear
from apps.audit.models import AuditEvent
from apps.students.models import Batch, Section
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", [Batch, Section])
def test_each_model_is_isolated_per_college(model, college_a, college_b, core_a, core_b):
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids
    assert a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_label_and_regulation_default_from_programme(core_a):
    batch = core_a["be_cse_batch"]
    assert batch.label == "2026-2030"
    assert batch.regulation == "R2021"
    assert str(batch) == "BE-CSE 2026-2030"
    assert str(core_a["be_cse_a"]) == "BE-CSE 2026-2030 A"


def test_explicit_label_and_regulation_are_kept(college_a, core_a):
    with college_context(college_a):
        year = AcademicYear.objects.create(
            label="2027-28", start_date=dt.date(2027, 6, 1), end_date=dt.date(2028, 5, 31)
        )
        batch = Batch.objects.create(
            programme=core_a["be_cse"], admission_year=year, label="27 batch", regulation="R2025"
        )
    assert (batch.label, batch.regulation) == ("27 batch", "R2025")


def test_one_batch_per_programme_per_year(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        Batch.objects.create(programme=core_a["be_cse"], admission_year=core_a["year"])


def test_section_names_are_unique_within_a_batch(college_a, core_a):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            Section.objects.create(batch=core_a["be_cse_batch"], name="A")
        Section.objects.create(batch=core_a["be_ece_batch"], name="C")


def test_section_capacity_must_be_positive(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        Section.objects.create(batch=core_a["be_cse_batch"], name="Z", capacity=0)


def test_batch_cannot_use_another_colleges_programme(college_a, core_a, core_b):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Batch.objects.create(programme=core_b["be_cse"], admission_year=core_a["year"])


def test_section_cannot_join_another_colleges_batch(college_a, core_b):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Section.objects.create(batch=core_b["be_cse_batch"], name="X")


def test_department_scope(core_a):
    cse = core_a["cse"].pk
    assert core_a["be_cse_batch"].scope_department_id == cse
    assert core_a["be_cse_a"].scope_department_id == cse
    assert Batch().scope_department_id is None
    assert Section().scope_department_id is None


def test_changes_are_audited(college_a, core_a):
    section = core_a["be_cse_a"]
    with college_context(college_a):
        section.capacity = 66
        section.save()
        event = AuditEvent.objects.filter(
            content_type=ContentType.objects.get_for_model(Section), object_id=str(section.pk)
        ).first()
        batches = AuditEvent.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch), action="create"
        )
        assert batches.count() == 2
    assert event.action == "update"
    assert event.changes == {"capacity": [60, 66]}

"""Fee heads, payment accounts and fee structures (D4, D12, D27)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academics.models import AcademicYear
from apps.audit.models import AuditEvent
from apps.fees.models import FeeHead, FeeStructure, FeeStructureLine, Instalment, PaymentAccount
from apps.tenancy.context import CrossCollegeError, NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db

MODELS = [FeeHead, PaymentAccount, FeeStructure, Instalment, FeeStructureLine]


@pytest.mark.parametrize("model", MODELS)
def test_each_model_is_isolated_per_college(model, college_a, college_b, core_a, core_b):
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids
    assert a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_a_structure_cannot_use_another_colleges_fee_head(college_a, core_a, core_b):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        FeeStructureLine.objects.create(
            structure=core_a["structure"], head=core_b["tuition"], amount=Decimal("1")
        )


def test_fee_head_codes_are_unique_and_well_formed(college_a, core_a):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            FeeHead.objects.create(code="TUITION", name="Again", tally_ledger="X")
        head = FeeHead(code="tuition fee", name="Bad", tally_ledger="X")
        with pytest.raises(ValidationError) as error:
            head.full_clean()
    assert "code" in error.value.message_dict


def test_gst_rate_is_bounded_and_taxable_heads_need_a_code(college_a, core_a):
    with college_context(college_a):
        with transaction.atomic(), pytest.raises(IntegrityError):
            FeeHead.objects.create(code="BAD", name="Bad", tally_ledger="X", gst_rate=50)
        books = FeeHead(code="BOOKS", name="Books", tally_ledger="Book Sales", gst_rate=5)
        with pytest.raises(ValidationError) as error:
            books.full_clean()
        assert "hsn_sac" in error.value.message_dict
        books.hsn_sac = "4901"
        books.full_clean()
        books.save()
    assert books.is_taxable and not core_a["tuition"].is_taxable


def test_structure_year_of_study_and_total(college_a, core_a):
    structure = core_a["structure"]
    assert structure.year_of_study == 1
    with college_context(college_a):
        assert structure.total() == Decimal("51500")
    assert str(structure) == "BE-CSE 2026-2030 year 1 2026-27"


def test_structure_must_fall_inside_the_batch(college_a, core_a):
    with college_context(college_a):
        before = AcademicYear.objects.create(
            label="2025-26", start_date=dt.date(2025, 6, 1), end_date=dt.date(2026, 5, 31)
        )
        late = AcademicYear.objects.create(
            label="2030-31", start_date=dt.date(2030, 6, 1), end_date=dt.date(2031, 5, 31)
        )
        last = AcademicYear.objects.create(
            label="2029-30", start_date=dt.date(2029, 6, 1), end_date=dt.date(2030, 5, 31)
        )
        for year in (before, late):
            with pytest.raises(ValidationError) as error:
                FeeStructure.objects.create(batch=core_a["be_ece_batch"], academic_year=year)
            assert "academic_year" in error.value.message_dict
        fourth = FeeStructure.objects.create(batch=core_a["be_ece_batch"], academic_year=last)
    assert fourth.year_of_study == 4


def test_structure_quota_must_be_one_the_college_uses(college_a, core_a):
    with college_context(college_a):
        with pytest.raises(ValidationError) as error:
            FeeStructure.objects.create(
                batch=core_a["be_cse_batch"], academic_year=core_a["year"], quota="NRI"
            )
        assert "quota" in error.value.message_dict
        management = FeeStructure.objects.create(
            batch=core_a["be_cse_batch"],
            academic_year=core_a["year"],
            quota="MGMT",
            residence="hostel",
        )
    assert management.specificity() == 2
    assert core_a["structure"].specificity() == 0
    assert str(management).endswith("MGMT Hostel")


def test_one_structure_per_batch_year_quota_and_residence(college_a, core_a):
    with college_context(college_a), pytest.raises(IntegrityError):
        FeeStructure.objects.create(batch=core_a["be_cse_batch"], academic_year=core_a["year"])


def test_line_needs_its_instalment_and_a_positive_amount(college_a, core_a):
    structure = core_a["structure"]
    with college_context(college_a):
        with pytest.raises(ValidationError):
            FeeStructureLine.objects.create(
                structure=structure, instalment_number=3, head=core_a["exam"], amount=1
            )
        with transaction.atomic(), pytest.raises(IntegrityError):
            FeeStructureLine.objects.create(
                structure=structure, instalment_number=2, head=core_a["exam"], amount=0
            )
        with transaction.atomic(), pytest.raises(IntegrityError):
            FeeStructureLine.objects.create(
                structure=structure, instalment_number=1, head=core_a["exam"], amount=5
            )


def test_heads_in_use_cannot_be_deleted(college_a, core_a):
    from django.db.models import ProtectedError

    with college_context(college_a), pytest.raises(ProtectedError):
        core_a["tuition"].delete()


def test_changes_are_audited(college_a, core_a):
    head = core_a["tuition"]
    with college_context(college_a):
        head.tally_ledger = "Tuition Fee Income"
        head.save()
        events = AuditEvent.objects.filter(
            content_type=ContentType.objects.get_for_model(FeeHead), object_id=str(head.pk)
        )
        assert events.filter(action="update").exists()

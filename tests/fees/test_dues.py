"""Raising dues from fee structures and applying concessions (D28)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.fees import dues
from apps.fees.models import (
    Concession,
    FeeStructure,
    FeeStructureLine,
    Instalment,
    StudentDue,
)
from apps.tenancy.context import NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db


def concession(core, student, **fields):
    defaults = {"academic_year": core["year"], "kind": "MERIT", "reason": "Fake order 1"}
    with college_context(student.college):
        return Concession.objects.create(student=student, **(defaults | fields))


def due_rows(student):
    with college_context(student.college):
        return [
            (d.instalment_number, d.head.code, d.amount, d.waived, d.govt_share)
            for d in StudentDue.objects.filter(student=student).order_by(
                "instalment_number", "head__sort_order"
            )
        ]


@pytest.mark.parametrize("model", [Concession, StudentDue])
def test_each_model_is_isolated_per_college(
    model, college_a, college_b, core_a, core_b, make_student
):
    for core in (core_a, core_b):
        student = make_student(core, "26CSE001")
        concession(core, student, percent=10)
        with college_context(student.college):
            dues.raise_dues(core["be_cse_batch"], core["year"])
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


def test_raise_dues_creates_one_row_per_head_and_instalment(college_a, core_a, make_student):
    first = make_student(core_a, "26CSE001")
    make_student(core_a, "26CSE002")
    make_student(core_a, "26CSE003", status="discontinued")
    with college_context(college_a):
        result = dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        again = dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        due = StudentDue.objects.filter(student=first).first()
    assert (result.created, result.students, result.skipped) == (6, 2, [])
    assert (again.created, again.students) == (0, 0)
    assert due_rows(first) == [
        (1, "TUITION", Decimal("25000"), 0, 0),
        (1, "EXAM", Decimal("1500"), 0, 0),
        (2, "TUITION", Decimal("25000"), 0, 0),
    ]
    assert (due.instalment_label, due.due_date) == ("Semester 1", dt.date(2026, 7, 15))
    assert due.balance == Decimal("25000")


def test_most_specific_structure_wins_and_misses_are_reported(college_a, core_a, make_student):
    general = make_student(core_a, "26CSE001")
    management = make_student(core_a, "26CSE002", quota="MGMT", residence="hostel")
    with college_context(college_a):
        for quota, residence, amount in [("MGMT", "", "60000"), ("", "hostel", "40000")]:
            structure = FeeStructure.objects.create(
                batch=core_a["be_cse_batch"],
                academic_year=core_a["year"],
                quota=quota,
                residence=residence,
            )
            Instalment.objects.create(
                structure=structure, number=1, label="Year", due_date=dt.date(2026, 7, 1)
            )
            FeeStructureLine.objects.create(
                structure=structure, head=core_a["tuition"], amount=Decimal(amount)
            )
        assert dues.structure_for(general, core_a["year"]) == core_a["structure"]
        assert dues.structure_for(management, core_a["year"]).quota == "MGMT"
        make_student(core_a, "26ECE001", batch_key="be_ece_batch")
        missing = dues.raise_dues(core_a["be_ece_batch"], core_a["year"])
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
    assert missing.skipped == ["26ECE001: no fee structure fits"]
    assert due_rows(management) == [(1, "TUITION", Decimal("60000"), 0, 0)]


def test_concessions_count_only_once_approved(college_a, core_a, make_student, principal):
    student = make_student(core_a, "26CSE001")
    merit = concession(core_a, student, percent=Decimal("10"))
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        assert due_rows(student)[0][3] == 0
        dues.approve(merit, principal)
        merit.refresh_from_db()
    assert merit.decided_by == principal and merit.funded_by == "college"
    assert due_rows(student) == [
        (1, "TUITION", Decimal("25000"), Decimal("2500"), 0),
        (1, "EXAM", Decimal("1500"), Decimal("150"), 0),
        (2, "TUITION", Decimal("25000"), Decimal("2500"), 0),
    ]
    with college_context(college_a):
        dues.withdraw(merit, principal)
    assert all(row[3] == 0 for row in due_rows(student))


def test_government_amount_is_taken_from_the_earliest_instalment(
    college_a, core_a, make_student, principal
):
    student = make_student(core_a, "26CSE001", community="SC")
    pms = concession(core_a, student, kind="PMS", head=core_a["tuition"], amount=Decimal("30000"))
    with college_context(college_a):
        dues.approve(pms, principal)  # before the dues exist: applied when they are raised
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        payable = sum(d.payable for d in StudentDue.objects.filter(student=student))
    assert pms.funded_by == "government"
    assert due_rows(student) == [
        (1, "TUITION", Decimal("25000"), 0, Decimal("25000")),
        (1, "EXAM", Decimal("1500"), 0, 0),
        (2, "TUITION", Decimal("25000"), 0, Decimal("5000")),
    ]
    assert payable == Decimal("21500")


def test_concessions_never_go_beyond_the_fee(college_a, core_a, make_student, principal):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
    full = concession(core_a, student, kind="FG", percent=Decimal("100"))
    extra = concession(core_a, student, head=core_a["exam"], amount=Decimal("500"))
    with college_context(college_a):
        dues.approve(full, principal)
        warnings = dues.approve(extra, principal)
    assert warnings == ["MERIT ₹500.00 for 26CSE001: ₹500.00 could not be applied"]
    assert all(row[4] == row[2] and row[3] == 0 for row in due_rows(student))


def test_paid_amounts_are_never_waived(college_a, core_a, make_student, principal):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        exam = StudentDue.objects.get(student=student, head=core_a["exam"])
        exam.paid = Decimal("1500")
        exam.save()
    sports = concession(core_a, student, kind="SPORTS", head=core_a["exam"], amount=Decimal("1500"))
    with college_context(college_a):
        warnings = dues.approve(sports, principal)
    assert warnings == ["SPORTS ₹1500.00 for 26CSE001: ₹1500.00 could not be applied"]


def test_decisions_follow_the_status_flow(college_a, core_a, make_student, principal):
    student = make_student(core_a, "26CSE001")
    merit = concession(core_a, student, percent=Decimal("5"))
    with college_context(college_a):
        with pytest.raises(ValidationError):
            dues.withdraw(merit, principal)
        dues.reject(merit, principal)
        with pytest.raises(ValidationError):
            dues.approve(merit, principal)


def test_concession_shape_is_checked(college_a, core_a, make_student):
    student = make_student(core_a, "26CSE001")
    for fields in [
        {"kind": "NOPE", "percent": 5},
        {},
        {"percent": 5, "amount": 5, "head": core_a["exam"]},
        {"amount": 5},
    ]:
        with pytest.raises(ValidationError):
            concession(core_a, student, **fields)


def test_dues_cannot_be_overpaid(college_a, core_a, make_student):
    student = make_student(core_a, "26CSE001")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        due = StudentDue.objects.filter(student=student).first()
        due.paid = due.amount + 1
        with transaction.atomic(), pytest.raises(IntegrityError):
            due.save()

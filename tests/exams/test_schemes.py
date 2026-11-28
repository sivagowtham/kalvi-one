"""Assessment schemes, grade scales, the marks arithmetic and the starting presets (D50-D52)."""

from decimal import Decimal as D

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.exams import marks, presets
from apps.exams.marks import component_marks, internal_total, round_marks
from apps.exams.models import (
    AssessmentScheme,
    GradeBand,
    GradeScale,
    SchemeComponent,
    SchemeLocked,
)
from apps.tenancy.context import NoCollegeSelected, college_context

pytestmark = pytest.mark.django_db


def load(college, name="anna-r2021"):
    with college_context(college):
        return presets.load(name)


def outcome(scheme_row, *args, **kwargs):
    with college_context(scheme_row.college):
        return marks.outcome(scheme_row, *args, **kwargs)


def scheme(college, code="AU-R2021-THEORY"):
    with college_context(college):
        return AssessmentScheme.objects.prefetch_related("components").get(code=code)


@pytest.mark.parametrize("model", [GradeScale, GradeBand, AssessmentScheme, SchemeComponent])
def test_each_model_is_isolated_per_college(model, college_a, college_b):
    load(college_a)
    load(college_b, "bharathiar-cbcs")
    with college_context(college_a):
        a_ids = set(model.objects.values_list("pk", flat=True))
    with college_context(college_b):
        b_ids = set(model.objects.values_list("pk", flat=True))
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    with pytest.raises(NoCollegeSelected):
        model.objects.count()


@pytest.mark.parametrize("name", sorted(presets.PRESETS))
def test_every_preset_loads_ready_to_use(name, college_a):
    result = load(college_a, name)
    assert result["skipped"] == []
    with college_context(college_a):
        schemes = AssessmentScheme.objects.all()
        assert schemes.count() == len(presets.PRESETS[name]["schemes"])
        for row in schemes:
            assert row.problems() == [], row.code
            assert row.is_active


def test_loading_twice_leaves_existing_rows_alone(college_a):
    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        theory.min_total_percent = D("55")
        theory.save()
    again = load(college_a)
    assert again["added"] == []
    assert scheme(college_a).min_total_percent == D("55")


def test_command_loads_a_preset(college_a, capsys):
    call_command("load_exam_schemes", "bharathiar-cbcs", "--college", "alpha")
    out = capsys.readouterr().out
    assert "added BU-CBCS-THEORY" in out and "regulation copy" in out
    with college_context(college_a):
        assert AssessmentScheme.objects.filter(code="BU-CBCS-THEORY").exists()


def test_best_two_of_three_tests_scaled_to_thirty(college_a):
    load(college_a)
    tests = scheme(college_a).components.get(code="TEST")
    # Best two of 40, 70, 90 out of 100 = 80% of 30.
    assert component_marks(tests, [D("40"), D("70"), D("90")]) == D("24")
    # A test not yet held or marked absent counts as zero.
    assert component_marks(tests, [D("90"), None]) == D("13.5")
    with pytest.raises(ValueError):
        component_marks(tests, [D("101")])
    with pytest.raises(ValueError):
        component_marks(tests, [D("1")] * 4)


def test_internal_total_rounds_once_at_the_end(college_a):
    load(college_a)
    theory = scheme(college_a)
    entered = {"TEST": [D("41"), D("70"), D("88")], "ASSIGN": [D("7"), D("8"), D("9")]}
    # Tests: (70 + 88) / 200 * 30 = 23.7. Assignments: 24 / 30 * 10 = 8. Total 31.7.
    assert internal_total(theory, entered, rounding="none") == D("31.70")
    assert internal_total(theory, entered, rounding="up") == D("32")
    assert internal_total(theory, entered, rounding="nearest") == D("32")
    with pytest.raises(ValueError):
        internal_total(theory, {"VIVA": [D("1")]})


def test_rounding_up_ignores_tiny_remainders():
    assert round_marks(D("30.0000001"), "up") == D("30")
    assert round_marks(D("30.01"), "up") == D("31")
    assert round_marks(D("30.5"), "nearest") == D("31")


@pytest.mark.parametrize(
    ("internal", "external", "passed", "letter", "point"),
    [
        (D("38"), D("56"), True, "O", D("10")),  # 94
        (D("30"), D("40"), True, "B+", D("7")),  # 70 falls in 61 to 70
        (D("40"), D("26"), False, "RA", D("0")),  # 26/60 is below the 45% end semester minimum
        (D("20"), D("28"), False, "RA", D("0")),  # 48 overall is below 50
        (D("23"), D("27"), True, "B", D("6")),  # exactly 27/60 and 50 overall
    ],
)
def test_anna_r2021_pass_rule_and_grades(college_a, internal, external, passed, letter, point):
    load(college_a)
    result = outcome(scheme(college_a), internal, external)
    assert (result.passed, result.letter, result.grade_point) == (passed, letter, point)
    assert result.passed == (not result.reasons)


def test_absent_student_gets_the_absent_letter(college_a):
    load(college_a)
    result = outcome(scheme(college_a), D("35"), None, absent=True)
    assert not result.passed and result.letter == "AB"


def test_bharathiar_pass_at_forty_percent(college_a):
    load(college_a, "bharathiar-cbcs")
    theory = scheme(college_a, "BU-CBCS-THEORY")
    assert outcome(theory, D("10"), D("30")).letter == "C"
    assert not outcome(theory, D("25"), D("29")).passed  # 29/75 is below 40%


def test_marks_outside_the_maximum_are_refused(college_a):
    load(college_a)
    with pytest.raises(ValueError):
        outcome(scheme(college_a), D("41"), D("10"))
    with pytest.raises(ValueError):
        outcome(scheme(college_a), D("10"), D("61"))


def test_problems_are_reported_in_plain_words(college_a):
    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        assign = theory.components.get(code="ASSIGN")
        assign.weight = D("5")
        assign.save()
        assert theory.problems() == [
            "The components add up to 35.00 but the internal maximum is 40.00."
        ]
        scale = theory.grade_scale
        scale.bands.get(letter="RA").delete()
        assert "Start the lowest grade at 0" in theory.problems()[1]


def test_database_refuses_bad_components(college_a):
    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        with pytest.raises(IntegrityError), transaction.atomic():
            SchemeComponent.objects.create(
                scheme=theory,
                code="QUIZ",
                name="Quiz",
                kind="quiz",
                count=2,
                max_marks=D("10"),
                rule="best",
                best_of=3,
                weight=D("0"),
            )


def test_one_active_scheme_per_regulation_and_course_type(college_a):
    load(college_a)
    with college_context(college_a):
        original = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        copy = original.copy("AU-R2021-THEORY-V2")
        assert not copy.is_active
        assert [c.code for c in copy.components.all()] == ["TEST", "ASSIGN"]
        copy.is_active = True
        with pytest.raises(IntegrityError), transaction.atomic():
            copy.save()
        original.is_active = False
        original.save()
        copy.save()


def test_a_locked_scheme_and_its_parts_cannot_change(college_a):
    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        theory.lock()
        theory.lock()  # a second call does nothing
        fresh = AssessmentScheme.objects.get(pk=theory.pk)
        assert fresh.is_locked
        fresh.min_total_percent = D("40")
        with pytest.raises(SchemeLocked):
            fresh.save()
        with pytest.raises(SchemeLocked):
            fresh.delete()
        component = fresh.components.first()
        component.weight = D("1")
        with pytest.raises(SchemeLocked):
            component.save()
        with pytest.raises(SchemeLocked):
            component.delete()
        scale = fresh.grade_scale
        scale.lock()
        band = scale.bands.first()
        band.min_percent = D("95")
        with pytest.raises(SchemeLocked):
            band.save()
        # A copy is free to change.
        new_scale = scale.copy("AU-R2021-V2")
        assert not new_scale.is_locked and new_scale.bands.count() == 6
        band = new_scale.bands.get(letter="O")
        band.min_percent = D("90")
        band.save()


def test_locking_is_audited(college_a):
    from apps.audit.models import AuditEvent

    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        theory.lock()
        event = AuditEvent.objects.filter(object_id=str(theory.pk)).order_by("-pk").first()
    assert event is not None and "is_locked" in str(event.changes)


def test_settings_have_defaults_and_follow_college_config(college_a):
    from apps.exams import config
    from apps.tenancy.models import CollegeFeature

    assert config.setting(college_a, "internal_rounding") == "up"
    college_a.config = {"exams": {"internal_rounding": "nearest"}}
    assert config.setting(college_a, "internal_rounding") == "nearest"
    assert [code for code, _ in config.setting(college_a, "mark_codes")] == ["AB", "MAL", "WH"]
    assert not config.is_autonomous(college_a)
    CollegeFeature.objects.create(college=college_a, key=config.AUTONOMOUS_FEATURE, enabled=True)
    assert config.is_autonomous(college_a)


def test_component_and_scheme_checks_in_plain_words(college_a):
    from django.core.exceptions import ValidationError

    load(college_a)
    with college_context(college_a):
        theory = AssessmentScheme.objects.get(code="AU-R2021-THEORY")
        component = SchemeComponent(
            scheme=theory,
            code="Q",
            name="Quiz",
            kind="quiz",
            count=2,
            max_marks=D("10"),
            rule="best",
            weight=D("0"),
        )
        with pytest.raises(ValidationError, match="how many count"):
            component.clean()
        component.best_of = 3
        with pytest.raises(ValidationError, match="more than are held"):
            component.clean()
        component.rule = "average"
        with pytest.raises(ValidationError, match="Only used"):
            component.clean()
        assert "best 2 of 3" in str(theory.components.get(code="TEST"))
        assert "all 3" in str(theory.components.get(code="ASSIGN"))
        internal_only = AssessmentScheme(
            code="X",
            name="X",
            internal_max=D("100"),
            external_max=D("0"),
            grade_scale=theory.grade_scale,
            min_external_percent=D("45"),
        )
        with pytest.raises(ValidationError, match="no end semester exam"):
            internal_only.clean()
        theory.grade_scale.bands.all().delete()
        assert "The scale has no grades." in theory.problems()[0] + theory.problems()[-1]

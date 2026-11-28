"""Starting schemes and grade scales for common Tamil Nadu regulations (D52).

These are starting points a college loads once and then edits to match its regulation copy.
They are named after universities and regulations, never after a college (D1). Loading is
idempotent: rows that already exist (by code) are left as they are.
"""

from __future__ import annotations

from decimal import Decimal as D

from django.db import transaction

from apps.academics.models import Course

from .models import AssessmentScheme, GradeBand, GradeScale, SchemeComponent

T = Course.CourseType

# Component tuples: (code, name, kind, count, each out of, rule, best of, worth).
PRESETS = {
    "anna-r2021": {
        "label": "Anna University, Regulation 2021 (affiliated engineering colleges)",
        "scale": {
            "code": "AU-R2021",
            "name": "Anna University R2021 grades",
            "fail_letter": "RA",
            "bands": [
                ("O", "Outstanding", "10", "91"),
                ("A+", "Excellent", "9", "81"),
                ("A", "Very good", "8", "71"),
                ("B+", "Good", "7", "61"),
                ("B", "Average", "6", "50"),
                ("RA", "Reappearance", "0", "0"),
            ],
        },
        "schemes": [
            {
                "code": "AU-R2021-THEORY",
                "name": "R2021 theory: 40 internal, 60 end semester",
                "regulation": "R2021",
                "course_type": T.THEORY,
                "internal_max": "40",
                "external_max": "60",
                "pass": ("45", "50"),
                "components": [
                    ("TEST", "Internal tests and model exam", "test", 3, "100", "best", 2, "30"),
                    ("ASSIGN", "Assignments", "assignment", 3, "10", "average", None, "10"),
                ],
            },
            {
                "code": "AU-R2021-PRACTICAL",
                "name": "R2021 practical: 60 internal, 40 end semester",
                "regulation": "R2021",
                "course_type": T.PRACTICAL,
                "internal_max": "60",
                "external_max": "40",
                "pass": ("45", "50"),
                "components": [
                    ("LAB", "Experiments and record", "lab", 1, "100", "average", None, "45"),
                    ("MODEL", "Model practical", "model_exam", 1, "100", "average", None, "15"),
                ],
            },
            {
                "code": "AU-R2021-INTEGRATED",
                "name": "R2021 theory with practical: 50 internal, 50 end semester",
                "regulation": "R2021",
                "course_type": T.THEORY_PRACTICAL,
                "internal_max": "50",
                "external_max": "50",
                "pass": ("45", "50"),
                "components": [
                    ("TEST", "Internal tests and model exam", "test", 3, "100", "best", 2, "25"),
                    ("LAB", "Experiments and record", "lab", 1, "100", "average", None, "25"),
                ],
            },
            {
                "code": "AU-R2021-PROJECT",
                "name": "R2021 project: 40 internal, 60 end semester viva",
                "regulation": "R2021",
                "course_type": T.PROJECT,
                "internal_max": "40",
                "external_max": "60",
                "pass": ("45", "50"),
                "components": [
                    ("REVIEW", "Reviews", "project_review", 3, "100", "average", None, "40"),
                ],
            },
        ],
    },
    "bharathiar-cbcs": {
        "label": "Bharathiar University CBCS (affiliated arts and science colleges)",
        "scale": {
            "code": "BU-CBCS",
            "name": "Bharathiar University CBCS grades",
            "fail_letter": "RA",
            "bands": [
                ("O", "Outstanding", "10", "90"),
                ("A+", "Excellent", "9", "80"),
                ("A", "Very good", "8", "70"),
                ("B+", "Good", "7", "60"),
                ("B", "Above average", "6", "50"),
                ("C", "Average", "5", "40"),
                ("RA", "Reappearance", "0", "0"),
            ],
        },
        "schemes": [
            {
                "code": "BU-CBCS-THEORY",
                "name": "CBCS theory: 25 internal, 75 end semester",
                "regulation": "",
                "course_type": T.THEORY,
                "internal_max": "25",
                "external_max": "75",
                "pass": ("40", "40"),
                "components": [
                    ("TEST", "CIA tests", "test", 2, "50", "average", None, "10"),
                    ("MODEL", "Model exam", "model_exam", 1, "75", "average", None, "5"),
                    ("ASSIGN", "Assignments", "assignment", 2, "10", "average", None, "5"),
                    ("SEMINAR", "Seminar", "seminar", 1, "10", "average", None, "5"),
                ],
            },
            {
                "code": "BU-CBCS-PRACTICAL",
                "name": "CBCS practical: 40 internal, 60 end semester",
                "regulation": "",
                "course_type": T.PRACTICAL,
                "internal_max": "40",
                "external_max": "60",
                "pass": ("40", "40"),
                "components": [
                    ("LAB", "Experiments and record", "lab", 1, "100", "average", None, "30"),
                    ("MODEL", "Model practical", "model_exam", 1, "100", "average", None, "10"),
                ],
            },
            {
                "code": "BU-CBCS-PROJECT",
                "name": "CBCS project: 20 internal, 80 end semester viva",
                "regulation": "",
                "course_type": T.PROJECT,
                "internal_max": "20",
                "external_max": "80",
                "pass": ("40", "40"),
                "components": [
                    ("REVIEW", "Reviews", "project_review", 2, "100", "average", None, "20"),
                ],
            },
        ],
    },
}


@transaction.atomic
def load(name: str) -> dict[str, list[str]]:
    """Load one preset into the current college. Returns the codes added and skipped."""
    preset = PRESETS[name]
    added, skipped = [], []
    spec = preset["scale"]
    scale = GradeScale.objects.filter(code=spec["code"]).first()
    if scale is None:
        scale = GradeScale.objects.create(
            code=spec["code"], name=spec["name"], fail_letter=spec["fail_letter"]
        )
        for letter, description, point, start in spec["bands"]:
            GradeBand.objects.create(
                scale=scale,
                letter=letter,
                description=description,
                grade_point=D(point),
                min_percent=D(start),
                is_pass=D(point) > 0,
            )
        added.append(scale.code)
    else:
        skipped.append(scale.code)
    for spec in preset["schemes"]:
        if AssessmentScheme.objects.filter(code=spec["code"]).exists():
            skipped.append(spec["code"])
            continue
        min_external, min_total = spec["pass"]
        # A scheme for the same regulation and course type may already be active; the new
        # one then starts inactive rather than breaking the "one active scheme" rule.
        clash = AssessmentScheme.objects.filter(
            regulation=spec["regulation"], course_type=spec["course_type"], is_active=True
        ).exists()
        scheme = AssessmentScheme.objects.create(
            code=spec["code"],
            name=spec["name"],
            regulation=spec["regulation"],
            course_type=spec["course_type"],
            internal_max=D(spec["internal_max"]),
            external_max=D(spec["external_max"]),
            grade_scale=scale,
            min_external_percent=D(min_external),
            min_total_percent=D(min_total),
            is_active=not clash,
        )
        for order, (code, cname, kind, count, each, rule, best, worth) in enumerate(
            spec["components"], start=1
        ):
            SchemeComponent.objects.create(
                scheme=scheme,
                code=code,
                name=cname,
                kind=kind,
                count=count,
                max_marks=D(each),
                rule=rule,
                best_of=best,
                weight=D(worth),
                sort_order=order,
            )
        added.append(scheme.code)
    return {"added": added, "skipped": skipped}

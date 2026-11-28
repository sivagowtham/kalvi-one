"""Working out internal totals, grades and pass or fail from a scheme (D51).

Plain functions on plain numbers, so the marks entry and results steps, the reports and the
AI risk list all use the same arithmetic. A missing mark or a mark code (absent, malpractice,
withheld) counts as zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from .models import AssessmentScheme, SchemeComponent

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
ONE = Decimal("1")

Mark = Decimal | None


def round_marks(value: Decimal, rounding: str) -> Decimal:
    if rounding == "up":
        # Ceiling, but ignore float-like dust such as 30.0000001 from scaling.
        return value.quantize(CENT, ROUND_HALF_UP).quantize(ONE, ROUND_CEILING)
    if rounding == "nearest":
        return value.quantize(ONE, ROUND_HALF_UP)
    return value.quantize(CENT, ROUND_HALF_UP)


def component_marks(component: SchemeComponent, marks: Iterable[Mark]) -> Decimal:
    """What one component adds to the internal total, unrounded.

    ``marks`` are the raw marks of each one held, out of ``component.max_marks``. Fewer than
    ``count`` means the rest were not held or not entered, and count as zero.
    """
    raw = [m if m is not None else ZERO for m in marks]
    for value in raw:
        if value < 0 or value > component.max_marks:
            raise ValueError(f"{value} is outside 0 to {component.max_marks} for {component.name}.")
    if len(raw) > component.count:
        raise ValueError(f"{component.name} has {component.count}, not {len(raw)}.")
    raw += [ZERO] * (component.count - len(raw))
    if component.rule == SchemeComponent.Rule.BEST:
        counted = sorted(raw, reverse=True)[: component.best_of]
        fraction = sum(counted, ZERO) / (component.max_marks * len(counted))
    else:
        fraction = sum(raw, ZERO) / (component.max_marks * component.count)
    return fraction * component.weight


def internal_total(
    scheme: AssessmentScheme,
    marks_by_component: Mapping[str, Iterable[Mark]],
    *,
    rounding: str = "up",
) -> Decimal:
    """The internal (CIA) total out of ``scheme.internal_max``, rounded once at the end."""
    components = list(scheme.components.all())
    unknown = set(marks_by_component) - {c.code for c in components}
    if unknown:
        raise ValueError(f"{scheme.code} has no component {', '.join(sorted(unknown))}.")
    total = sum((component_marks(c, marks_by_component.get(c.code, ())) for c in components), ZERO)
    return min(round_marks(total, rounding), scheme.internal_max)


@dataclass(frozen=True)
class Outcome:
    total: Decimal
    percent: Decimal
    passed: bool
    letter: str
    grade_point: Decimal
    reasons: tuple[str, ...]


def percent_of(value: Decimal, maximum: Decimal) -> Decimal:
    if not maximum:
        return ZERO
    return (value * HUNDRED / maximum).quantize(CENT, ROUND_HALF_UP)


def outcome(
    scheme: AssessmentScheme,
    internal: Decimal,
    external: Decimal | None,
    *,
    absent: bool = False,
) -> Outcome:
    """Pass or fail, grade and grade point for one student in one course.

    ``external`` is the end semester mark out of ``scheme.external_max`` (None when the
    course has no end semester exam). ``absent`` means the student missed that exam.
    """
    scale = scheme.grade_scale
    external = external if external is not None else ZERO
    if internal < 0 or internal > scheme.internal_max:
        raise ValueError(f"Internal {internal} is outside 0 to {scheme.internal_max}.")
    if external < 0 or external > scheme.external_max:
        raise ValueError(f"End semester {external} is outside 0 to {scheme.external_max}.")
    total = internal + external
    percent = percent_of(total, scheme.total_max)
    reasons = []
    if absent and scheme.external_max:
        reasons.append("absent from the end semester exam")
    if scheme.external_max and percent_of(external, scheme.external_max) < (
        scheme.min_external_percent
    ):
        reasons.append(f"end semester below {scheme.min_external_percent.normalize():f}%")
    if scheme.internal_max and percent_of(internal, scheme.internal_max) < (
        scheme.min_internal_percent
    ):
        reasons.append(f"internal below {scheme.min_internal_percent.normalize():f}%")
    if percent < scheme.min_total_percent:
        reasons.append(f"total below {scheme.min_total_percent.normalize():f}%")
    band = scale.band_for(percent)
    if not band.is_pass:
        reasons.append(f"grade {band.letter} is not a pass")
    if reasons:
        letter = scale.absent_letter if absent and scheme.external_max else scale.fail_letter
        return Outcome(total, percent, False, letter, ZERO, tuple(reasons))
    return Outcome(total, percent, True, band.letter, band.grade_point, ())

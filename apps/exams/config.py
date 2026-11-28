"""Per-college settings for the exams module, stored in College.config["exams"] (D13, D52).

Every key has a default here, so a college needs config only where it differs. Schemes,
grade scales and pass rules are rows, not config, because results point at them (D51).
Whether a college runs its own end semester exams is the feature flag ``exams_autonomous``.
"""

from __future__ import annotations

from typing import Any

AUTONOMOUS_FEATURE = "exams_autonomous"

DEFAULTS: dict[str, Any] = {
    # How the internal total is rounded once the components are added up:
    # "up" (ceiling to a whole mark, common in Tamil Nadu), "nearest" (half up) or "none"
    # (kept to two decimal places).
    "internal_rounding": "up",
    # Codes a teacher can enter instead of a mark: [code, label]. Each counts as zero.
    "mark_codes": [
        ["AB", "Absent"],
        ["MAL", "Malpractice"],
        ["WH", "Withheld"],
    ],
}

ROUNDING_CHOICES = {"up", "nearest", "none"}


def setting(college, key: str) -> Any:
    return (college.config or {}).get("exams", {}).get(key, DEFAULTS[key])


def is_autonomous(college) -> bool:
    return college.has_feature(AUTONOMOUS_FEATURE)

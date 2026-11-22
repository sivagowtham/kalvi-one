"""Fee reminder drafts in English and Tamil, filled in on our server (D32).

Staff send them from their own phone through a WhatsApp link; KalviOne sends nothing itself.
"""

from __future__ import annotations

from urllib.parse import quote

from . import config
from .templatetags.fees import inr

LANGUAGES = {"en": "English", "ta": "தமிழ்"}


def drafts(college, student, balance, due_date) -> list[dict]:
    values = {
        "name": student.name,
        "roll": student.roll_number,
        "college": college.name,
        "balance": inr(balance),
        "due_date": f"{due_date:%d-%m-%Y}" if due_date else "",
    }
    templates = config.setting(college, "reminder_templates")
    result = []
    for code, label in LANGUAGES.items():
        if code not in templates:
            continue
        text = templates[code].format(**values)
        link = ""
        if student.mobile:
            link = f"https://wa.me/91{student.mobile}?text={quote(text)}"
        result.append({"code": code, "label": label, "text": text, "whatsapp": link})
    return result

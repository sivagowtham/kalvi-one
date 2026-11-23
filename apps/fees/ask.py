"""Plain-word fee questions, turned into a report by Claude (D32).

Claude gets only the question and the names of the college's years, batches and fee heads.
It answers with which report to open and its filters; the numbers then come from our own
database, so Claude never sees a student, an amount or a total.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear
from apps.students.models import Batch

from . import config
from .models import FeeHead

log = logging.getLogger(__name__)

REPORTS = ("dues", "at_risk", "collections")
# A long run of digits looks like a phone, Aadhaar or roll number: refuse it before sending.
DIGITS = re.compile(r"\d{6,}")

SYSTEM = """You turn a college fee office's question into one report and its filters.
Reports: "dues" (what students owe, by batch; can list who owes in one batch),
"at_risk" (students with overdue fees most likely to fall behind),
"collections" (money received between two dates).
Pick names only from the lists given; use "" for any filter the question does not name.
Dates are YYYY-MM-DD; today's date is given. "overdue" is true only if the question is
about fees past their due date. If the question is not about fees, set report to "none"."""


@dataclass
class Answer:
    report: str
    params: dict
    summary: str


def enabled(college) -> bool:
    return bool(settings.ANTHROPIC_API_KEY) and bool(config.setting(college, "ai_questions"))


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=20, max_retries=1)


def _choices():
    years = {y.label: y.pk for y in AcademicYear.objects.all()}
    batches = {
        str(b): b.pk for b in Batch.objects.filter(is_active=True).select_related("programme")
    }
    heads = {h.name: h.pk for h in FeeHead.objects.filter(is_active=True)}
    return years, batches, heads


def _schema(years, batches, heads) -> dict:
    def pick(names):
        return {"type": "string", "enum": ["", *names]}

    return {
        "type": "object",
        "properties": {
            "report": {"type": "string", "enum": [*REPORTS, "none"]},
            "academic_year": pick(years),
            "batch": pick(batches),
            "head": pick(heads),
            "overdue": {"type": "boolean"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "summary": {
                "type": "string",
                "description": "One short sentence saying what the report will show.",
            },
        },
        "required": [
            "report",
            "academic_year",
            "batch",
            "head",
            "overdue",
            "start",
            "end",
            "summary",
        ],
        "additionalProperties": False,
    }


def _date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def interpret(college, question: str, today: dt.date) -> Answer:
    question = question.strip()
    if not question:
        raise ValidationError("Type a question about fees.")
    if DIGITS.search(question):
        raise ValidationError(
            "Leave out phone, roll and Aadhaar numbers; ask about batches, years or fee heads."
        )
    years, batches, heads = _choices()
    prompt = json.dumps(
        {
            "question": question[:300],
            "today": today.isoformat(),
            "academic_years": list(years),
            "batches": list(batches),
            "fee_heads": list(heads),
        },
        ensure_ascii=False,
    )
    try:
        response = _client().messages.create(
            model=settings.FEES_AI_MODEL,
            max_tokens=400,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": _schema(years, batches, heads)},
            },
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
    except Exception:
        log.exception("Fee question could not be answered")
        raise ValidationError(
            "The question could not be answered just now. Use the filters."
        ) from None
    report = data.get("report")
    if report not in REPORTS:
        raise ValidationError("That does not look like a question about fees.")
    if report == "collections":
        start = _date(data.get("start")) or today
        end = _date(data.get("end")) or start
        start, end = min(start, end), max(start, end)
        params = {"start": start.isoformat(), "end": end.isoformat()}
    else:
        params = {
            "academic_year": years.get(data.get("academic_year"), ""),
            "batch": batches.get(data.get("batch"), ""),
            "head": heads.get(data.get("head"), ""),
        }
        if data.get("overdue") and report == "dues":
            params["overdue"] = "on"
        params = {key: value for key, value in params.items() if value != ""}
    return Answer(report, params, str(data.get("summary", ""))[:200])

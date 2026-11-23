"""AI features (D32): dues-risk flags, plain-word questions, reminder drafts."""

import datetime as dt
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.fees import ask, dues, receipts, reminders, risk
from apps.fees.reports import DuesFilter
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
TODAY = dt.date(2026, 11, 22)  # semester 1 (due 15 July) is overdue, semester 2 is not


@pytest.fixture
def setup(college_a, core_a, make_student, accountant):
    never_paid = make_student(core_a, "26CSE001", mobile="9876543210")
    part_paid = make_student(core_a, "26CSE002")
    paid_up = make_student(core_a, "26CSE003")
    with college_context(college_a):
        dues.raise_dues(core_a["be_cse_batch"], core_a["year"])
        receipts.collect(
            part_paid, Decimal("20000"), mode="cash", account=core_a["cash"], user=accountant
        )
        receipts.collect(
            paid_up, Decimal("26500"), mode="cash", account=core_a["cash"], user=accountant
        )
    return {"never_paid": never_paid, "part_paid": part_paid, "paid_up": paid_up}


def test_flags_rank_students_with_plain_reasons(college_a, setup):
    with college_context(college_a):
        flagged = risk.flags(DuesFilter(), TODAY)
    assert [f.roll_number for f in flagged] == ["26CSE001", "26CSE002"]
    first, second = flagged
    assert first.overdue == Decimal("26500") and first.level == risk.HIGH
    assert "has not paid anything yet" in first.reasons
    assert first.reasons[0] == "₹26,500.00 overdue for 130 day(s)"
    assert second.overdue == Decimal("6500") and second.level == risk.WATCH
    assert second.last_paid is not None


def test_flags_stay_inside_their_college(college_a, college_b, setup, core_b, make_student):
    make_student(core_b, "26CSE001")
    with college_context(college_b):
        dues.raise_dues(core_b["be_cse_batch"], core_b["year"])
        other = risk.flags(DuesFilter(), TODAY)
    assert [f.roll_number for f in other] == ["26CSE001"]
    assert other[0].mobile == ""


def test_reminder_drafts_in_english_and_tamil(college_a, setup):
    student = setup["never_paid"]
    with college_context(college_a):
        drafts = reminders.drafts(college_a, student, Decimal("26500"), dt.date(2026, 7, 15))
    assert [d["code"] for d in drafts] == ["en", "ta"]
    assert "₹26,500.00" in drafts[0]["text"] and "15-07-2026" in drafts[0]["text"]
    assert "நிலுவை" in drafts[1]["text"]
    assert drafts[0]["whatsapp"].startswith("https://wa.me/919876543210?text=Dear%20")


def test_at_risk_and_reminder_pages(client, college_a, setup, office):
    client.force_login(office)
    page = client.get("/fees/reports/at-risk/", HTTP_HOST=ALPHA).content.decode()
    assert "26CSE001" in page and "26CSE003" not in page and "Draft a reminder" in page
    reminder = client.get(f"/fees/reminders/{setup['never_paid'].pk}/", HTTP_HOST=ALPHA)
    assert "Open in WhatsApp" in reminder.content.decode()
    paid = client.get(f"/fees/reminders/{setup['paid_up'].pk}/", HTTP_HOST=ALPHA)
    assert "Nothing is overdue" in paid.content.decode()


def test_faculty_sees_neither_risk_nor_reminders(client, college_a, setup, make_user):
    from apps.accounts.roles import Role

    faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
    client.force_login(faculty)
    assert client.get("/fees/reports/at-risk/", HTTP_HOST=ALPHA).status_code == 403
    response = client.get(f"/fees/reminders/{setup['never_paid'].pk}/", HTTP_HOST=ALPHA)
    assert response.status_code == 403


def _reply(data):
    block = SimpleNamespace(type="text", text=json.dumps(data))
    return SimpleNamespace(content=[block])


def _answer(**fields):
    base = {
        "report": "dues",
        "academic_year": "",
        "batch": "",
        "head": "",
        "overdue": False,
        "start": "",
        "end": "",
        "summary": "Overdue tuition fees.",
    }
    return _reply(base | fields)


@pytest.fixture
def claude(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    client = mock.MagicMock()
    with mock.patch.object(ask, "_client", return_value=client):
        yield client.messages.create


def test_question_sends_only_names_never_student_data(college_a, core_a, setup, claude):
    claude.return_value = _answer(head="Tuition fee", overdue=True)
    with college_context(college_a):
        batch = str(core_a["be_cse_batch"])
        claude.return_value = _answer(head="Tuition fee", batch=batch, overdue=True)
        answer = ask.interpret(college_a, "Who in CSE owes tuition past due?", TODAY)
    assert answer.report == "dues"
    assert answer.params == {
        "batch": core_a["be_cse_batch"].pk,
        "head": core_a["tuition"].pk,
        "overdue": "on",
    }
    sent = json.dumps(claude.call_args.kwargs, ensure_ascii=False, default=str)
    for student in setup.values():
        assert student.roll_number not in sent and student.name not in sent
    assert "9876543210" not in sent and "26500" not in sent and "26,500" not in sent
    schema = claude.call_args.kwargs["output_config"]["format"]["schema"]
    assert "Tuition fee" in schema["properties"]["head"]["enum"]


def test_question_with_numbers_is_refused_before_sending(college_a, setup, claude):
    with college_context(college_a), pytest.raises(Exception, match="Leave out"):
        ask.interpret(college_a, "What does 9876543210 owe?", TODAY)
    claude.assert_not_called()


def test_collections_dates_and_failures(college_a, setup, claude):
    claude.return_value = _answer(report="collections", start="2026-11-30", end="2026-11-01")
    with college_context(college_a):
        answer = ask.interpret(college_a, "Money received this month", TODAY)
        assert answer.params == {"start": "2026-11-01", "end": "2026-11-30"}
        claude.return_value = _answer(report="none")
        with pytest.raises(Exception, match="not look like"):
            ask.interpret(college_a, "What is the weather?", TODAY)
        claude.side_effect = RuntimeError("down")
        with pytest.raises(Exception, match="could not be answered"):
            ask.interpret(college_a, "Dues this year", TODAY)


def test_ask_view_redirects_to_the_report(client, college_a, core_a, setup, office, claude):
    claude.return_value = _answer(report="at_risk", head="Exam fee")
    client.force_login(office)
    page = client.get("/fees/reports/dues/", HTTP_HOST=ALPHA).content.decode()
    assert "Ask in plain words" in page
    response = client.post(
        "/fees/reports/ask/",
        {"question": "Exam fee at risk", "next": "/fees/reports/dues/"},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302
    assert response["Location"] == f"/fees/reports/at-risk/?head={core_a['exam'].pk}"


def test_ask_box_hidden_without_a_key_or_when_turned_off(
    client, college_a, setup, office, settings
):
    settings.ANTHROPIC_API_KEY = ""
    client.force_login(office)
    page = client.get("/fees/reports/dues/", HTTP_HOST=ALPHA).content.decode()
    assert "Ask in plain words" not in page
    settings.ANTHROPIC_API_KEY = "test-key"
    college_a.config = {"fees": {"ai_questions": False}}
    college_a.save()
    page = client.get("/fees/reports/dues/", HTTP_HOST=ALPHA).content.decode()
    assert "Ask in plain words" not in page

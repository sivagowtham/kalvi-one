"""Timetable pages and the admin (D7, D14, D35, D36)."""

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.students.models import StudentSemester
from apps.tenancy.context import college_context
from apps.timetable.models import Allocation, CalendarDay, LabGroup, TimetableEntry

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"


@pytest.fixture
def principal(college_a, make_user):
    return make_user(college_a, "principal", roles=[Role.PRINCIPAL])


@pytest.fixture
def hod_ece(college_a, core_a, make_user):
    return make_user(college_a, "hod-ece", roles=[(Role.HOD, core_a["ece"])])


class TestMyTimetable:
    def test_teacher_sees_their_classes_for_a_day(self, client, core_a):
        client.force_login(core_a["teacher"])
        page = client.get("/timetable/", {"day": 1}, HTTP_HOST=ALPHA).content.decode()
        assert "CS3301" in page and "CS-101" in page and "09:00" in page
        other = client.get("/timetable/", {"day": 2}, HTTP_HOST=ALPHA).content.decode()
        assert "No classes for you on Tuesday" in other

    def test_today_opens_on_the_day_the_calendar_says(self, client, college_a, core_a):
        with college_context(college_a):
            CalendarDay.objects.create(date=timezone.localdate(), is_working=True, day=1)
        client.force_login(core_a["teacher"])
        page = client.get("/timetable/", HTTP_HOST=ALPHA).content.decode()
        assert "CS3301" in page and "Monday" in page

    def test_holiday_is_shown(self, client, college_a, core_a):
        with college_context(college_a):
            CalendarDay.objects.create(date=timezone.localdate(), is_working=False, note="Pongal")
        client.force_login(core_a["teacher"])
        page = client.get("/timetable/", HTTP_HOST=ALPHA).content.decode()
        assert "holiday, Pongal" in page

    def test_accounts_staff_and_visitors_are_kept_out(self, client, college_a, core_a, make_user):
        assert client.get("/timetable/", HTTP_HOST=ALPHA).status_code == 302
        client.force_login(make_user(college_a, "cashier", roles=[Role.ACCOUNTS]))
        assert client.get("/timetable/", HTTP_HOST=ALPHA).status_code == 403

    def test_home_links_to_the_timetable(self, client, core_a):
        client.force_login(core_a["teacher"])
        assert "My timetable" in client.get("/", HTTP_HOST=ALPHA).content.decode()


def test_section_timetable_lists_every_day(client, college_a, core_a):
    client.force_login(core_a["teacher"])
    listing = client.get("/timetable/sections/", HTTP_HOST=ALPHA).content.decode()
    assert str(core_a["be_cse_a"]) in listing
    page = client.get(f"/timetable/sections/{core_a['be_cse_a'].pk}/", HTTP_HOST=ALPHA)
    text = page.content.decode()
    assert "Monday" in text and "Saturday" in text and "Fake Teacher" in text


def test_another_colleges_section_is_not_found(client, core_a, core_b):
    client.force_login(core_a["teacher"])
    url = f"/timetable/sections/{core_b['be_cse_a'].pk}/"
    assert client.get(url, HTTP_HOST=ALPHA).status_code == 404


class TestAdmin:
    @pytest.mark.parametrize(
        "model",
        [
            "bellschedule",
            "calendarday",
            "labgroup",
            "allocation",
        ],
    )
    def test_principal_opens_every_list_and_form(self, client, core_a, principal, model):
        client.force_login(principal)
        assert client.get(f"/admin/timetable/{model}/", HTTP_HOST=ALPHA).status_code == 200
        assert client.get(f"/admin/timetable/{model}/add/", HTTP_HOST=ALPHA).status_code == 200

    def test_allocation_page_shows_entries(self, client, core_a, principal):
        client.force_login(principal)
        url = f"/admin/timetable/allocation/{core_a['allocation'].pk}/change/"
        page = client.get(url, HTTP_HOST=ALPHA).content.decode()
        assert "CS-101" in page and "Monday" in page

    def test_principal_fills_a_term(self, client, college_a, core_a, principal):
        client.force_login(principal)
        response = client.post(
            "/admin/timetable/calendarday/fill/",
            {"semester": core_a["odd"].pk, "holidays": "2026-10-02 Gandhi Jayanti"},
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        with college_context(college_a):
            assert CalendarDay.objects.count() == 153
            assert not CalendarDay.objects.get(date=dt.date(2026, 10, 2)).is_working

    def test_a_bad_holiday_line_is_explained(self, client, core_a, principal):
        client.force_login(principal)
        response = client.post(
            "/admin/timetable/calendarday/fill/",
            {"semester": core_a["odd"].pk, "holidays": "Pongal"},
            HTTP_HOST=ALPHA,
        )
        assert "is not a date like 2027-01-15" in response.content.decode()

    def test_hods_and_teachers_cannot_fill_the_calendar(self, client, core_a, hod_ece):
        for user in [hod_ece, core_a["teacher"]]:
            client.force_login(user)
            url = "/admin/timetable/calendarday/fill/"
            # The teacher has no office workspace at all, so the admin sends them to log in.
            assert client.get(url, HTTP_HOST=ALPHA).status_code in (302, 403)

    def test_hod_cannot_plan_another_department(self, client, college_a, core_a, hod_ece):
        client.force_login(hod_ece)
        response = client.post(
            "/admin/timetable/allocation/add/",
            {
                "semester": core_a["odd"].pk,
                "course": core_a["course"].pk,
                "section": core_a["be_cse_b"].pk,
                "hours_per_week": 3,
                "block_length": 1,
                "teachers-TOTAL_FORMS": 0,
                "teachers-INITIAL_FORMS": 0,
                "entries-TOTAL_FORMS": 0,
                "entries-INITIAL_FORMS": 0,
                "roster-TOTAL_FORMS": 0,
                "roster-INITIAL_FORMS": 0,
            },
            HTTP_HOST=ALPHA,
        )
        # The CSE section is not offered to the ECE HOD, so the form is refused.
        assert response.status_code == 200
        assert "Select a valid choice" in response.content.decode()
        with college_context(college_a):
            assert not Allocation.objects.filter(section=core_a["be_cse_b"]).exists()

    def test_a_clash_shows_on_the_admin_form(self, client, college_a, core_a, principal):
        client.force_login(principal)
        allocation = core_a["allocation"]
        entry = core_a["entry"]
        with college_context(college_a):
            teacher_link = allocation.teachers.get().pk
        response = client.post(
            f"/admin/timetable/allocation/{allocation.pk}/change/",
            {
                "semester": core_a["odd"].pk,
                "course": core_a["course"].pk,
                "section": core_a["be_cse_a"].pk,
                "hours_per_week": 4,
                "block_length": 1,
                "teachers-TOTAL_FORMS": 1,
                "teachers-INITIAL_FORMS": 1,
                "teachers-0-id": teacher_link,
                "teachers-0-allocation": allocation.pk,
                "teachers-0-teacher": core_a["teacher"].pk,
                "entries-TOTAL_FORMS": 2,
                "entries-INITIAL_FORMS": 1,
                "entries-0-id": entry.pk,
                "entries-0-allocation": allocation.pk,
                "entries-0-day": 1,
                "entries-0-period": core_a["periods"][1].pk,
                "entries-0-room": "CS-101",
                "entries-1-allocation": allocation.pk,
                "entries-1-day": 1,
                "entries-1-period": core_a["periods"][1].pk,
                "entries-1-room": "",
                "roster-TOTAL_FORMS": 0,
                "roster-INITIAL_FORMS": 0,
            },
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 200
        with college_context(college_a):
            assert TimetableEntry.objects.count() == 1

    def test_split_lab_groups_evenly(self, client, college_a, core_a, principal, make_student):
        students = [make_student(core_a, f"26CSE00{n}") for n in range(1, 6)]
        with college_context(college_a):
            for student in students:
                StudentSemester.objects.create(
                    student=student,
                    semester=core_a["odd"],
                    semester_number=3,
                    section=core_a["be_cse_a"],
                )
            b2 = LabGroup.objects.create(
                section=core_a["be_cse_a"], semester=core_a["odd"], name="B2"
            )
        client.force_login(principal)
        response = client.post(
            "/admin/timetable/labgroup/",
            {"action": "split_evenly", "_selected_action": [core_a["lab_b1"].pk, b2.pk]},
            HTTP_HOST=ALPHA,
        )
        assert response.status_code == 302
        with college_context(college_a):
            assert core_a["lab_b1"].members.count() == 3
            assert b2.members.count() == 2
            first = core_a["lab_b1"].members.order_by("student__roll_number").first()
            assert first.student.roll_number == "26CSE001"

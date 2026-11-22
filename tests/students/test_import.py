"""Excel import (D22)."""

import datetime as dt
from io import BytesIO, StringIO

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from openpyxl import Workbook, load_workbook

from apps.accounts.roles import Role
from apps.audit.models import AuditEvent
from apps.students import importer
from apps.students.fakes import fake_aadhaar
from apps.students.models import Guardian, ImportMapping, ImportRun, Student, StudentSemester
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db
ALPHA = "alpha.localhost"
HEADERS = [
    "Roll number",
    "Admission number",
    "Name",
    "Gender",
    "Date of birth",
    "Programme code",
    "Batch year",
    "Section",
    "Current semester",
    "Community",
    "Quota",
    "First graduate",
    "Aadhaar number",
    "Father name",
    "Father mobile",
    "Mother name",
    "Mobile",
]


def good_row(n, **changes):
    row = {
        "Roll number": f"26CSE{n:03d}",
        "Admission number": f"A{n}",
        "Name": f"IMPORTED {n}",
        "Gender": "Female",
        "Date of birth": dt.datetime(2008, 1, n),
        "Programme code": "be-cse",
        "Batch year": 2026,
        "Section": "a",
        "Current semester": 1,
        "Community": "bc",
        "Quota": "GOVT",
        "First graduate": "yes",
        "Aadhaar number": fake_aadhaar(500 + n),
        "Father name": f"FATHER {n}",
        "Father mobile": "9876543210",
        "Mother name": f"MOTHER {n}",
        "Mobile": 9123456780.0,  # Excel stores numbers as floats
    }
    return row | changes


def xlsx(rows, headers=HEADERS, name="students.xlsx"):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(h) for h in headers])
    sheet.append([None] * len(headers))  # blank rows are skipped
    out = BytesIO()
    book.save(out)
    return SimpleUploadedFile(name, out.getvalue())


@pytest.fixture
def office(college_a, make_user):
    return make_user(college_a, "office", roles=[Role.OFFICE])


def run(office, upload, **kwargs):
    with college_context(office.college):
        return importer.run(office, upload, **kwargs)


def test_check_only_saves_nothing(college_a, core_a, office):
    result = run(office, xlsx([good_row(1), good_row(2)]), commit=False)
    assert (result.status, result.row_count, result.errors) == ("checked", 2, [])
    with college_context(college_a):
        assert not Student.objects.exists()


def test_import_creates_students_logins_guardians_and_placements(college_a, core_a, office):
    result = run(office, xlsx([good_row(1), good_row(2)]), commit=True)
    assert result.status == "imported" and result.created_count == 2
    with college_context(college_a):
        student = Student.objects.get(roll_number="26CSE001")
        placement = StudentSemester.objects.get(student=student)
        guardians = Guardian.objects.filter(student=student).order_by("relation")
        assert student.reveal("aadhaar", office) == fake_aadhaar(501)
        assert AuditEvent.objects.filter(action="create", object_repr__startswith="26CSE0").count()
    assert student.community == "BC" and student.gender == "female"
    assert student.date_of_birth == dt.date(2008, 1, 1)
    assert student.mobile == "9123456780"
    assert student.is_first_graduate
    assert student.user.username == "26CSE001" and student.user.roles() == {Role.STUDENT}
    # The login gets the student's contact details, so reset and invite emails can reach them.
    assert (student.user.email, student.user.phone) == (student.email, "9123456780")
    assert (placement.semester_number, placement.section) == (1, core_a["be_cse_a"])
    assert [g.is_primary for g in guardians] == [True, False]
    assert str(result).startswith("students.xlsx")


def test_one_bad_row_blocks_the_whole_file(college_a, core_a, make_student, office):
    make_student(core_a, "26CSE009", admission_number="TAKEN")
    rows = [
        good_row(1),
        good_row(2, **{"Gender": "x", "Community": "XYZ", "Quota": "NRI"}),
        good_row(3, **{"Roll number": "26CSE009", "Admission number": "TAKEN"}),
        good_row(4, **{"Batch year": 2019}),
        good_row(5, **{"Section": "Z"}),
        good_row(6, **{"Current semester": 2}),
        good_row(7, **{"Aadhaar number": "123412341234", "Mobile": "12345"}),
        good_row(8, **{"Date of birth": "31/02/2008", "Name": ""}),
        good_row(1, **{"Aadhaar number": fake_aadhaar(510)}),  # roll and admission repeat
        good_row(11, **{"Aadhaar number": fake_aadhaar(502), "Current semester": "two"}),
    ]
    result = run(office, xlsx(rows), commit=True)
    assert result.status == "failed" and result.created_count == 0
    found = {(row, column) for row, column, _ in result.errors}
    expected = {
        (3, "Gender"),
        (3, "Community"),
        (3, "Quota"),
        (4, "Roll number"),
        (4, "Admission number"),
        (5, "Batch year"),
        (6, "Section"),
        (7, "Current semester"),
        (8, "Aadhaar number"),
        (8, "Mobile"),
        (9, "Date of birth"),
        (9, "Name"),
        (10, "Roll number"),
        (10, "Admission number"),
        (11, "Aadhaar number"),
        (11, "Current semester"),
    }
    assert expected <= found
    with college_context(college_a):
        assert Student.objects.count() == 1


def test_file_level_problems(college_a, core_a, office):
    missing = run(office, xlsx([{"Name": "X"}], headers=["Name"]), commit=False)
    assert [1, "Roll number", "This required column is missing."] in missing.errors
    junk = run(office, SimpleUploadedFile("x.xlsx", b"not a workbook"), commit=False)
    assert junk.errors == [[0, "File", "This is not an Excel (.xlsx) file."]]
    with college_context(college_a):
        core_a["odd"].is_current = False
        core_a["odd"].save()
    no_term = run(office, xlsx([good_row(1)]), commit=False)
    assert no_term.errors[0][2].startswith("Set the current term")


def test_saved_mapping_reads_other_headers(college_a, core_a, office):
    headers = ["Reg No", *HEADERS[1:]]
    with college_context(college_a):
        layout = ImportMapping.objects.create(
            name="Laudea export", mapping={"Reg No": "roll_number"}
        )
    row = good_row(1)
    row["Reg No"] = row.pop("Roll number")
    result = run(office, xlsx([row], headers=headers), mapping=layout, commit=True)
    assert result.created_count == 1
    assert str(layout) == "Laudea export"


def test_permission(college_a, core_a, make_user):
    faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
    with college_context(college_a), pytest.raises(PermissionDenied):
        importer.run(faculty, xlsx([good_row(1)]), commit=True)


def test_template_lists_columns_and_allowed_values(college_a, core_a):
    with college_context(college_a):
        book = load_workbook(BytesIO(importer.template(college_a)))
    assert next(book["Students"].values)[0] == "Roll number"
    notes = {row[0]: row[2] for row in book["Allowed values"].values}
    assert "BCM" in notes["Community"]
    assert "BE-CSE" in notes["Programme code"]


class TestAdmin:
    def test_import_page_check_and_import(self, client, college_a, core_a, office):
        client.force_login(office)
        listing = client.get("/admin/students/student/", HTTP_HOST=ALPHA)
        assert b"Import from Excel" in listing.content
        url = "/admin/students/student/import/"
        bad = client.post(
            url, {"file": xlsx([good_row(1, Gender="x")]), "import": "1"}, HTTP_HOST=ALPHA
        )
        assert "Nothing was saved" in bad.content.decode()
        checked = client.post(url, {"file": xlsx([good_row(1)]), "check": "1"}, HTTP_HOST=ALPHA)
        assert "All 1 row(s) passed" in checked.content.decode()
        done = client.post(url, {"file": xlsx([good_row(1)]), "import": "1"}, HTTP_HOST=ALPHA)
        assert done.status_code == 302
        with college_context(college_a):
            assert Student.objects.count() == 1
            assert ImportRun.objects.count() == 3
        runs = client.get("/admin/students/importrun/", HTTP_HOST=ALPHA)
        assert runs.status_code == 200

    def test_template_download(self, client, core_a, office):
        client.force_login(office)
        response = client.get("/admin/students/student/import/template/", HTTP_HOST=ALPHA)
        assert response["Content-Disposition"].endswith('template.xlsx"')

    def test_faculty_is_refused(self, client, college_a, core_a, make_user):
        client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
        assert client.get("/admin/students/student/import/", HTTP_HOST=ALPHA).status_code == 403
        url = "/admin/students/student/import/template/"
        assert client.get(url, HTTP_HOST=ALPHA).status_code == 403
        assert (
            b"Import from Excel"
            not in client.get("/admin/students/student/", HTTP_HOST=ALPHA).content
        )


class TestCommand:
    def test_check_and_commit(self, tmp_path, college_a, core_a, office):
        path = tmp_path / "students.xlsx"
        path.write_bytes(xlsx([good_row(1)]).read())
        out = StringIO()
        call_command("import_students", str(path), college="alpha", username="office", stdout=out)
        assert "Checked" in out.getvalue()
        call_command(
            "import_students",
            str(path),
            college="alpha",
            commit=True,
            stdout=out,
            username="office",
        )
        with college_context(college_a):
            assert Student.objects.count() == 1
            event = AuditEvent.objects.filter(action="create").latest("pk")
        assert event.actor == office

    def test_errors(self, tmp_path, college_a, core_a, office):
        path = tmp_path / "bad.xlsx"
        path.write_bytes(xlsx([good_row(1, Gender="x")]).read())
        out = StringIO()
        with pytest.raises(CommandError, match="Nothing was saved"):
            call_command(
                "import_students", str(path), college="alpha", stdout=out, username="office"
            )
        assert "Row 2, Gender" in out.getvalue()
        for kwargs, message in [
            ({"college": "nope", "username": "office"}, "No active college"),
            ({"college": "alpha", "username": "ghost"}, "is not a user"),
            ({"college": "alpha", "username": "office", "mapping": "none"}, "No saved layout"),
        ]:
            with pytest.raises(CommandError, match=message):
                call_command("import_students", str(path), **kwargs)
        with pytest.raises(CommandError, match="is not a file"):
            call_command("import_students", "/nope.xlsx", college="alpha", username="office")

"""Excel import of existing students (D22).

Every row is checked first. Nothing is saved unless every row passes, and then everything is
saved in one transaction, one row at a time so the audit log records each student.
The uploaded file is read in memory and never stored.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.academics.models import Semester
from apps.accounts.models import RoleAssignment, User
from apps.accounts.permissions import has_perm
from apps.accounts.roles import Role

from . import config, crypto
from .models import (
    AdmissionType,
    Batch,
    Gender,
    Guardian,
    ImportMapping,
    ImportRun,
    Residence,
    Section,
    Student,
)
from .promotion import place
from .validators import mobile_validator, normalise_aadhaar, pincode_validator

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Column:
    field: str
    header: str
    required: bool = False
    help: str = ""


COLUMNS = [
    Column("roll_number", "Roll number", True),
    Column("admission_number", "Admission number", True),
    Column("register_number", "Register number"),
    Column("name", "Name", True, "As in the 12th mark sheet"),
    Column("initials", "Initials"),
    Column("gender", "Gender", True, "male, female or transgender"),
    Column("date_of_birth", "Date of birth", help="A date cell, or DD-MM-YYYY"),
    Column("programme", "Programme code", True, "e.g. BE-CSE"),
    Column("batch_year", "Batch year", True, "The year the batch joined, e.g. 2025"),
    Column("section", "Section", True, "e.g. A"),
    Column("semester_number", "Current semester", True, "The semester studied this term"),
    Column("admission_type", "Admission type", help="regular, lateral or transfer"),
    Column("community", "Community", help="A community code"),
    Column("caste", "Caste"),
    Column("religion", "Religion"),
    Column("quota", "Quota", help="A quota code"),
    Column("is_first_graduate", "First graduate", help="yes or no"),
    Column("is_govt_school_student", "Government school student", help="yes or no"),
    Column("residence", "Residence", help="day_scholar or hostel"),
    Column("mobile", "Mobile"),
    Column("email", "Email"),
    Column("communication_address", "Address"),
    Column("pincode", "PIN code"),
    Column("qualifying_percent", "12th or diploma percentage"),
    Column("emis_id", "EMIS ID"),
    Column("umis_id", "UMIS ID"),
    Column("aadhaar", "Aadhaar number", help="Stored encrypted"),
    Column("father_name", "Father name"),
    Column("father_mobile", "Father mobile"),
    Column("mother_name", "Mother name"),
]
BY_FIELD = {c.field: c for c in COLUMNS}


@dataclass
class Result:
    rows: list[dict] = field(default_factory=list)
    errors: list[list] = field(default_factory=list)  # [row number, header, message]

    def error(self, row: int, field_name: str, message: str) -> None:
        header = BY_FIELD[field_name].header if field_name in BY_FIELD else field_name
        self.errors.append([row, header, message])


def template(college) -> bytes:
    """An empty workbook with the college's columns and a sheet of allowed values."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    from apps.academics.models import Programme

    book = Workbook()
    sheet = book.active
    sheet.title = "Students"
    sheet.append([c.header for c in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    help_sheet = book.create_sheet("Allowed values")
    help_sheet.append(["Column", "Required", "Allowed values or notes"])
    lists = {
        "gender": ", ".join(Gender.values),
        "community": ", ".join(code for code, _ in config.setting(college, "communities")),
        "quota": ", ".join(code for code, _ in config.setting(college, "quotas")),
        "programme": ", ".join(Programme.objects.values_list("code", flat=True)),
        "admission_type": ", ".join(AdmissionType.values),
        "residence": ", ".join(Residence.values),
    }
    for column in COLUMNS:
        help_sheet.append(
            [column.header, "yes" if column.required else "", lists.get(column.field, column.help)]
        )
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def read(upload, mapping: ImportMapping | None = None) -> tuple[list[dict], list[list]]:
    """Rows of {field: value} from the first sheet, plus header problems."""
    from openpyxl import load_workbook

    if upload.size > MAX_BYTES:
        return [], [[0, "File", "The file is larger than 5 MB."]]
    try:
        book = load_workbook(upload, read_only=True, data_only=True)
    except Exception:  # openpyxl raises many types for a bad file
        return [], [[0, "File", "This is not an Excel (.xlsx) file."]]
    sheet = book.worksheets[0]
    lines = sheet.iter_rows(values_only=True)
    headers = next(lines, None) or ()
    lookup = {c.header.lower(): c.field for c in COLUMNS} | {c.field: c.field for c in COLUMNS}
    if mapping is not None:
        lookup |= {str(k).strip().lower(): v for k, v in mapping.mapping.items()}
    positions = {}
    for index, header in enumerate(headers):
        name = lookup.get(str(header or "").strip().lower())
        if name in BY_FIELD:
            positions[name] = index
    problems = [
        [1, c.header, "This required column is missing."]
        for c in COLUMNS
        if c.required and c.field not in positions
    ]
    rows = []
    for line in lines:
        if line is None or all(v in (None, "") for v in line):
            continue
        rows.append({f: line[i] if i < len(line) else None for f, i in positions.items()})
        if len(rows) > MAX_ROWS:
            return [], [[0, "File", f"Import at most {MAX_ROWS} rows at a time."]]
    book.close()
    return rows, problems


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _yes(value) -> bool:
    return _text(value).lower() in {"yes", "y", "true", "1"}


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(_text(value), fmt).date()
        except ValueError:
            continue
    raise ValidationError("Use DD-MM-YYYY.")


def check(college, raw_rows: list[dict], term: Semester | None) -> Result:
    """Check every row. Clean rows hold ready values; errors name the row and column."""
    result = Result()
    if term is None:
        result.error(0, "Term", "Set the current term under Academics first.")
        return result
    batches = {
        (b.programme.code.upper(), b.admission_year.start_date.year): b
        for b in Batch.objects.select_related("programme", "admission_year")
    }
    sections = {(s.batch_id, s.name.upper()): s for s in Section.objects.all()}
    known = {
        "community": {c.upper(): c for c in config.codes(college, "communities")},
        "quota": {c.upper(): c for c in config.codes(college, "quotas")},
    }
    taken_rolls = set(Student.objects.values_list("roll_number", flat=True))
    taken_admissions = set(Student.objects.values_list("admission_number", flat=True))
    taken_registers = set(
        Student.objects.exclude(register_number="").values_list("register_number", flat=True)
    )
    taken_aadhaar = set(
        Student.objects.exclude(aadhaar_hash="").values_list("aadhaar_hash", flat=True)
    )
    taken_users = set(User.objects.filter(college=college).values_list("username", flat=True))
    seen: dict[str, set] = {"roll": set(), "admission": set(), "register": set(), "aadhaar": set()}

    for number, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        before = len(result.errors)
        row = {name: _text(raw.get(name)) for name in BY_FIELD}

        for column in COLUMNS:
            if column.required and not row[column.field]:
                result.error(number, column.field, "Required.")

        roll = row["roll_number"]
        if roll and (roll in taken_rolls or roll in taken_users):
            result.error(number, "roll_number", f"{roll} already exists.")
        elif roll in seen["roll"]:
            result.error(number, "roll_number", f"{roll} appears twice in this file.")
        seen["roll"].add(roll)
        admission = row["admission_number"]
        if admission and admission in taken_admissions | seen["admission"]:
            result.error(number, "admission_number", f"{admission} already exists.")
        seen["admission"].add(admission)
        register = row["register_number"]
        if register and register in taken_registers | seen["register"]:
            result.error(number, "register_number", f"{register} already exists.")
        if register:
            seen["register"].add(register)

        gender = row["gender"].lower()
        if gender and gender not in Gender.values:
            result.error(number, "gender", f"{row['gender']} is not male, female or transgender.")
        for name, allowed in known.items():
            if row[name] and row[name].upper() not in allowed:
                result.error(number, name, f"{row[name]} is not a known {name}.")
        admission_type = row["admission_type"].lower() or AdmissionType.REGULAR
        if admission_type not in AdmissionType.values:
            result.error(number, "admission_type", f"{row['admission_type']} is not allowed.")
        residence = row["residence"].lower().replace(" ", "_") or Residence.DAY_SCHOLAR
        if residence not in Residence.values:
            result.error(number, "residence", f"{row['residence']} is not allowed.")

        for name, validator in [
            ("mobile", mobile_validator),
            ("father_mobile", mobile_validator),
            ("pincode", pincode_validator),
        ]:
            if row[name]:
                try:
                    validator(row[name])
                except ValidationError as error:
                    result.error(number, name, error.messages[0])
        try:
            birth = _date(raw.get("date_of_birth"))
        except ValidationError as error:
            result.error(number, "date_of_birth", error.messages[0])
            birth = None
        percent = None
        if row["qualifying_percent"]:
            try:
                percent = Decimal(row["qualifying_percent"])
                if not 0 <= percent <= 100:
                    raise InvalidOperation
            except InvalidOperation:
                result.error(number, "qualifying_percent", "Enter a number from 0 to 100.")
        aadhaar = ""
        if row["aadhaar"]:
            try:
                aadhaar = normalise_aadhaar(row["aadhaar"])
            except ValidationError as error:
                result.error(number, "aadhaar", error.messages[0])
            else:
                hashed = crypto.keyed_hash(aadhaar)
                if hashed in taken_aadhaar | seen["aadhaar"]:
                    result.error(number, "aadhaar", "Another student has this Aadhaar.")
                seen["aadhaar"].add(hashed)

        batch = section = None
        if row["programme"] and row["batch_year"]:
            try:
                year = int(row["batch_year"])
            except ValueError:
                year = None
            batch = batches.get((row["programme"].upper(), year))
            if batch is None:
                result.error(
                    number,
                    "batch_year",
                    f"There is no {row['programme']} batch that joined in {row['batch_year']}.",
                )
        if batch is not None and row["section"]:
            section = sections.get((batch.pk, row["section"].upper()))
            if section is None:
                result.error(number, "section", f"{batch} has no section {row['section']}.")
        semester_number = None
        if row["semester_number"]:
            try:
                semester_number = int(row["semester_number"])
            except ValueError:
                result.error(number, "semester_number", "Enter a whole number.")
        if batch is not None and semester_number is not None:
            allowed = term.semester_numbers(batch.programme.total_semesters)
            if semester_number not in allowed:
                result.error(
                    number,
                    "semester_number",
                    f"In the {term.get_term_display().lower()} term this batch can be in "
                    f"semester {', '.join(map(str, allowed))}.",
                )

        if len(result.errors) == before:
            result.rows.append(
                row
                | {
                    "number": number,
                    "gender": gender,
                    "community": known["community"].get(row["community"].upper(), ""),
                    "quota": known["quota"].get(row["quota"].upper(), ""),
                    "admission_type": admission_type,
                    "residence": residence,
                    "date_of_birth": birth,
                    "qualifying_percent": percent,
                    "aadhaar": aadhaar,
                    "batch": batch,
                    "section": section,
                    "semester_number": semester_number,
                }
            )
    return result


STUDENT_FIELDS = [
    "roll_number",
    "admission_number",
    "register_number",
    "name",
    "initials",
    "gender",
    "date_of_birth",
    "admission_type",
    "community",
    "caste",
    "religion",
    "quota",
    "residence",
    "mobile",
    "email",
    "communication_address",
    "pincode",
    "qualifying_percent",
    "emis_id",
    "umis_id",
]


def _save(row: dict, college, term: Semester) -> Student:
    lateral = row["admission_type"] == AdmissionType.LATERAL
    student = Student(
        batch=row["batch"],
        entry_semester=3 if lateral else 1,
        is_first_graduate=_yes(row["is_first_graduate"]),
        is_govt_school_student=_yes(row["is_govt_school_student"]),
        **{name: row[name] for name in STUDENT_FIELDS},
    )
    if row["aadhaar"]:
        student.set_secret("aadhaar", row["aadhaar"])
    student.save()
    login = User.objects.create_user(
        student.roll_number, None, college=college, full_name=student.display_name
    )
    RoleAssignment.objects.create(user=login, role=Role.STUDENT)
    student.user = login
    student.save()
    if row["father_name"]:
        Guardian.objects.create(
            student=student,
            relation=Guardian.Relation.FATHER,
            name=row["father_name"],
            mobile=row["father_mobile"],
            is_primary=True,
        )
    if row["mother_name"]:
        Guardian.objects.create(
            student=student,
            relation=Guardian.Relation.MOTHER,
            name=row["mother_name"],
            is_primary=not row["father_name"],
        )
    place(student, term, row["section"], row["semester_number"])
    return student


def run(user, upload, *, mapping: ImportMapping | None = None, commit: bool) -> ImportRun:
    """Check the file and, when ``commit`` and every row passes, save it all at once."""
    if not has_perm(user, "students.import_students"):
        raise PermissionDenied
    college = user.college
    term = Semester.objects.filter(is_current=True).first()
    raw_rows, problems = read(upload, mapping)
    result = Result(errors=problems) if problems else check(college, raw_rows, term)
    status = ImportRun.Status.CHECKED
    created = 0
    if result.errors:
        status = ImportRun.Status.FAILED
    elif commit:
        with transaction.atomic():
            for row in result.rows:
                _save(row, college, term)
                created += 1
        status = ImportRun.Status.IMPORTED
    return ImportRun.objects.create(
        uploaded_by=user,
        file_name=getattr(upload, "name", "upload.xlsx")[:200],
        mapping=mapping,
        row_count=len(raw_rows),
        created_count=created,
        status=status,
        errors=result.errors[:500],
    )

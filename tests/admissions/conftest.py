import pytest

from apps.admissions.models import Application, Intake
from apps.students.fakes import fake_aadhaar
from apps.tenancy.context import college_context
from tests.students.conftest import build_batches


@pytest.fixture
def core_a(college_a):
    return build_batches(college_a, "Alpha ")


@pytest.fixture
def core_b(college_b):
    return build_batches(college_b, "Beta ")


@pytest.fixture
def office(college_a, make_user):
    from apps.accounts.roles import Role

    return make_user(college_a, "office", roles=[Role.OFFICE])


@pytest.fixture
def intake(college_a, core_a):
    with college_context(college_a):
        return Intake.objects.create(
            academic_year=core_a["year"],
            programme=core_a["be_cse"],
            quota="GOVT",
            sanctioned_seats=2,
        )


@pytest.fixture
def make_application():
    def _make(core, serial=1, *, programme="be_cse", **fields):
        defaults = {
            "academic_year": core["year"],
            "programme": core[programme],
            "name": f"APPLICANT {serial}",
            "gender": "male",
            "community": "MBC",
            "quota": "GOVT",
            "qualifying_percent": 80,
            "father_name": f"FATHER {serial}",
            "mother_name": f"MOTHER {serial}",
            "guardian_mobile": "9876500000",
        }
        with college_context(core["year"].college):
            application = Application(**(defaults | fields))
            application.set_secret("aadhaar", fake_aadhaar(9000 + serial))
            application.set_secret("annual_income", "90000")
            application.save()
        return application

    return _make


ALL_DOCUMENTS = {"TC": True, "SSLC": True, "HSC": True, "COMMUNITY": True}

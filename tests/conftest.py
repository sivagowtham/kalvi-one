import pytest

from apps.tenancy.models import College


@pytest.fixture
def college_a(db):
    return College.objects.create(
        name="Alpha College of Engineering",
        code="ACE",
        slug="alpha",
        college_type=College.CollegeType.ENGINEERING,
    )


@pytest.fixture
def college_b(db):
    return College.objects.create(
        name="Beta College of Arts and Science",
        code="BCAS",
        slug="beta",
        college_type=College.CollegeType.ARTS_SCIENCE,
    )

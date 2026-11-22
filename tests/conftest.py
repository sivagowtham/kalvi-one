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


@pytest.fixture
def make_user(db):
    """Create a college user with roles: make_user(college, "name", roles=[Role.FACULTY])."""
    from apps.accounts.models import RoleAssignment, User

    def _make(college, username, *, roles=(), password="correct-horse-1", is_staff=True, **extra):
        user = User.objects.create_user(
            username, password, college=college, is_staff=is_staff, **extra
        )
        for role in roles:
            RoleAssignment.all_colleges.create(user=user, role=role)
        return user

    return _make

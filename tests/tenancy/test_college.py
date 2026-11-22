import pytest
from django.core.exceptions import ValidationError

from apps.tenancy.models import College, CollegeFeature

pytestmark = pytest.mark.django_db


def test_feature_flags_are_per_college(college_a, college_b):
    CollegeFeature.objects.create(college=college_a, key="cbcs-grading", enabled=True)
    CollegeFeature.objects.create(college=college_b, key="cbcs-grading", enabled=False)
    assert college_a.has_feature("cbcs-grading")
    assert not college_b.has_feature("cbcs-grading")
    assert not college_a.has_feature("never-defined")


@pytest.mark.parametrize("slug", ["www", "admin", "Bad", "-edge", "has space", "a.b"])
def test_invalid_or_reserved_slugs_are_rejected(slug):
    college = College(name="X", code="X1", slug=slug, college_type="engineering")
    with pytest.raises(ValidationError):
        college.full_clean()


def test_valid_slug_passes(db):
    college = College(name="X", code="X1", slug="pie-tech", college_type="engineering")
    college.full_clean()
    assert str(college) == "X"


def test_feature_str(college_a):
    feature = CollegeFeature.objects.create(college=college_a, key="hostel", enabled=True)
    assert str(feature) == "ACE:hostel=on"

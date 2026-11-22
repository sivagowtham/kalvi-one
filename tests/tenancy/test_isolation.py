"""Cross-college isolation for TenantModel (D4)."""

import pytest

from apps.tenancy.context import (
    CrossCollegeError,
    NoCollegeSelected,
    college_context,
    get_current_college,
)
from tests.testapp.models import Gadget, Widget

pytestmark = pytest.mark.django_db


@pytest.fixture
def widgets(college_a, college_b):
    with college_context(college_a):
        a1 = Widget.objects.create(name="a-one")
        a2 = Widget.objects.create(name="a-two")
    with college_context(college_b):
        b1 = Widget.objects.create(name="b-one")
    return {"a1": a1, "a2": a2, "b1": b1}


def test_each_college_sees_only_its_own_rows(college_a, college_b, widgets):
    with college_context(college_a):
        assert set(Widget.objects.values_list("name", flat=True)) == {"a-one", "a-two"}
    with college_context(college_b):
        assert list(Widget.objects.values_list("name", flat=True)) == ["b-one"]


def test_get_by_pk_of_other_college_is_not_found(college_a, widgets):
    with college_context(college_a), pytest.raises(Widget.DoesNotExist):
        Widget.objects.get(pk=widgets["b1"].pk)


def test_query_without_college_fails_closed(widgets):
    assert get_current_college() is None
    with pytest.raises(NoCollegeSelected):
        Widget.objects.all()
    with pytest.raises(NoCollegeSelected):
        Widget.objects.count()


def test_all_colleges_manager_is_unfiltered(widgets):
    assert Widget.all_colleges.count() == 3


def test_save_takes_college_from_context(college_a):
    with college_context(college_a):
        widget = Widget.objects.create(name="auto")
    assert widget.college == college_a


def test_save_without_college_fails_closed(db):
    with pytest.raises(NoCollegeSelected):
        Widget.objects.create(name="orphan")


def test_cannot_save_row_of_another_college(college_a, college_b, widgets):
    with college_context(college_a):
        b1 = Widget.all_colleges.get(pk=widgets["b1"].pk)
        b1.name = "hijacked"
        with pytest.raises(CrossCollegeError):
            b1.save()


def test_cannot_move_row_to_another_college(college_b, widgets):
    a1 = widgets["a1"]
    a1.college = college_b
    with pytest.raises(CrossCollegeError):
        a1.save()  # no context: the stored-college check still applies


def test_foreign_key_to_other_college_is_refused(college_a, widgets):
    with college_context(college_a), pytest.raises(CrossCollegeError):
        Gadget.objects.create(widget=widgets["b1"], label="bad")


def test_foreign_key_within_college_is_allowed(college_a, widgets):
    with college_context(college_a):
        gadget = Gadget.objects.create(widget=widgets["a1"], label="ok")
        assert list(widgets["a1"].gadgets.all()) == [gadget]


def test_same_name_allowed_in_different_colleges(college_a, college_b):
    with college_context(college_a):
        Widget.objects.create(name="shared")
    with college_context(college_b):
        Widget.objects.create(name="shared")
    assert Widget.all_colleges.filter(name="shared").count() == 2


def test_bulk_create_sets_college_and_refuses_foreign_rows(college_a, college_b):
    with college_context(college_a):
        Widget.objects.bulk_create([Widget(name="x"), Widget(name="y")])
        assert Widget.objects.count() == 2
        with pytest.raises(CrossCollegeError):
            Widget.objects.bulk_create([Widget(name="z", college=college_b)])


def test_bulk_create_without_college_fails_closed(db):
    with pytest.raises(NoCollegeSelected):
        Widget.all_colleges.bulk_create([Widget(name="x")])


def test_update_cannot_change_college(college_a, college_b, widgets):
    with college_context(college_a):
        with pytest.raises(CrossCollegeError):
            Widget.objects.update(college=college_b)
        # A plain update is fine and touches only this college's rows.
        assert Widget.objects.filter(name="a-one").update(name="renamed") == 1
    assert Widget.all_colleges.filter(name="renamed").count() == 1


def test_context_nests_and_restores(college_a, college_b):
    with college_context(college_a):
        with college_context(college_b):
            assert get_current_college() == college_b
        assert get_current_college() == college_a
    assert get_current_college() is None

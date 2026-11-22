"""The audit log records who changed what and when (D8)."""

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role
from apps.audit.bulk import audited_update
from apps.audit.context import audit_context
from apps.audit.mixins import AuditBypassError
from apps.audit.models import AuditEvent, ImmutableError
from apps.tenancy.context import NoCollegeSelected, college_context
from tests.testapp.models import Gadget, Widget

pytestmark = pytest.mark.django_db
Action = AuditEvent.Action


def events_for(obj):
    return AuditEvent.all_colleges.filter(
        content_type=ContentType.objects.get_for_model(type(obj)), object_id=str(obj.pk)
    ).order_by("id")


@pytest.fixture
def widget(college_a):
    with college_context(college_a):
        return Widget.objects.create(name="w")


@pytest.fixture
def teacher(college_a, make_user):
    return make_user(college_a, "teacher", roles=[Role.FACULTY])


def test_create_update_delete_are_recorded_with_actor_and_changes(college_a, widget, teacher):
    with college_context(college_a), audit_context(actor_id=teacher.pk, actor_label="teacher"):
        gadget = Gadget.objects.create(widget=widget, label="first")
        gadget.label = "second"
        gadget.save()
        gadget_id = gadget.pk
        gadget.delete()
    gadget.pk = gadget_id
    create, update, delete = events_for(gadget)
    assert [create.action, update.action, delete.action] == [
        Action.CREATE,
        Action.UPDATE,
        Action.DELETE,
    ]
    assert {e.actor_id for e in (create, update, delete)} == {teacher.pk}
    assert create.changes["label"] == [None, "first"]
    assert update.changes == {"label": ["first", "second"]}
    assert delete.changes["label"] == ["second", None]
    assert create.college == college_a
    assert str(update) == "teacher updated second"


def test_save_without_changes_is_not_recorded(college_a, widget):
    with college_context(college_a):
        gadget = Gadget.objects.create(widget=widget, label="same")
        gadget.save()
    assert events_for(gadget).count() == 1


def test_masked_fields_never_store_values(college_a, widget):
    with college_context(college_a):
        gadget = Gadget.objects.create(widget=widget, label="g", secret="hunter2")
        gadget.secret = "hunter3"
        gadget.save()
    for event in events_for(gadget):
        assert "hunter" not in str(event.changes)
        assert event.changes["secret"] == ["***", "***"]


def test_passwords_never_appear_in_the_log(college_a, teacher):
    teacher.set_password("a-brand-new-password")
    teacher.save()
    update = events_for(teacher).filter(action=Action.UPDATE).get()
    assert update.changes == {"password": ["***", "***"]}
    for event in events_for(teacher):
        assert "md5$" not in str(event.changes)  # the test settings hash with MD5


def test_last_login_alone_is_not_an_update(college_a, teacher):
    before = events_for(teacher).count()
    User.objects.filter(pk=teacher.pk).first().save(update_fields=["last_login"])
    assert events_for(teacher).count() == before


def test_role_changes_are_audited(college_a, teacher):
    assignment = RoleAssignment.all_colleges.get(user=teacher)
    event = events_for(assignment).get()
    assert event.action == Action.CREATE
    assert event.changes["role"] == [None, "faculty"]


def test_events_are_visible_only_within_their_college(college_a, college_b):
    with college_context(college_a):
        Widget.objects.create(name="ignored")  # Widget is not audited
    with college_context(college_b):
        Gadget.objects.create(widget=Widget.objects.create(name="b"), label="beta-gadget")
    with college_context(college_a):
        assert not AuditEvent.objects.filter(object_repr="beta-gadget").exists()
    with college_context(college_b):
        assert AuditEvent.objects.filter(object_repr="beta-gadget").exists()
    with pytest.raises(NoCollegeSelected):
        AuditEvent.objects.count()


def test_audit_rows_are_immutable(college_a, widget):
    with college_context(college_a):
        Gadget.objects.create(widget=widget, label="g")
    event = AuditEvent.all_colleges.first()
    event.action = Action.DELETE
    with pytest.raises(ImmutableError):
        event.save()
    with pytest.raises(ImmutableError):
        event.delete()
    with pytest.raises(ImmutableError):
        AuditEvent.all_colleges.update(action=Action.DELETE)
    with pytest.raises(ImmutableError):
        AuditEvent.all_colleges.all().delete()
    with pytest.raises(ImmutableError):
        AuditEvent.all_colleges.bulk_update([event], ["action"])


def test_bulk_operations_that_skip_signals_are_refused(college_a, widget):
    with college_context(college_a):
        Gadget.objects.create(widget=widget, label="g")
        with pytest.raises(AuditBypassError):
            Gadget.objects.update(label="x")
        with pytest.raises(AuditBypassError):
            Gadget.objects.bulk_create([Gadget(widget=widget, label="y")])
        with pytest.raises(AuditBypassError):
            Gadget.objects.bulk_update(list(Gadget.objects.all()), ["label"])


def test_queryset_delete_is_still_audited(college_a, widget):
    with college_context(college_a):
        Gadget.objects.create(widget=widget, label="one")
        Gadget.objects.create(widget=widget, label="two")
        Gadget.objects.all().delete()
    assert AuditEvent.all_colleges.filter(action=Action.DELETE).count() == 2


def test_audited_update_helper_records_each_row(college_a, widget):
    with college_context(college_a):
        Gadget.objects.create(widget=widget, label="one")
        Gadget.objects.create(widget=widget, label="two")
        assert audited_update(Gadget.objects.all(), label="same") == 2
    assert AuditEvent.all_colleges.filter(action=Action.UPDATE).count() == 2


def test_college_changes_are_audited_against_that_college(college_a):
    college_a.name = "Alpha College of Engineering and Technology"
    college_a.save()
    event = events_for(college_a).filter(action=Action.UPDATE).get()
    assert event.college == college_a
    assert event.actor_label == "system"

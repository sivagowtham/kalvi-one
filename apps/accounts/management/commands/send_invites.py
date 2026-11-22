"""Email invite links to every account in one college that has never had a password (D25)."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts import links
from apps.accounts.models import User
from apps.accounts.roles import STAFF_ROLES, Role
from apps.audit.context import audit_context
from apps.tenancy.context import college_context
from apps.tenancy.models import College

GROUPS = {
    "staff": STAFF_ROLES,
    "students": frozenset({Role.STUDENT}),
    "parents": frozenset({Role.PARENT}),
}


class Command(BaseCommand):
    help = "Email invite links to accounts in one college that have no password yet."

    def add_arguments(self, parser):
        parser.add_argument("--college", required=True, help="The college slug.")
        parser.add_argument(
            "--as", dest="username", required=True, help="A principal or office user."
        )
        parser.add_argument("--only", choices=sorted(GROUPS), help="Invite only this group.")
        parser.add_argument("--send", action="store_true", help="Send. Without it, only count.")

    def handle(self, *args, college, username, only, send, **options):
        college_row = College.objects.filter(slug=college, is_active=True).first()
        if college_row is None:
            raise CommandError(f"No active college with slug {college!r}.")
        actor = User.objects.filter(college=college_row, username=username).first()
        if actor is None:
            raise CommandError(f"{username!r} is not a user of {college_row}.")
        with (
            college_context(college_row),
            audit_context(actor_id=actor.pk, actor_label=actor.username),
        ):
            if not actor.has_perm("accounts.invite_user"):
                raise CommandError(f"{username!r} may not send invites.")
            users = User.objects.filter(college=college_row, is_active=True).exclude(email="")
            if only:
                users = users.filter(role_assignments__role__in=GROUPS[only]).distinct()
            waiting = [user for user in users.order_by("username") if links.can_invite(user)]
            if not send:
                self.stdout.write(f"{len(waiting)} account(s) would get an invite. Add --send.")
                return
            sent = sum(links.send_invite(user) for user in waiting)
        self.stdout.write(f"Sent {sent} invite email(s) for {college_row}.")

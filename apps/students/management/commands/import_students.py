"""Import students from an Excel file on the server (D22), e.g. for a first data load."""

from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.audit.context import audit_context
from apps.students import importer
from apps.students.models import ImportMapping
from apps.tenancy.context import college_context
from apps.tenancy.models import College


class Command(BaseCommand):
    help = "Check, and with --commit import, students from an .xlsx file into one college."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--college", required=True, help="The college slug.")
        parser.add_argument(
            "--as", dest="username", required=True, help="A principal or office user."
        )
        parser.add_argument("--mapping", help="The name of a saved import layout.")
        parser.add_argument("--commit", action="store_true", help="Save when every row passes.")

    def handle(self, *args, path, college, username, mapping, commit, **options):
        college_row = College.objects.filter(slug=college, is_active=True).first()
        if college_row is None:
            raise CommandError(f"No active college with slug {college!r}.")
        user = User.objects.filter(college=college_row, username=username).first()
        if user is None:
            raise CommandError(f"{username!r} is not a user of {college_row}.")
        file = Path(path)
        if not file.is_file():
            raise CommandError(f"{path} is not a file.")
        upload = SimpleUploadedFile(file.name, file.read_bytes())
        actor = audit_context(actor_id=user.pk, actor_label=user.username)
        with college_context(college_row), actor:
            layout = ImportMapping.objects.filter(name=mapping).first() if mapping else None
            if mapping and layout is None:
                raise CommandError(f"No saved layout named {mapping!r}.")
            run = importer.run(user, upload, mapping=layout, commit=commit)
        for row, column, message in run.errors:
            self.stdout.write(f"Row {row}, {column}: {message}")
        self.stdout.write(
            f"{run.get_status_display()}: {run.row_count} rows, {run.created_count} imported."
        )
        if run.errors:
            raise CommandError("Nothing was saved.")

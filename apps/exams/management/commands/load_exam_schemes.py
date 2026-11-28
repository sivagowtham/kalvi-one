"""Load a starting set of assessment schemes and grades into one college (D52)."""

from django.core.management.base import BaseCommand, CommandError

from apps.audit.context import audit_context
from apps.exams import presets
from apps.tenancy.context import college_context
from apps.tenancy.models import College


class Command(BaseCommand):
    help = "Load starting assessment schemes and a grade scale for a regulation into a college."

    def add_arguments(self, parser):
        parser.add_argument("preset", choices=sorted(presets.PRESETS))
        parser.add_argument("--college", required=True, help="The college slug.")

    def handle(self, *args, preset, college, **options):
        college_row = College.objects.filter(slug=college, is_active=True).first()
        if college_row is None:
            raise CommandError(f"No active college with slug {college!r}.")
        with college_context(college_row), audit_context(actor_label="load_exam_schemes"):
            result = presets.load(preset)
        self.stdout.write(f"{presets.PRESETS[preset]['label']} for {college_row}:")
        for code in result["added"]:
            self.stdout.write(f"  added {code}")
        for code in result["skipped"]:
            self.stdout.write(f"  already there, left as it is: {code}")
        self.stdout.write("Check every number against the college's regulation copy before use.")

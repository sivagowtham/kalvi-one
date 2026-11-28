from apps.accounts.permissions import register
from apps.accounts.roles import Role

READERS = [Role.PRINCIPAL, Role.HOD, Role.FACULTY, Role.OFFICE, Role.EXAM_CELL]

register("timetable.view", READERS, "See your own timetable and section timetables")

# College-wide set-up (D35): the principal owns the bell schedules and the calendar.
for model, label in [
    ("bellschedule", "bell schedules"),
    ("periodslot", "period timings"),
    ("scheduleprogramme", "programmes on a bell schedule"),
    ("calendarday", "calendar days"),
]:
    register(f"timetable.view_{model}", READERS, f"See {label}")
    for action in ["add", "change", "delete"]:
        register(f"timetable.{action}_{model}", [Role.PRINCIPAL], f"{action} {label}")
register("timetable.fill_calendar", [Role.PRINCIPAL], "Fill in a term's calendar and day orders")

# Department-level (D14, D36): HODs plan their own department's teaching.
for model, label in [
    ("labgroup", "lab groups"),
    ("labgroupmember", "lab group members"),
    ("allocation", "teaching allocations"),
    ("allocationteacher", "teachers of an allocation"),
    ("allocationstudent", "elective rosters"),
    ("timetableentry", "timetable entries"),
]:
    register(f"timetable.view_{model}", READERS, f"See {label}")
    for action in ["add", "change", "delete"]:
        register(
            f"timetable.{action}_{model}",
            [Role.PRINCIPAL, Role.HOD],
            f"{action} {label}",
            department_scoped=True,
        )

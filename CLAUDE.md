# KalviOne: notes for contributors and AI assistants

- KalviOne is a multi-tenant college ERP. Read `docs/decisions.md` before changing architecture, and add a new entry for every new architecture decision in the same PR.
- Foundation phase only: do not add domain modules (marks, attendance, fees, timetable, admissions) until the brief says so.
- One codebase for all colleges (D1). Never branch on a specific college in code; use configuration or a feature flag.
- Only fake data, everywhere (D10).
- Tests run on PostgreSQL (D5). Run `make check` before opening a PR. CI must be green.
- Style: ruff with line length 100. Settings come from environment variables via django-environ.
- Every college-owned model extends `apps.tenancy.models.TenantModel` and gets isolation tests (D4, D12). Treat `all_colleges` and raw SQL as review flags.

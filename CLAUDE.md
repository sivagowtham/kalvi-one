# KalviOne: notes for contributors and AI assistants

- KalviOne is a multi-tenant college ERP. Read `docs/decisions.md` before changing architecture, and add a new entry for every new architecture decision in the same PR.
- The foundation is done. Students and Admissions is the first domain module (D16) and Fees the second (D26); attendance and timetable (from D34) and Exams and marks (D50) are being built; their plans are agreed. Do not start other domain modules until Gowtham approves a plan for them.
- Exam schemes, grade scales and anything results point at are locked once used; change them on a copy (D51).
- One codebase for all colleges (D1). Never branch on a specific college in code; use configuration or a feature flag.
- Only fake data, everywhere (D10).
- Tests run on PostgreSQL (D5). Run `make check` before opening a PR. CI must be green.
- Style: ruff with line length 100. Settings come from environment variables via django-environ.
- Every college-owned model extends `apps.tenancy.models.TenantModel` and gets isolation tests (D4, D12). Treat `all_colleges` and raw SQL as review flags.
- Every view needs `@require_perm("code")` or `@public` (D7); register new codes in the app's `grants.py`. The default-deny test fails otherwise.
- Models holding college data mix in `apps.audit.mixins.Audited` (D8). Never bypass it with queryset `update()`/`bulk_*` or raw SQL; use `apps.audit.bulk.audited_update()`.
- Sensitive personal data (Aadhaar, community certificate number, income) is encrypted per field (D18). Write it with `set_secret()` and read it only with `reveal()`, which checks `students.view_sensitive` and audits the read (D19). Never log or display ciphertext or decrypted values elsewhere.
- Every per-college setting (a config key, feature flag or set-up data a college must give) gets a question with its default in `docs/onboarding-questionnaire.md` in the same PR, and the Word copy in the project files is rebuilt from it.

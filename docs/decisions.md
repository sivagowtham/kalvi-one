# Architecture decisions

Every architecture decision for KalviOne is recorded here with its reasons.

How to use this file:

- Add an entry in the same pull request that makes the decision.
- Never edit or delete an accepted decision. To change one, add a new entry and mark the old one "Superseded by Dn".
- Keep entries short: context, decision, alternatives, consequences.

| # | Decision | Status |
| --- | --- | --- |
| D1 | One multi-tenant codebase; college differences are configuration and feature flags | Accepted |
| D2 | SaaS with a subdomain per college, plus optional dedicated deployment | Accepted |
| D3 | Working product name KalviOne, repo `kalvi-one` | Accepted |
| D4 | Shared database and schema, college column on every college-owned row | Accepted |
| D5 | Python 3.13, Django 5.2 LTS, PostgreSQL 17 | Accepted |
| D6 | Custom user model from the first migration; each user belongs to one college, platform staff to none | Accepted |
| D7 | Fixed roles in code, assignments in the database, one permission registry, default deny enforced by a test | Accepted |
| D8 | Custom append-only audit log written from model signals, in the same database | Accepted |
| D9 | A semester is an odd or even term of an academic year | Accepted |
| D10 | Only fake data in the repo, seeds and CI | Accepted |
| D11 | Tooling: uv, ruff, pytest-django, factory_boy, GitHub Actions | Accepted |
| D12 | Current college resolved from the host and held in a context variable; tenant queries fail closed | Accepted |
| D13 | Per-college configuration in a JSON field, rare needs as per-college feature flags | Accepted |
| D14 | HOD permissions stop at their own department, checked per object | Accepted |
| D15 | Minimal academic core: Course is a subject in one programme, regulation is text | Accepted |
| D16 | Students and Admissions is the first domain module, built before the staff survey results | Accepted |
| D17 | A batch is one programme's intake in one year; sections belong to a batch and placement is recorded per term | Accepted |
| D18 | Sensitive personal fields are encrypted per field, masked by default, and need their own permission | Accepted |
| D19 | Revealing an encrypted field is audited (adds to D8) | Accepted |
| D20 | Community, quota and document lists and the roll number pattern are per-college config with Tamil Nadu defaults | Accepted |
| D21 | Admissions use a fixed status flow; enrolment is one transaction that creates the student, login, guardians, consent and first placement | Accepted |
| D22 | Excel import checks every row before saving anything, then saves all rows in one transaction; the file is never stored | Accepted |
| D23 | Each college has its own login page; logins pause after repeated wrong passwords, counted from the audit log | Accepted |
| D24 | Forgotten passwords are reset through a one-time emailed link on the college's own address; the reply never says whether an account exists | Accepted |
| D25 | New accounts get an invite email with a 7-day link to choose their first password, sent from admin or a command | Accepted |
| D26 | Fees is the second domain module; Tally gets a daily XML file of receipt vouchers first, live sync later | Accepted |
| D27 | Fee heads carry their Tally ledger and GST rate; a fee structure is one batch's year, split into instalments | Accepted |
| D28 | Dues are raised per student, head and instalment; concessions count once the principal approves, split into college and government shares | Accepted |
| D29 | Receipts are taken on a phone-first counter page, settle the oldest dues first, are numbered per financial year and are cancelled, never deleted | Accepted |

---

## D1. One multi-tenant codebase for all colleges

- **Date:** 2026-11-22
- **Status:** Accepted (agreed by Gowtham)
- **Context:** KalviOne will serve the trust's own colleges first and then be sold to other colleges. Colleges differ in grading schemes, fee heads, regulation year, affiliating university, and whether they are autonomous or affiliated.
- **Decision:** There is one codebase and one product. Per-college differences are data and configuration on the College record. The rare needs that only some colleges have go behind per-college feature flags. Per-college forks or branches are never used.
- **Alternatives:** A fork per college (fast at first, but every fix must be repeated for each college); a separate product for engineering and for arts and science (doubles the maintenance).
- **Consequences:** Any code that would branch on a specific college must use configuration or a feature flag instead. Reviewers reject `if college.code == "..."` style checks.

## D2. SaaS with a subdomain per college, plus optional dedicated deployment

- **Date:** 2026-11-22
- **Status:** Accepted (agreed by Gowtham)
- **Context:** Most colleges want a hosted service, but some may require their own server for policy or data reasons.
- **Decision:** The main offering is hosted SaaS. Each college is reached on its own subdomain, and the subdomain decides which college a request belongs to. The same code can also be deployed for a single college on a dedicated server, with no code changes.
- **Alternatives:** One shared login page with a college picker (more confusing for users, and easier to log into the wrong college); on-premise installs only (expensive to support).
- **Consequences:** Tenant resolution must work from the request host. A dedicated deployment is just an instance with one College row.

## D3. Working product name

- **Date:** 2026-11-22
- **Status:** Accepted (agreed by Gowtham, "for now")
- **Decision:** The product is called KalviOne ("kalvi" means education in Tamil). The repository is `kalvi-one`, and the Python project is `kalvione`.
- **Consequences:** If the name changes later, only user-facing text and the domain change. Module and app names do not include the product name, so they stay as they are.

## D4. Shared database, shared schema, college column on every row

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** D1 needs strong isolation between colleges. Isolation can live at the database level (a database or schema per college) or the row level (a college column).
- **Decision:** Use one PostgreSQL database and one schema. Every college-owned table has a required `college` foreign key. A tenant-aware base model and manager filter every query to the current college, and they fail closed: a query with no current college raises an error instead of returning everything. Cross-college isolation is covered by tests.
- **Alternatives:**
  - Schema per college (for example django-tenants): strong isolation, but migrations run once per college, connection handling is more complex, and trust-wide reports are harder.
  - Database per college: strongest isolation, highest operating cost.
- **Consequences:** Migrations are simple and the design scales to hundreds of colleges. A missed filter is the main risk, so the base manager must be used everywhere, and the isolation tests are mandatory for every new tenant model. PostgreSQL row-level security can be added later as a second guard without changing the data model.

## D5. Python 3.13, Django 5.2 LTS, PostgreSQL 17

- **Date:** 2026-11-22
- **Status:** Accepted
- **Decision:** Python 3.13, Django 5.2 LTS (security support until April 2028) and PostgreSQL 17 in Docker and CI. Tests always run against PostgreSQL, never SQLite.
- **Alternatives:** Django 6.x, which is newer but has a shorter support window than an LTS release; SQLite for tests, which is faster but hides PostgreSQL-specific behaviour such as constraints and JSON queries.
- **Consequences:** We plan an upgrade to the next Django LTS before April 2028. Developers need PostgreSQL to run tests, and `docker compose up db` provides it.

## D10. Only fake data in the repo, seeds and CI

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Student and staff records are personal data under India's Digital Personal Data Protection Act, 2023.
- **Decision:** No real names, phone numbers, emails, marks or other personal data ever go into the repository, fixtures, seed scripts, screenshots or CI logs. Seed data is generated with Faker.
- **Consequences:** Real college data is loaded only into deployed environments, through an import process to be designed later. The `seed_demo` command runs only where `ALLOW_DEMO_SEED` is true (dev and test settings, never prod). It uses `.example` email domains and Faker's Indian-English names with a fixed seed, so runs are repeatable.

## D11. Tooling

- **Date:** 2026-11-22
- **Status:** Accepted
- **Decision:**
  - uv for dependencies, with a committed `uv.lock`.
  - ruff for linting and formatting, with line length 100 and bandit security rules enabled.
  - pytest with pytest-django, factory_boy and coverage.
  - GitHub Actions CI with three jobs: lint, tests against a PostgreSQL 17 service, and a Docker image build.
- **Alternatives:** pip-tools or Poetry (slower, more configuration); black, flake8 and isort as separate tools (ruff replaces all three).
- **Consequences:** A pull request merges only when all three CI jobs pass.

## D12. How the current college is resolved and enforced

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** D2 serves each college on its own subdomain, and D4 needs every query filtered to one college without relying on developers to remember the filter.
- **Decision:**
  - `TenantMiddleware` reads the request host. `<slug>.<base domain>` serves the active college with that slug. Hosts listed in `TENANT_PLATFORM_HOSTS` serve the platform with no college. Every other host, unknown slug or inactive college gets a 404.
  - `TENANT_DEDICATED_COLLEGE_SLUG` makes one instance serve a single college on every host, for the dedicated deployment in D2.
  - The current college lives in a `ContextVar`, which is isolated per thread and per asyncio task. The middleware sets it for each request and clears it afterwards. Scripts and tests use `with college_context(college):`.
  - `TenantModel` is the base for every college-owned model. Its default manager filters to the current college and raises `NoCollegeSelected` when none is set. The `all_colleges` manager is the explicit, unfiltered escape hatch.
  - Saving takes the college from the context. Saving or linking a row across colleges raises `CrossCollegeError`, and so does changing a row's college, including through `bulk_create` and `update`.
- **Alternatives:** Thread-local storage, which is not safe with async code; passing the college explicitly to every query, which is easy to forget; `django-tenants` or `django-multitenant`, which add a dependency for the small amount of code needed here.
- **Consequences:** Code outside a request (management commands, background jobs) must set a college or use `all_colleges` deliberately, and reviewers treat any use of `all_colleges` as a flag. Raw SQL bypasses the manager and must filter on `college_id` by hand. Row-level security in PostgreSQL remains a possible second guard.

## D13. Per-college configuration and feature flags

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** D1 says college differences are configuration, never forks.
- **Decision:** `College.config` is a JSON field for structured settings such as the grading scheme or regulation year. Each key is owned and documented by the module that reads it. `CollegeFeature (college, key, enabled)` holds on/off switches, read with `college.has_feature("key")`. Fixed facts about a college that many modules read (type, autonomous or affiliated, affiliating university) are ordinary columns.
- **Alternatives:** A settings table per module (more tables, more migrations); a feature-flag library such as django-waffle (more than we need for per-college switches).
- **Consequences:** A config key that becomes important or needs validation is promoted to its own column or model through a decision entry.

## D6. Users belong to one college

- **Date:** 2026-11-22
- **Status:** Accepted (default for plan question 1, approved by Gowtham)
- **Context:** Swapping Django's user model after the first migration is painful. Every user must be tied to a college for D4 to hold.
- **Decision:**
  - Each user belongs to exactly one college, set in `accounts.User.college`, from the first migration.
  - Usernames are unique within a college, not across colleges. Staff use their email and students their roll number.
  - Platform staff have no college. Only they can be superusers, which a database constraint enforces, and they can log in only on platform hosts.
  - `CollegeBackend` looks a username up only in the current college, and re-checks the college on every request that uses a session. A session cookie copied to another college's subdomain is ignored.
- **Alternatives:** One account shared across colleges through a membership table. This is more flexible for trust administrators and faculty who teach at both colleges, but every check becomes harder. If that need is confirmed, a later decision can add a membership model.
- **Consequences:** A person working in two colleges has two accounts. `auth.W004` is silenced because usernames are deliberately not globally unique. The Django `Group` and per-user permission tables are not used.

## D7. Roles, permissions and default deny

- **Date:** 2026-11-22
- **Status:** Accepted
- **Decision:**
  - The roles (principal, HOD, faculty, office, accounts, exam cell, student, parent) are a fixed `Role` enum in code. `RoleAssignment` rows give users roles in their own college, and a user can hold several.
  - Each app declares its permissions in `grants.py` as `register(code, roles, description)`. Codes are Django model permissions such as `academics.change_department`, so Django admin works unchanged, or custom actions.
  - `has_perm(user, code)` is true only when one of the user's roles in the current college is granted the code. Unknown codes raise in our own code and are denied through Django's API.
  - Views use `@require_perm(code)` or `@public`. A test walks every URL and fails on any view with neither mark. Django admin is the one exception, because it checks `User.has_perm`, which uses the same registry.
  - Denied requests send a `permission_denied` signal, which the audit log will record.
- **Alternatives:** Django groups and permissions edited in admin. These are flexible, but access rules then live in the database where code review never sees them. django-guardian (object-level permissions) is more than we need now.
- **Consequences:** Changing who can do what is a code change, visible in review. Object-level rules, such as a HOD's scope stopping at their own department, are added per permission when the models exist (PR 5).

## D8. Audit log

- **Date:** 2026-11-22
- **Status:** Accepted (plan question 7: record changes, logins and denials, not reads; keep indefinitely)
- **Context:** Colleges need to know who changed what and when, for marks, fees and student records above all. The log must be trustworthy, and it must respect the college boundary.
- **Decision:**
  - `audit.AuditEvent` stores one row per event: college, actor (plus a username snapshot), action, object type and ID, object description, field changes as `{field: [before, after]}`, extra data, request ID, IP address, user agent and time.
  - The actions are create, update, delete, login, failed login, logout and permission denied.
  - A model opts in with the `Audited` mixin. Save and delete signals write the events. Saves that change nothing are skipped. `audit_exclude` drops noisy fields (`User.last_login`), and `audit_mask` records only that a field changed, never its value (`User.password`).
  - `AuditContextMiddleware` captures the actor, the request ID (taken from `X-Request-ID` or generated, and echoed in the response), the IP address and the user agent. Scripts set the same data with `audit_context(...)`.
  - Rows are append-only: save-after-create, delete, queryset update, delete and bulk_update all raise. Admin shows them read-only to the principal.
  - Bulk `update`, `bulk_create` and `bulk_update` skip Django's signals, so they are refused on audited tenant models. `audited_update()` is the deliberate bulk path. A queryset `delete()` still fires signals, so it stays audited.
  - Audit events are in the same transaction as the change: if the change rolls back, so does its record. `@require_perm` returns its 403 rather than raising, so a denial record survives `ATOMIC_REQUESTS`.
  - Audited now: College, CollegeFeature, User and RoleAssignment.
- **Alternatives:**
  - django-auditlog and django-simple-history are mature, but they don't know our college boundary, and simple-history adds a history table per model.
  - django-pghistory uses database triggers, which catch even raw SQL, but brings more moving parts and is harder to read for newcomers.
- **Consequences:** Raw SQL and `User` bulk updates are not audited, and reviewers must flag them. Append-only is enforced in the application, not the database. A database role without UPDATE or DELETE on `audit_auditevent`, or a trigger, can be added at deployment. The table will grow without limit, and partitioning or archiving gets its own decision once volumes are known.

## D9. A semester is a term of an academic year

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** In Tamil Nadu colleges the calendar runs in two terms each year. In the odd term students study semesters 1, 3, 5 and 7, and in the even term 2, 4, 6 and 8.
- **Decision:** `Semester` is a term (odd or even) of an `AcademicYear`, with its own dates. A programme's semester number (1 to 8) is a separate idea, held on `Course.semester_number`. `Semester.semester_numbers(n)` maps a term to the semester numbers it runs. Each college has at most one current academic year and one current term, which database constraints enforce.
- **Alternatives:** One `Semester` row per programme semester per year. That model is closer to a timetable, but duplicates the calendar for every programme.
- **Consequences:** Colleges on trimesters or annual patterns would need a new term type. That is configuration under D1, added when a college needs it.

## D14. HOD scope is their own department

- **Date:** 2026-11-22
- **Status:** Accepted
- **Decision:**
  - A HOD `RoleAssignment` must name a department, which a database constraint enforces, and one person may head several departments.
  - A permission registered with `department_scoped=True` lets a user whose only granting role is HOD act only on objects whose `scope_department_id` is one of their departments. Any other granting role, such as principal, is college-wide.
  - Checks without an object, such as list pages, are allowed. In admin, HOD course forms offer only their own programmes, and saves are re-checked against the object.
- **Alternatives:** Admin querysets filtered by department for HODs. That is stricter for reading, but HODs and faculty routinely need to see other departments' courses.
- **Consequences:** Every new department-level model exposes `scope_department_id`. Reading stays college-wide unless a module decides otherwise.

## D15. Minimal academic core

- **Date:** 2026-11-22
- **Status:** Accepted (defaults for plan questions 5 and 6)
- **Decision:**
  - Department, Programme, Course, AcademicYear and Semester are tenant models, audited, with codes unique per college.
  - "Course" means a subject or paper, such as CS3401, taught in one semester of one programme. "Programme" is the degree, such as B.E. CSE.
  - Regulation, such as R2021, is a text field on Programme for now.
  - Viewing is open to principal, HOD, faculty, office and exam cell. Structure (years, terms, departments, programmes) is changed by the principal. Courses are changed by the principal or the department's HOD.
- **Alternatives:** A full curriculum model now, with shared and elective courses across programmes and regulation versions. It was deferred until the staff interviews describe real practice.
- **Consequences:** A course shared by two programmes is two rows until the curriculum module adds a mapping. Students, enrolment, marks, attendance and fees build on these models later.

## D16. Students and Admissions is the first domain module

- **Date:** 2026-11-22
- **Status:** Accepted (Gowtham chose to start now, and approved the module plan with its defaults)
- **Context:** The foundation is merged. The staff survey at PIE Tech and PCAS is still running, but attendance, exams and fees all need students first, and the basics of a Tamil Nadu student record are standard.
- **Decision:**
  - Build Students and Admissions now, in two apps: `students` (batch, section, student, guardian, consent, semester enrolment) and `admissions` (intake, application). Admissions depends on students, never the reverse, so a college can import students without using admissions.
  - Office staff use Django admin plus three custom admin pages: enrol an applicant, promote a batch, and import from Excel. A proper staff interface gets its own plan after the survey.
  - Not in this module: fees, attendance, marks, certificates, a public online application form, document uploads and parent logins.
  - Survey answers are expected to change configuration and details, not the structure.
- **Alternatives:** Wait for the survey and build what staff rank highest. That avoids rework, but leaves every later module without students.
- **Consequences:** CLAUDE.md and the README now say the first domain module is in progress. Other domain modules still need an approved plan.

## D17. Batches, sections and per-term placement

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Tamil Nadu colleges group students by the year they joined a programme ("2026 batch"), split them into sections, and sometimes reshuffle sections, for example after first year. Lateral entry students join the second year of an existing batch.
- **Decision:**
  - `Batch` is one programme's intake in one academic year, unique per programme and year. Its label (2026-2030) is filled in from the programme's duration, and its regulation is copied from the programme but can be changed, because regulations change by batch.
  - `Section` belongs to a batch (A, B, C), with an optional capacity.
  - Which section a student is in, and in which semester, will be recorded per term in `StudentSemester` (PR 3), not on the student, so reshuffles and promotions keep their history.
  - Lateral entry students join an existing batch at semester 3.
  - Batches and sections are department-level objects (D14): the principal, the HOD of the programme's department and office staff can add and change them. Only the principal can delete, and protected foreign keys stop a batch or section with students from being deleted.
- **Alternatives:** Sections fixed on the student record, which is simpler but loses history when sections change; one row per programme semester per term, which duplicates the calendar (rejected in D9 for the same reason).
- **Consequences:** Class lists for a term are read from `StudentSemester`. A batch that changes regulation mid-course is one edit, recorded in the audit log.

## D18. Field-level encryption for sensitive personal data

- **Date:** 2026-11-22
- **Status:** Accepted (plan question 2: store Aadhaar encrypted, show the last 4 digits, principal and office may reveal)
- **Context:** Scholarship and government portals ask for a student's Aadhaar number, community certificate number and family income. Under the DPDP Act these need strong protection, and the Aadhaar rules expect the number to be stored encrypted and shown masked.
- **Decision:**
  - Aadhaar, the community certificate number and a guardian's annual income are stored only as Fernet ciphertext (`cryptography`'s MultiFernet) in `<name>_ciphertext` columns. There is no plain attribute: code writes with `set_secret(name, value)` and reads with `reveal(name, user)`.
  - Aadhaar also keeps `aadhaar_last4` for display (`XXXX XXXX 1234`) and `aadhaar_hash`, an HMAC-SHA256 keyed by `FIELD_HASH_KEY`, so a partial unique constraint stops the same person being admitted twice in a college without decrypting anything.
  - Aadhaar numbers are checked for form and for their Verhoeff check digit before they are stored, which catches most typing mistakes.
  - Keys come from `FIELD_ENCRYPTION_KEYS` (comma-separated; the first encrypts, all decrypt, so keys rotate without downtime) and `FIELD_HASH_KEY`. Production settings refuse to start without them. Test settings use fixed fake keys, and development settings fall back to dev-only keys.
  - `students.view_sensitive` (principal and office) is needed to see community, caste, the category fields, guardians, consent and income in admin, and to reveal encrypted values. Faculty, HODs, exam cell and accounts see the academic record only.
  - Encrypted columns are masked in the audit log, which records only that they changed.
- **Alternatives:** A third-party encrypted field package such as django-cryptography, which hides the ciphertext behind a normal attribute, so any template or serializer could leak a value without a permission check; PostgreSQL pgcrypto, which needs the key inside SQL statements and so in database logs; storing only the last 4 digits, which is safest but fails the scholarship use case.
- **Consequences:** Encrypted fields cannot be searched or sorted, except Aadhaar by exact match through the hash. Losing the keys loses the data, so key backup is part of deployment. Changing `FIELD_HASH_KEY` needs a re-hash of every row.

## D19. Revealing an encrypted field is audited

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** D8 records changes, logins and denials, not reads. For Aadhaar and income, who looked matters as much as who changed it.
- **Decision:** `reveal()` checks the permission first, then writes a `view_sensitive` audit event naming the field (never the value), in the same transaction, before returning the value. The admin shows only the masked value and a "Reveal (audited)" link to a page that calls `reveal()`.
- **Alternatives:** Auditing every view of a student page, which would bury the important events in noise.
- **Consequences:** Every future screen, export or API that shows a sensitive value must go through `reveal()`. Reviewers treat direct use of `crypto.decrypt` outside the students app as a review flag.

## D20. Per-college student settings with Tamil Nadu defaults

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Reservation categories, quotas, required admission documents and roll number formats differ between colleges and states. D1 and D13 say such differences are data.
- **Decision:**
  - `College.config["students"]` holds `communities`, `quotas`, `required_documents` (each a list of `[code, label]`), `roll_number_pattern` and `consent_notice_version`. `apps/students/config.py` documents each key and holds the default.
  - Defaults are Tamil Nadu's: communities OC, BC, BC(M), MBC and DNC, SC, SC(A) and ST; quotas government (counselling) and management; and the usual transfer certificate, mark sheets and community certificate.
  - Community and quota are plain text columns checked against the college's list on every save, not database choices, so changing a list needs no migration. Admin forms offer the college's own list.
  - Lateral entry is an admission type, not a quota.
  - The 7.5% preferential reservation for government school students is a yes/no field on the student, because it also decides some state scholarships.
- **Alternatives:** Database choices on the model (a migration for every list change, and the same list for every college); a table per list (more admin screens for values that rarely change).
- **Consequences:** Removing a code from a college's list makes existing students with that code fail validation on their next save, so a code should be renamed with a data fix, not just removed.

## D21. Admission status flow and one-step enrolment

- **Date:** 2026-11-22
- **Status:** Accepted (plan questions 3, 4 and 7: staff enter applications, documents are a checklist, no parent logins yet)
- **Context:** An admission passes through the same steps at every college: the application is entered, a seat is offered in a quota, the fee and documents are checked, and the student is enrolled. A half-finished enrolment, such as a student without a login or a login without a section, is hard to clean up.
- **Decision:**
  - `Intake` holds sanctioned seats per programme, year and quota. Filled seats are counted from applications that hold a seat (offered, confirmed, enrolled), not stored.
  - `Application` shares `PersonDetails` with `Student`, plus father, mother, guardian mobile, encrypted income, fee paid (a checkbox until the fees module exists), a document checklist from the college's `required_documents`, and a merit score.
  - The statuses are draft, submitted, offered, confirmed, enrolled, rejected and withdrawn. `admissions.services.move()` is the only way to change status. It allows only listed moves, refuses an offer when the quota's seats are full, and refuses confirmation until the fee is ticked and every required document is received. Every change is audited, so there is no separate history table.
  - `services.enrol()` runs in one transaction. It takes the next roll and admission numbers from the college's patterns, copies the personal fields (and the ciphertext as it is, never decrypting), creates a student login with no usable password, creates the guardians and a consent record under the current notice version, and places the student in the chosen section for the current term (semester 3 for lateral entry).
  - Numbers come from `NumberCounter` rows locked with SELECT FOR UPDATE, so two clerks never get the same number. Numbers already taken, for example by imported students, are skipped.
  - One open application per Aadhaar per year, and no enrolment of an Aadhaar that already belongs to a student.
  - Rank lists order by merit score, then qualifying marks, then date of birth (older first), filtered by community if needed, and download as Excel (openpyxl). The community column appears only for users with `students.view_sensitive`.
  - Applications are never deleted. Rejected, withdrawn and enrolled applications are read-only in admin.
- **Alternatives:** A workflow library such as django-fsm (another dependency for seven states); creating the student at confirmation (it would leave students for applicants who never join).
- **Consequences:** The fees module will replace the fee checkbox with a payment check inside `move()`. A public online application form will create applications in draft through the same model. New students need a password set by staff before they can log in.

## D22. Excel import of existing students

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Both colleges hold their current students in spreadsheets or in another ERP (PIE Tech uses Laudea). Office staff need to load hundreds of rows, and a partly loaded file is worse than none.
- **Decision:**
  - One fixed set of columns, described in a downloadable template whose second sheet lists the college's allowed values (communities, quotas, programme codes).
  - Every row is checked first: required values, numbers already used in the college or repeated in the file, community and quota codes, gender, Aadhaar form and duplicates, mobile and PIN code formats, dates, the batch (programme code plus batch year), the section, and a semester number that runs in the current term. Errors are listed by row and column.
  - If any row fails, nothing is saved. Otherwise all rows are saved in one transaction, one at a time, so the audit log records each student, guardian, login and placement.
  - Imported students get a student login with no usable password and are placed in the current term. Father and mother become guardians.
  - No consent record is created on import, because the import cannot prove that consent was given. Consent is recorded afterwards through the student record.
  - An `ImportMapping` (for example "Laudea export") maps another system's headers to KalviOne fields. Its default is create-only, and an update mode can follow.
  - The uploaded file is read in memory and never stored. An `ImportRun` keeps only the file name, counts and errors. Files are limited to 5 MB and 5,000 rows.
  - `manage.py import_students FILE --college SLUG --as USER [--commit]` does the same on a server, for a first data load.
  - Only the principal and office can import (`students.import_students`).
- **Alternatives:** Importing the good rows and reporting the bad ones (leaves half-loaded classes to clean up); django-import-export (generic, and harder to make college-aware and to keep sensitive values out of its previews and logs).
- **Consequences:** Real files are loaded only in deployed environments (D10). Error messages quote cell values, so `ImportRun.errors` can hold a mistyped name or roll number but never an Aadhaar number. Updating existing students from a file needs its own change.

## D23. College login page and the pause after wrong passwords

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Until now the only way in was the Django admin login, which students cannot use and which never slows down password guessing. Staff and students need their own sign-in page on their college's address.
- **Decision:**
  - `/login/`, `/logout/` (POST only) and `/password/change/` are served on every college host and use `CollegeBackend` (D6), so an account works only on its own college's address. The page shows the college's name. Staff sign in with their email and students with their roll number. `/` is a simple home page that later modules add their links to; staff with `is_staff` also see a link to the admin.
  - `LOGIN_URL` is now this page, so `@require_perm` sends signed-out visitors here instead of to the admin login.
  - After `LOGIN_FAILURE_LIMIT` (default 5) wrong passwords for one username from one IP address within `LOGIN_LOCKOUT_MINUTES` (default 15) on one college host, with no successful login in between, further attempts are refused without checking the password. Each refusal is audited as a failed login with reason `too_many_attempts`. Refusals do not extend the pause. The Django admin login form has the same check.
  - The failure count is read from the audit log's failed-login events (D8), so there is no cache or extra table, and every web process sees the same count.
  - A third view mark, `@require_login`, is for pages about the signed-in user themselves (their home page, their own password). It checks login but no permission code. The default-deny test (D7) accepts it alongside `@require_perm` and `@public`.
- **Alternatives:**
  - django-axes, which is mature but keeps its own tables and is not college-aware.
  - A cache-based counter, which would need a shared cache such as Redis in production.
  - Locking a username for everyone, which lets anyone lock a principal out by guessing on purpose. Counting per IP address avoids that, at the cost of letting a guesser who uses many addresses go slower but not stop.
- **Consequences:** Behind a proxy, `REMOTE_ADDR` must be the visitor's real address, or every visitor shares one count; this is set up at deployment. The check reads the audit table on each login attempt, which the existing indexes cover at current volumes.

## D24. Forgot password and emailed set-password links

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Imported and enrolled students, and new staff, get accounts with no usable password (D21, D22). People also forget passwords. The office should not have to type passwords for hundreds of people.
- **Decision:**
  - `/password/forgot/` asks for an email or roll number. It finds an active account in the current college by username, or by email when exactly one account has it. If the account has an email address, it gets a link to `/password/reset/<id>/<token>/` on the same college address. The page always gives the same reply, so it cannot be used to find out who has an account.
  - The token is Django's reset token with its own salt, also tied to the user's college. It stops working once the password is set, after the person signs in, when their email changes, and after `PASSWORD_RESET_TIMEOUT` (default 1 hour). Django's view moves the token from the address bar into the session before showing the form. The link page looks the user up only in the current college.
  - The link also works for accounts with no usable password, so it is how imported students set their first password.
  - At most `PASSWORD_RESET_EMAILS_PER_HOUR` (default 3) reset emails go to one account per hour, counted from the audit log.
  - The audit log records each request (`reset_requested`, with whether an email was sent and why not) and each password set from a link (`password_set`), next to the usual masked User update. Requests for unknown accounts record the text typed, as failed logins already do.
  - Email goes through Django's mail API, configured by `EMAIL_URL` (django-environ). The default prints emails to the console. A real provider (for example Zoho Mail SMTP or Amazon SES) is set at deployment.
  - Excel import now copies the student's email and mobile number to their login, as enrolment already did.
- **Alternatives:** One-time codes by SMS (costs money per message, and needs a provider and DLT registration in India; it can be added later for students without email); django-allauth (much more than we need, and not college-aware).
- **Consequences:** People with no email on file must ask the office to add one. Sending happens inside the request, so a slow mail server slows the page; a background queue can come later.

## D25. Invite emails for a first password

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Staff, imported students and enrolled students get accounts with no usable password (D21, D22). The college needs to tell them their account exists and let each one choose a password, without the office handling passwords.
- **Decision:**
  - An invite is an email with the username and a link to `/welcome/<id>/<token>/` on the college's address, where the person chooses their first password. It reuses the D24 link page, with its own token salt, so an invite link is never a reset link and the other way round. It lasts `INVITE_LINK_TIMEOUT` (default 7 days) and stops working once a password is set.
  - Only active accounts with an email address and no usable password can be invited. Anyone who already has a password uses "Forgot password?" instead.
  - The principal and office (`accounts.invite_user`) send invites from the admin user list ("Send invite email"), or for a whole college with `manage.py send_invites --college SLUG --as USER [--only staff|students|parents] [--send]`. Without `--send` the command only counts.
  - Each invite is audited as `invite_sent`, with the sender as actor.
  - Emails sent outside a request build the link from `COLLEGE_URL_TEMPLATE` (for example `https://{slug}.kalvione.in`), so they always point at the college's own address.
- **Alternatives:** Sending invites automatically on enrolment or import (easy to add later, but colleges may want to check the data first); temporary passwords printed on a slip (they get shared and never changed).
- **Consequences:** `COLLEGE_URL_TEMPLATE` must be set correctly in each deployment. A large college sends hundreds of emails in one run, so the mail provider's sending limits apply; a background queue can come later.

## D26. Fees is the second domain module, with a daily Tally file first

- **Date:** 2026-11-22
- **Status:** Accepted (Gowtham approved the module plan with its defaults; changes may follow from the accountants and colleges)
- **Context:** Fees is the module colleges ask about first after students, and most Tamil Nadu colleges keep their accounts in Tally (Prime, or the older ERP 9). Accountants should not have to type each fee receipt into Tally a second time.
- **Decision:**
  - Build Fees now as one app, `fees`, in six small pull requests: fee heads, payment accounts and structures; concessions, scholarships and student dues; receipts on a phone-first screen, printing and cancelling; dues reports and the admissions fee check; the daily Tally file; and AI help (dues-risk flags, plain-word questions and reminder drafts).
  - Tally integration starts as a daily XML file of that day's receipts as Receipt vouchers, which the accountant imports into Tally. A receipt goes into a downloaded file only once. Live sync through Tally's own XML port is a later phase.
  - The accounts role takes payments and downloads the Tally file. Only the principal approves concessions and cancels receipts. Office staff and HODs can see fee set-up and dues.
  - Most college fees are exempt from GST, so every fee head is exempt unless it is given a rate.
  - One Tally ledger per fee head, not per student.
  - Not in this module yet: online payment links or a gateway, live Tally sync, late fines and refunds.
  - AI features never send student names, numbers, amounts or sensitive fields to an AI service. Dues-risk flags are worked out on our own server.
- **Alternatives:** Live Tally sync first (needs Tally running and reachable from our server at every college, which is rare on day one); a CSV for the accountant to key in (still double entry).
- **Consequences:** Every fee head and payment account needs its Tally ledger name spelt as it is in Tally. A ledger list file will let the accountant create missing ledgers in one import.

## D27. Fee heads, payment accounts and fee structures

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Colleges charge the same kinds of fee (tuition, development, exam, hostel, bus) but in different amounts per batch, year, quota and hostel or day scholar, usually in two or more instalments.
- **Decision:**
  - `FeeHead` is one kind of fee with a code, the name printed on receipts, its Tally ledger name, a GST rate (0 to 40, default 0) and, for taxable heads, an HSN or SAC code.
  - `PaymentAccount` is where money is received: a cash counter or a bank account, each with its Tally ledger name. A college can have several bank accounts.
  - `FeeStructure` is what one batch pays in one academic year. It can be limited to one quota and to hostel or day scholars; blank means all. When several structures fit a student, the most specific one applies (quota and residence each count once). The year of study is worked out from the batch's admission year and must fall inside the programme's duration.
  - A structure has `Instalment`s (number, label, due date) and `FeeStructureLine`s (instalment number, fee head, amount). The admin edits both on one page and refuses an amount for an instalment that is not set up.
  - `College.config["fees"]` holds the Tally company name, the GST output ledgers, the receipt number pattern and the month the financial year starts, documented in `apps/fees/config.py`.
  - The principal and accounts set up fees; office staff and HODs can only see them. Fee heads in use cannot be deleted.
- **Alternatives:** One amount per head per year with no instalments (does not match how colleges collect); a structure per student (too much data entry); fee heads as a config list instead of rows (receipts and Tally need a stable row to point at).
- **Consequences:** Next year's fees are a new structure, so old receipts always point at the amounts that applied then. Copying a structure to a new year can be added when the accountants ask for it.

## D28. Student dues and concessions

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Students owe different amounts once scholarships and concessions are taken off. Tamil Nadu has several government scholarships (Post-Matric for SC, SCA and ST students, first graduate, the 7.5% government school scheme, and BC, MBC and DNC scholarships) that the student does not pay but the college must still collect from the government. Colleges also give their own concessions (merit, staff ward, sports, management).
- **Decision:**
  - `StudentDue` is one row per student, fee head and instalment for an academic year, copied from the student's fee structure with its label and due date. It keeps the amount, `waived` (the college's concession), `govt_share` (expected from a government scholarship) and `paid`. What the student pays is amount minus waived minus the government share, and the database refuses a row where those and `paid` add up to more than the amount.
  - Dues are raised for a whole batch from the fee structure list ("Raise dues"), by the principal or accounts. It picks each studying student's most specific structure (quota first, then residence), skips students no structure fits and lists them, and never changes dues that already exist, so it can be run again for students who join late.
  - `Concession` belongs to a student and an academic year. Its type comes from `College.config["fees"]["concession_types"]` (Tamil Nadu defaults), and each type says whether the government or the college pays. That is copied onto the concession, so a later config change does not rewrite history. A concession is a percentage (of one head or all heads) or a fixed amount for one head, taken from the earliest instalments first.
  - Office and accounts enter concessions; only the principal approves, rejects or withdraws them. Only approved concessions count. Each decision works the shares out again from scratch, and a due is never reduced below what has been paid on it. What no longer fits is shown as a warning, because it needs a refund or an adjustment by hand.
  - Dues cannot be added, changed or deleted by hand in the admin. Concessions are never deleted; they are rejected or withdrawn.
- **Alternatives:** Working dues out on the fly from structures and concessions every time (simple to store, but slow for reports and it would change old dues when a structure is edited); one due row per student per instalment with heads in JSON (harder to post per head to Tally).
- **Consequences:** Changing a structure after dues are raised does not change those dues; that needs a correction tool, to be added when accountants ask. The government share is the basis for a "receivable from government" report in step 4.

## D29. Receipts on a phone-first counter page

- **Date:** 2026-11-22
- **Status:** Accepted
- **Context:** Most accounts staff work from a phone (Gowtham, 2026-11-22). They need to find a student, see what is owed, take cash, UPI, card, bank transfer, cheque or DD, and hand over or share a receipt, all on a small screen. Receipt numbers must never repeat, and the Tally file (step 5) needs fee head amounts and GST per receipt.
- **Decision:**
  - The fee counter has its own pages outside the admin, using the shared base template: `/fees/collect/` (search by roll number or name; one match opens straight away), `/fees/collect/<student>/` (dues per instalment, then the payment form), `/fees/receipts/<id>/` (the printable receipt, which also saves as PDF from the phone's print menu) and `/fees/receipts/<id>/cancel/`. The home page links to the counter for users who may collect.
  - `fees.collect` (principal and accounts) takes payments; `fees.view_receipt` (also office and HODs) opens and prints receipts; `fees.cancel_receipt` is the principal's alone.
  - `receipts.collect()` locks the student's dues, refuses more than is owed (no advance payments yet), and settles the oldest dues first: by due date, then instalment, then the fee head's print order. Each `ReceiptLine` points at the due it paid.
  - Cash goes to a cash account and every other mode to a bank account. Every mode except cash needs a reference number, which the database also checks.
  - Numbers come from `College.config["fees"]["receipt_number_pattern"]` (default `{code}/{fy}/{seq:06}`, for example `PIE/2026-27/000123`), with a separate counter per financial year. The financial year starts in the configured month (April). The students module's locked `NumberCounter` is reused, so two counters never get the same number.
  - The receipt date is always the day it is saved. Backdated receipts are not allowed, so the daily Tally file for a day can only gain receipts on that day.
  - Fee amounts include GST. On a taxable head the line keeps the taxable value, CGST and SGST, rounded to the paisa, and the database checks that they add up to the amount.
  - Receipts are never deleted or edited. Cancelling needs a reason, puts each line's amount back on its due, and keeps the receipt marked as cancelled.
  - Amounts are shown with Indian digit grouping (1,23,456.00), and in words with lakh and crore.
- **Alternatives:** Taking payments inside the Django admin (unusable on a phone); letting the cashier choose which dues to pay (more taps, and more mistakes at a busy counter; can be added later); a separate receipt number table (the existing locked counter already does this).
- **Consequences:** A student who overpays or wants to pay in advance cannot yet; refunds and advances need their own change. Sharing on WhatsApp is done by saving the receipt as a PDF from the phone for now.

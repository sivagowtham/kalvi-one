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
| D10 | Only fake data in the repo, seeds and CI | Accepted |
| D11 | Tooling: uv, ruff, pytest-django, factory_boy, GitHub Actions | Accepted |
| D12 | Current college resolved from the host and held in a context variable; tenant queries fail closed | Accepted |
| D13 | Per-college configuration in a JSON field, rare needs as per-college feature flags | Accepted |

D8 (audit log) and D9 (semester as term) will be recorded in the pull requests that implement them.

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
- **Consequences:** Real college data is loaded only into deployed environments, through an import process to be designed later.

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

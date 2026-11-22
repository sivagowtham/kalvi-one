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
| D10 | Only fake data in the repo, seeds and CI | Accepted |
| D11 | Tooling: uv, ruff, pytest-django, factory_boy, GitHub Actions | Accepted |

D6 to D9 (custom user model, roles and permissions, audit log, semester as term) will be recorded in the pull requests that implement them.

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

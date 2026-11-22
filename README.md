# KalviOne

KalviOne is a multi-tenant ERP for colleges. One codebase serves every college. Each college gets its own subdomain, and the differences between colleges are configuration, never forks (see [docs/decisions.md](docs/decisions.md)).

The project is in the foundation phase: scaffold, multi-tenancy, authentication and roles, audit log, and a minimal academic core. Domain modules such as marks, attendance and fees come later.

## Run it locally

You need Docker, and [uv](https://docs.astral.sh/uv/) if you want to run tests on your machine.

```sh
cp .env.example .env
make up                 # Django on http://localhost:8000 and PostgreSQL on localhost:5432
make migrate            # in a second terminal
make seed               # fake demo colleges with one user per role
docker compose run --rm web python manage.py createsuperuser   # platform admin at http://localhost:8000/admin/
```

Check it is running at http://localhost:8000/health/.

`make seed` creates two fake colleges, "Demo College of Engineering" at http://demo.localhost:8000/admin/ and "Sample College of Arts and Science" at http://sample.localhost:8000/admin/. Each gets departments, programmes, courses and the 2026-27 academic year, plus one user for every role: `principal@demo.example`, `hod@demo.example`, `faculty@demo.example`, `office@demo.example`, `accounts@demo.example`, `examcell@demo.example`, student `26DCE001` and `parent@demo.example`. The password for all of them is `kalvione-demo-123`. The command is safe to run twice, and it refuses to run in production settings.

Each college is served on its own subdomain. With a college whose slug is `demo`, open http://demo.localhost:8000/. Browsers send `*.localhost` to your own machine, so no DNS setup is needed.

## Tests and lint

The tests need PostgreSQL. Start just the database with `docker compose up db`, then:

```sh
uv sync
make lint
make test
make check              # everything CI runs
```

## Layout

| Path | What it holds |
| --- | --- |
| `config/` | Settings for dev, test and prod, plus URLs, WSGI and ASGI |
| `apps/` | Django apps: `core`, `tenancy` (College, TenantModel, middleware), `accounts` (users, roles, permissions), `audit` (append-only audit log), `academics` (departments, programmes, courses, years, terms) |
| `tests/testapp/` | Models used only by tests to exercise TenantModel |
| `tests/` | Project-wide tests |
| `docs/decisions.md` | Every architecture decision and its reasons |

# KalviOne

KalviOne is a multi-tenant ERP for colleges. One codebase serves every college. Each college gets its own subdomain, and the differences between colleges are configuration, never forks (see [docs/decisions.md](docs/decisions.md)).

The project is in the foundation phase: scaffold, multi-tenancy, authentication and roles, audit log, and a minimal academic core. Domain modules such as marks, attendance and fees come later.

## Run it locally

You need Docker, and [uv](https://docs.astral.sh/uv/) if you want to run tests on your machine.

```sh
cp .env.example .env
make up                 # Django on http://localhost:8000 and PostgreSQL on localhost:5432
make migrate            # in a second terminal
```

Check it is running at http://localhost:8000/health/.

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
| `apps/` | Django apps (`core` for now; tenancy, accounts, audit and academics follow) |
| `tests/` | Project-wide tests |
| `docs/decisions.md` | Every architecture decision and its reasons |

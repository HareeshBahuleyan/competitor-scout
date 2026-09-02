# Competitor Scout

B2B competitive intelligence powered by bounded main-agent and child-agent Scout Runs
running on [Otari](https://otari.ai). Users sign in with Google, track competitors, and
receive synthesized findings and briefs.

Every model request — planning, child research tasks, and synthesis — goes through the
Otari gateway, under the per-run token, concurrency, deadline, and cost ceilings
configured in `.env`.

The backend (FastAPI API + Scout worker + PostgreSQL) runs in Docker. The frontend
(Next.js) runs on the host and proxies to the containerized API.

## Prerequisites

| Tool                             | Version | Needed for                                     |
| -------------------------------- | ------- | ---------------------------------------------- |
| Docker + Compose                 | current | PostgreSQL, API, worker                        |
| Node.js                          | 22      | frontend dev server                            |
| pnpm                             | 10.11.1 | frontend dependencies (`corepack enable pnpm`) |
| Python                           | 3.12    | host-side backend commands                     |
| [uv](https://docs.astral.sh/uv/) | current | backend tests, lint, migrations                |

Python and `uv` are only required to run backend tests, linting, or migrations on the
host — the containers install their own dependencies.

## 1. Configure the environment

```bash
cp .env.example .env
```

Fill these in `.env` before starting anything; the API refuses to boot without them:

- `SESSION_SECRET` and `CSRF_SECRET` — at least 32 characters each
  (`openssl rand -hex 32`)
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` — from a Google OAuth 2.0 client with
  the authorized redirect URI `http://localhost:3000/auth/google/callback`
- `OTARI_AI_TOKEN` — any non-empty dummy value is fine for offline development,
  because the test suites inject fake Otari clients. Replace it only for an explicitly
  approved hosted smoke test.

`.env` is gitignored. Leave `DATABASE_URL` pointing at `localhost:5432` — that value is
used by host commands such as `alembic`; Compose overrides it to the `postgres` service
hostname inside the container network.

## 2. Start the backend in Docker

```bash
docker compose up --build
```

This starts four services:

| Service        | Role                                                          |
| -------------- | ------------------------------------------------------------- |
| `postgres`     | PostgreSQL 16, exposed on `localhost:5432`                    |
| `prestart`     | one-shot `alembic upgrade head`; must exit successfully first |
| `backend-api`  | Uvicorn API on `http://localhost:8000`                        |
| `scout-worker` | background Scout Run executor                                 |

`backend-api` and `scout-worker` wait for `prestart` to complete, so a failed migration
stops the stack rather than starting a half-configured API. Check readiness with
`curl http://localhost:8000/health/ready`.

Useful variants:

```bash
docker compose up --build -d          # detached
docker compose logs -f backend-api    # follow API logs
docker compose down                   # stop (keeps the database volume)
docker compose down -v                # stop and delete the database volume
```

## 3. Start the frontend on the host

In a second terminal:

```bash
cd apps/web
pnpm install
pnpm dev
```

Open `http://localhost:3000`. Next.js rewrites `/api/*`, `/auth/*`, and `/health/*` to
`WEB_INTERNAL_API_URL` (default `http://localhost:8000`), so use port 3000 for
everything — including sign-in, which depends on the OAuth redirect URI above.

## Verification

```bash
cd apps/backend
uv run pytest
uv run ruff check src tests scripts
uv run alembic check          # needs the postgres service running

cd ../web
pnpm test
pnpm lint
pnpm build

# Optional browser smoke suite
pnpm exec playwright install chromium
pnpm test:e2e
```

All normal verification is offline and must not make paid Otari calls. The live
evaluation script additionally requires both `ALLOW_PAID_OTARI_EVALS=true` and
`--confirm-paid-run`.

## Pre-commit checks

Install [pre-commit](https://pre-commit.com/) and enable the repository hooks:

```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks reject common file errors, private keys, and leaked secrets; they also
apply Ruff and Prettier linting and formatting. The Gitleaks hook requires Go.
GitHub Actions repeats these checks and runs the backend, frontend, migration,
build, and dependency-review suites for every pull request. The Playwright browser
smoke suite remains available as an on-demand local or pre-release check.

See the [Railway deployment guide](docs/railway-deployment.md) for production topology, configuration, and smoke checks.

## Project guidance

- [Agent instructions](AGENTS.md)
- [Architecture overview](docs/architecture/overview.md)
- [Backend architecture](docs/architecture/backend.md)
- [Scout agent runtime](docs/architecture/agent-runtime.md)
- [Frontend design system](docs/frontend/design-system.md)

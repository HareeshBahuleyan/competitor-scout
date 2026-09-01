# Competitor Scout

Private-alpha B2B SaaS competitive intelligence powered by bounded main-agent and child-agent Scout Runs. Google sign-in admits up to the configured active-user capacity.

## Local prerequisites

- Python 3.12
- Node.js 22
- Docker

## Start local services

Create the root `.env` first, then start PostgreSQL, run migrations, and launch the
API and worker:

```bash
docker compose up --build
```

The `backend-api` service is available at `http://localhost:8000`. The one-shot
`prestart` service must complete successfully before `backend-api` and
`scout-worker` start.

## Frontend

Run the frontend on the host in a separate terminal:

```bash
cd apps/web
pnpm install
pnpm dev
```

Open `http://localhost:3000`. Next.js proxies API and authentication requests to
the containerized API at `http://localhost:8000`.

Copy `.env.example` to the ignored root `.env`. A dummy `OTARI_AI_TOKEN` is safe
for offline development because the normal suites inject fake Otari clients; replace
it only when an explicitly approved hosted smoke test is being performed.

## Verification

```bash
cd apps/backend
uv run pytest
uv run ruff check src tests scripts
uv run alembic check

cd ../web
pnpm test
pnpm lint
pnpm build
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
build, dependency-review, and browser test suites for every pull request.

See the [Railway deployment guide](docs/railway-deployment.md) for production topology, configuration, and smoke checks.

## Project guidance

- [Agent instructions](AGENTS.md)
- [Architecture overview](docs/architecture/overview.md)
- [Backend architecture](docs/architecture/backend.md)
- [Scout agent runtime](docs/architecture/agent-runtime.md)
- [Frontend design system](docs/frontend/design-system.md)

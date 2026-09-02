# Railway deployment

Competitor Scout deploys as exactly four Railway services in one project: `web`,
`api`, `worker`, and `postgres`. The browser reaches only `web`; Railway private
networking connects `web` to `api`, and both Python services connect to `postgres`.

## Service topology

| Service    | Railway root directory      | Config                | Exposure             |
| ---------- | --------------------------- | --------------------- | -------------------- |
| `web`      | `/apps/web`                 | `railway.toml`        | Public custom domain |
| `api`      | `/apps/backend`             | `railway.api.toml`    | Private network only |
| `worker`   | `/apps/backend`             | `railway.worker.toml` | Private network only |
| `postgres` | Railway PostgreSQL template | Managed by Railway    | Private network only |

Set `WEB_INTERNAL_API_URL` on `web` to the API's Railway private URL, including
the `http://` scheme and port. Make the variable available during the web image
build because Next.js materializes rewrite configuration during the production build.

## Required variables

Set these on both `api` and `worker` unless noted otherwise:

- `ENVIRONMENT=production`
- `DATABASE_URL` from the `postgres` service, using the `postgresql+asyncpg://` scheme
- `PUBLIC_BASE_URL=https://<web-domain>`
- `SESSION_COOKIE_NAME=competitor_scout_session`
- `SESSION_SECRET` and `CSRF_SECRET`, each generated independently with at least 32 random bytes
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
- `OTARI_BASE_URL=https://api.otari.ai`
- `OTARI_AI_TOKEN` (the only supported Otari credential)
- `OTARI_MAIN_MODEL=general-mzai-then-openai-models`
- `OTARI_CHILD_MODEL=general-mzai-then-openai-models`
- optional `OTARI_COST_LOOKUP_ATTEMPTS` and `OTARI_COST_LOOKUP_DELAY_SECONDS`, which bound
  the settled-cost lookup described in `docs/architecture/agent-runtime.md`
- all documented task, deadline, concurrency, confidence, and cost-ceiling variables from `.env.example`

The Otari workspace budget is configured in Otari rather than duplicated as a Railway variable. Otari enforces it for `OTARI_AI_TOKEN`; keep the application-level `MAX_RUN_COST_USD` and `MAX_USER_DAILY_COST_USD` ceilings configured as an additional guard.

Named-policy rollout is gated on the hosted Otari cutover. The legacy hosted model catalog lists concrete models only and still resolves the workspace default regardless of the requested policy name. Before deploying this configuration, confirm that `general-mzai-then-openai-models` is selectable on the target Otari deployment; until then, it is effective only when the same policy is the legacy workspace default.

Do not configure `E2E_AUTH_SECRET` in production.

Set this on `web`:

- `WEB_INTERNAL_API_URL=http://<api-private-host>:<port>`

## Provisioning order

1. Create `postgres`, then attach its connection variable to `api` and `worker`.
2. Deploy `api`. Its pre-deploy command runs `alembic upgrade head`.
3. Confirm `GET /health/live` and `GET /health/ready` return `200` inside the project.
4. Deploy `worker`, then verify scheduler and executor startup logs.
5. Deploy `web`, attach the public domain, and set `PUBLIC_BASE_URL` to that exact origin.

Keep the `worker` service at exactly one replica in the MVP. Its Otari semaphore is
shared process-wide; horizontal worker scaling requires a PostgreSQL-backed global
request permit before additional replicas are safe.

In Google Cloud, register this exact redirect URI:

```text
https://<web-domain>/auth/google/callback
```

## Account capacity

Set `MAX_ACTIVE_USERS=10` on `api` and `worker`. Google OAuth creates accounts
without an invite allowlist until that active-user capacity is reached. Existing
users can continue to log in after registration closes, and disabled users do not
consume an active slot.

## Otari deployment gate

Hosted Otari structured output, configured models, Tavily-backed web-search entitlement,
request IDs, pricing metadata, and the configured ceilings must be verified in a
staging Railway project before production monitoring is enabled. This is a paid
external test and requires explicit approval. Never use the dummy local token for it.
The smoke test must also confirm that activity records name
`general-mzai-then-openai-models` as the applied policy rather than silently using a
legacy workspace default.

## Rollback and restore

Application rollback is an image redeploy, not a destructive database downgrade:

1. Stop the worker so it claims no new jobs.
2. Roll `api` and `web` back to the last known-good Railway deployment.
3. Consult the migration's downgrade notes before changing the database schema.
4. Prefer a forward-fix; restore a Railway backup only after preserving the failed database.
5. Verify a restore in a separate database by running `alembic current`, read-only row counts,
   and representative user-scoped API queries before redirecting services.

## Smoke-test checklist

- API liveness and database readiness return `200`.
- Google OAuth creates users up to the configured capacity, rejects the next new account, and permits existing-user login.
- Source discovery creates safe, in-domain suggestions without changing prior approvals.
- Approving a source permits activation and a manual run.
- A completed or valid partial run exposes bounded tasks and settled usage.
- Every published finding links to direct quoted evidence over public HTTPS.
- A weekly fixture job produces a grounded brief.
- Logs correlate request, run, task, and provider request IDs without cookies, tokens,
  raw prompts, or full model responses.

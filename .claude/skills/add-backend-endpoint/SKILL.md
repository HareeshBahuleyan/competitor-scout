---
name: add-backend-endpoint
description: Use when adding or changing a FastAPI route, request or response schema, API-backed service operation, or frontend-consumed API contract in Competitor Scout.
---

# Add Backend Endpoint

Add endpoints through the repository's existing transport, service, persistence, and contract boundaries. Preserve user isolation and security behavior before optimizing for convenience.

## Workflow

1. Read the root and backend `AGENTS.md` files plus `docs/architecture/backend.md`.
2. Find the closest existing route and test with `rg`; follow its dependency, error, pagination, and response conventions.
3. Define Pydantic request and response types in `apps/backend/src/competitor_scout/schemas/`. Do not return ORM objects accidentally.
4. Keep the function in `api/` limited to HTTP concerns. Put queries and domain behavior in `services/` unless the operation is truly transport-only.
5. Require `CurrentUser` for user-owned resources and include `user.id` in every ownership query. Return the repository's problem-details errors without exposing whether another user's record exists.
6. Use `DbSession`; let `session_dependency` own request commit or rollback. Add explicit transactions only for background work or a demonstrated multi-session requirement.
7. If persistence changes, update SQLAlchemy models and add an Alembic migration. Never edit an applied migration to represent a new change.
8. If the response is consumed by the web app, update `apps/web/src/lib/schemas.ts` and its schema/API tests in the same change.
9. Add focused unit tests for domain rules and integration tests for routing, validation, authorization, user isolation, and database behavior.
10. Run the smallest applicable verification set, then broaden it when the contract or persistence layer changed.

## Security checks

- Use `CsrfRequired` for mutations.
- Pass submitted source URLs through the existing public-HTTPS/SSRF validation path.
- Keep test authentication gated to the test environment.
- Do not log cookies, tokens, raw prompts, provider responses, or sensitive task output.
- Preserve stable, safe error codes for worker-visible failures.

## Verification

Use the verification matrix in the root `AGENTS.md`, selecting rows by what the change touched:

| Change                     | Matrix rows             |
| -------------------------- | ----------------------- |
| Route, service, or schema  | Backend                 |
| Model or migration         | Backend, then Migration |
| Frontend-consumed contract | Cross-stack contract    |

During iteration, narrow the backend row to the affected tests (`uv run pytest tests/unit tests/integration`) before running the full suite.

Do not run paid Otari evaluations unless the user explicitly approves them.

## Common mistakes

- Querying by record ID without `user_id`.
- Putting reusable business logic directly in a route.
- Changing Pydantic output without updating the corresponding Zod schema.
- Manually committing inside a request-scoped service.
- Adding a mutation without CSRF enforcement.
- Treating generated OpenAPI documentation as sufficient contract verification.

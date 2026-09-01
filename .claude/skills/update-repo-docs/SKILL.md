---
name: update-repo-docs
description: Use when implementing or reviewing Competitor Scout changes that alter setup, commands, API or runtime behavior, architecture, security invariants, jobs, agent execution, deployment, or frontend design conventions.
---

# Update Repository Docs

Document verified current behavior in the smallest authoritative location and repair stale statements elsewhere in the same change.

## Workflow

1. Read the root `AGENTS.md` and the nearest nested agent guide.
2. Inspect the change with `git diff`, `git status`, and targeted `rg` searches, including configuration, migrations, tests, and deployment files.
3. Use the impact map below to select affected documents. Do not edit every document by default.
4. Verify every claim against source, configuration, tests, or command output. Never present a proposal as implemented.
5. Update the authoritative document and link to it from shorter guidance. Avoid duplicated commands and invariants.
6. Replace stale text instead of appending qualifications. Keep paths, service names, variables, diagrams, statuses, and commands exact.
7. Update `README.md` navigation when a durable document is added, moved, or removed.
8. Re-read the changed code and documentation together, then run formatting, link, and diff checks.

## Documentation impact map

| Change                                                               | Update when affected                                      |
| -------------------------------------------------------------------- | --------------------------------------------------------- |
| Local setup, prerequisites, common verification                      | `README.md`, root `AGENTS.md`                             |
| Repository boundaries, safety rules, skills                          | Root `AGENTS.md`                                          |
| API layers, transactions, models, migrations, auth, jobs             | `apps/backend/AGENTS.md`, `docs/architecture/backend.md`  |
| Runtime topology or synchronous/background flows                     | `docs/architecture/overview.md`                           |
| Prompts, contracts, run states, evidence, budgets, provider behavior | `docs/architecture/agent-runtime.md`, backend `AGENTS.md` |
| Tokens, layout, components, interaction, accessibility               | `docs/frontend/design-system.md`, `apps/web/AGENTS.md`    |
| Railway services, variables, rollout, rollback, smoke checks         | `docs/railway-deployment.md`, architecture overview       |
| Migration-specific operating rules                                   | `apps/backend/migrations/README.md`                       |

`AGENTS.md` gives change instructions, `docs/` explains behavior and rationale, and `README.md` is the human quick start.

## Quality rules

- Write in present tense and distinguish current constraints from future work.
- Prefer semantic descriptions plus source paths over brittle line-number references.
- Keep Mermaid diagrams small and ensure every named component exists.
- Include security and operational consequences when a boundary changes.
- Omit unstable internal details that do not help maintainers.
- Preserve the generated Next.js block in `apps/web/AGENTS.md`; add project guidance outside its markers.

## Verification

- Run Prettier on changed Markdown and YAML files.
- Run `git diff --check` and scan new files for unfinished placeholders and trailing whitespace.
- Resolve every changed local Markdown link to an existing file.
- Run `quick_validate.py` for every changed repository skill.
- Run application tests required by the underlying code change; prose-only edits do not require unrelated application suites.

## Common mistakes

- Updating only the README after changing an architectural invariant.
- Describing remembered behavior without checking current source.
- Duplicating the same rule across several documents until they drift.
- Leaving an old diagram or command beside newer contradictory prose.
- Treating passing Markdown formatting as proof that technical claims are correct.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Competitor Scout web guide

These instructions apply under `apps/web` and supplement the root `AGENTS.md`. Keep project-specific guidance outside the generated markers above.

Read `docs/frontend/design-system.md` before adding reusable components, tokens, visual variants, or interaction patterns.

## Framework and boundaries

- This app uses Next.js 16, React 19, Tailwind CSS 4, HeroUI 3, TanStack Query 5, and Zod 3, plus `@vvo/tzdb` for IANA timezone data. Inspect the relevant installed Next.js guide under `node_modules/next/dist/docs/` before changing framework behavior.
- Prefer server components. Add `"use client"` only for state, effects, event handlers, context, or browser-only APIs; keep client boundaries narrow.
- Keep `src/app/` route files focused on metadata, parameters, and view composition.
- Choose the component ownership level from the table in `docs/frontend/design-system.md`.
- Use the `@/` import alias for application modules.

## API and security

- Call same-origin relative paths through `src/lib/api.ts`; do not call the private backend URL from browser code.
- Preserve `credentials: "include"`, redirect-on-401 behavior, CSRF headers on mutations, safe problem-details parsing, and the same-origin path assertion.
- Parse every JSON response with a Zod schema from `src/lib/schemas.ts`; the backend Pydantic model is the contract's source of truth.
- Never expose secrets in `NEXT_PUBLIC_*` variables or render sensitive agent task output that the backend intentionally filters.

## UI rules

`docs/frontend/design-system.md` owns the tokens, status roles, state coverage, and accessibility requirements. The rules that decide whether a change belongs here:

- Reuse semantic variables and established patterns in `src/app/globals.css`; do not add literal product colors when a semantic token fits.
- Use HeroUI when it provides useful accessible behavior and matches an existing project pattern. Use semantic HTML or a small local component for simple markup.
- Restyle HeroUI through the token mapping block in `globals.css`, not with per-component class overrides.
- A native `<select>` cannot style its own dropdown list. Use HeroUI's `Select` with a `ListBox` when the list needs product styling; keep a native `<select>` only where a control must submit inside a plain GET form without JavaScript.
- Keep operator and diagnostic routes such as `/runs` out of `PrimaryNavigation`; link them from the context that motivates opening them.
- Use the interface vocabulary in `docs/frontend/design-system.md` for user-facing copy, and leave routes, API paths, and Zod fields on the backend contract's names.
- Extract a shared component only when it centralizes repeated markup, behavior, tokens, or accessibility requirements.

## Tests and verification

- Use Testing Library and Vitest for user-visible behavior, semantics, forms, and state transitions. Avoid assertions coupled only to Tailwind class strings.
- Drive HeroUI and react-aria overlays with `@testing-library/user-event`; `fireEvent` does not dispatch the pointer sequence that opens a popover.
- Use Playwright for critical authentication and cross-page workflows, not for every component variant.
- Do not update snapshots or loosen assertions merely to make a failure disappear; verify the intended behavior first.

During iteration, run the focused test. Before completion, run the frontend commands from the verification matrix in the root `AGENTS.md`.

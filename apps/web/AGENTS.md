<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Competitor Scout web guide

These instructions apply under `apps/web` and supplement the root `AGENTS.md`. Keep project-specific guidance outside the generated markers above.

Read `docs/frontend/design-system.md` before adding reusable components, tokens, visual variants, or interaction patterns.

## Framework and boundaries

- This app uses Next.js 16, React 19, Tailwind CSS 4, HeroUI 3, TanStack Query 5, and Zod 3. Inspect the relevant installed Next.js guide under `node_modules/next/dist/docs/` before changing framework behavior.
- Prefer server components. Add `"use client"` only for state, effects, event handlers, context, or browser-only APIs; keep client boundaries narrow.
- Keep `src/app/` route files focused on metadata, parameters, and view composition.
- Put page-level data orchestration in `src/components/pages/`, reusable product components in `src/components/`, and generic visual or interaction primitives in `src/components/ui/`.
- Use the `@/` import alias for application modules.

## API and security

- Call same-origin relative paths through `src/lib/api.ts`; do not call the private backend URL from browser code.
- Preserve `credentials: "include"`, redirect-on-401 behavior, CSRF headers on mutations, safe problem-details parsing, and the same-origin path assertion.
- Parse every JSON response with a Zod schema from `src/lib/schemas.ts`. Keep it synchronized with the backend Pydantic response model.
- Never expose secrets in `NEXT_PUBLIC_*` variables or render sensitive agent task output that the backend intentionally filters.

## UI rules

- Reuse semantic variables and established patterns in `src/app/globals.css`; do not add literal product colors when a semantic token fits.
- Use HeroUI when it provides useful accessible behavior and matches an existing project pattern. Use semantic HTML or a small local component for simple markup.
- Cover loading, empty, error, populated, disabled, and submitting states as applicable.
- Pair status colors with text or another non-color signal. Preserve visible focus, keyboard access, form error associations, live-region behavior, responsive layout, and reduced motion.
- Extract a shared component only when it centralizes repeated markup, behavior, tokens, or accessibility requirements.

## Tests and verification

- Use Testing Library and Vitest for user-visible behavior, semantics, forms, and state transitions. Avoid assertions coupled only to Tailwind class strings.
- Use Playwright for critical authentication and cross-page workflows, not for every component variant.
- During iteration, run the focused test. Before completion, run `pnpm format:check`, `pnpm test`, `pnpm lint`, and `pnpm build`; add `pnpm test:e2e` when a critical browser flow changes.
- Do not update snapshots or loosen assertions merely to make a failure disappear; verify the intended behavior first.

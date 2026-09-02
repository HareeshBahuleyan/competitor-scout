---
name: add-ui-pattern
description: Use when adding or changing a reusable React component, visual pattern, form control, status treatment, loading or empty state, or shared interaction in the Competitor Scout web app.
---

# Add UI Pattern

Extend the interface through semantic design tokens, accessible behavior, and the smallest reusable component boundary that removes real duplication.

## Workflow

1. Read the root and web `AGENTS.md` files and `docs/frontend/design-system.md`.
2. Inspect the installed Next.js guide relevant to the change under `apps/web/node_modules/next/dist/docs/`; do not rely on remembered framework behavior.
3. Search `apps/web/src/components`, `globals.css`, and HeroUI usage for an existing pattern before adding one.
4. Choose the smallest ownership level using the component-ownership table in `docs/frontend/design-system.md`.
5. Reuse semantic CSS variables from `globals.css`. Add a token only when it expresses a reusable design decision; avoid repeating literal brand colors in JSX.
6. Prefer a server component. Add `"use client"` only for state, effects, event handlers, or browser-only APIs, and keep the client boundary narrow.
7. Implement semantic HTML and keyboard behavior first. Provide visible focus, programmatic labels, error associations, appropriate live regions, and text or icons in addition to color.
8. Cover loading, empty, error, disabled, success, and long-content behavior that the pattern can encounter. Preserve reduced-motion behavior and responsive layouts.
9. Add a focused Testing Library test for behavior and accessibility semantics. Extend Playwright only for a critical cross-page workflow.
10. Run formatting, the focused test, lint, and the production build.

## Pattern checklist

| Concern       | Expected treatment                                                             |
| ------------- | ------------------------------------------------------------------------------ |
| Color         | Semantic token; never the only status signal                                   |
| Spacing       | Tailwind scale unless an existing shell constraint requires an arbitrary value |
| Async content | Loading, empty, error, and populated states                                    |
| Forms         | Label, description/error linkage, disabled and submitting states               |
| Interaction   | Keyboard access, visible focus, sufficient target size                         |
| Motion        | Brief and optional; covered by the global reduced-motion rule                  |
| API data      | Parsed through the matching Zod schema                                         |

## Verification

During iteration, run the focused test from `apps/web`:

```bash
pnpm test -- <focused-test-file>
```

Before completion, run the frontend row of the verification matrix in the root `AGENTS.md`. Add the critical-browser-flow row when navigation, authentication, or another first-login-to-first-scan path changes.

## Common mistakes

- Creating a generic component for a pattern used only once.
- Copying a hex value already represented by a semantic token.
- Using a client component solely because a parent is client-rendered.
- Showing status through color alone.
- Testing class strings instead of user-visible behavior and semantics.
- Adding a new library when HeroUI, semantic HTML, or a small local component already suffices.

# Frontend design system

Competitor Scout uses a quiet editorial interface: warm neutral surfaces, a restrained coral accent, compact operational typography, and evidence-first information hierarchy. The system is implemented with Tailwind CSS 4, semantic CSS variables, HeroUI where it supplies useful behavior, and local React components.

## Principles

1. Prioritize readable evidence and operational state over decoration.
2. Use semantic tokens so meaning survives palette changes.
3. Make every state understandable without color alone.
4. Prefer server components and semantic HTML; add client behavior only where interaction requires it.
5. Extract a shared component when reuse or behavioral consistency is real, not merely possible.

## Foundations

The source of truth is `apps/web/src/app/globals.css`.

### Semantic color tokens

| Token                   | Role                                | Current value |
| ----------------------- | ----------------------------------- | ------------- |
| `--color-canvas`        | Application background              | `#f7f5f1`     |
| `--color-surface`       | Cards, controls, raised content     | `#fffefa`     |
| `--color-sidebar`       | Navigation background               | `#f1eee8`     |
| `--color-ink`           | Primary text                        | `#272421`     |
| `--color-muted`         | Secondary text                      | `#716b64`     |
| `--color-border`        | Default separators and outlines     | `#e5e0d9`     |
| `--color-accent`        | Primary actions and active emphasis | `#d34d50`     |
| `--color-accent-strong` | Hover and high-contrast accent text | `#b93e42`     |
| `--color-accent-soft`   | Accent tint backgrounds             | `#fae8e6`     |
| `--color-success`       | Completed or healthy state          | `#27845d`     |
| `--color-warning`       | Partial or attention state          | `#b7791f`     |
| `--color-danger`        | Failed or destructive state         | `#bd3035`     |

The custom slate scale provides warm neutrals. Existing Tailwind `blue-50` and `blue-700` aliases map to the coral accent for compatibility; new code should prefer semantic variables instead of treating blue as a product color. Do not add literal brand hex values to JSX when a semantic token fits.

### Shape and elevation

| Token              | Use                                           |
| ------------------ | --------------------------------------------- |
| `--radius-control` | Buttons, fields, compact interactive elements |
| `--radius-card`    | Cards, list rows, empty states                |
| `--radius-panel`   | Large grouped panels and shells               |
| `--shadow-card`    | Default surface elevation                     |
| `--focus-ring`     | Focus reinforcement for fields                |

Use Tailwind's spacing scale for layout. Arbitrary values are reserved for established shell constraints, icon sizing, or typography tuning that cannot be expressed clearly by the scale.

### HeroUI token mapping

HeroUI 3 resolves its own controls from semantic variables such as `--field-background`, `--field-border`, `--field-radius`, `--overlay`, `--accent`, `--border`, and `--muted`. A single `:root` block in `globals.css`, placed after the `@heroui/styles` import so its values win, maps those onto the workspace tokens above. The installed `@heroui/styles` package is the reference for which variable a given utility reads; see `dist/themes/shared/theme.css` for the mapping and `dist/components/` for per-component rules.

Change HeroUI's appearance in that block. Do not restyle HeroUI components individually with class overrides: the mapping keeps every current and future HeroUI control consistent, while per-component overrides drift.

### Typography

The sans stack begins with Avenir Next and falls back to system sans fonts. Page titles use `text-4xl font-semibold` with tight tracking supplied by `.app-content`. Section titles usually use `text-xl font-semibold`. Body text uses slate-600/700 with comfortable line height. `.eyebrow` is the standard compact uppercase contextual label.

Do not communicate hierarchy by shrinking important text below readable sizes. Uppercase labels should remain short and use deliberate letter spacing.

## Layout and surfaces

`AppShell` owns the responsive navigation and a content column capped at 1120px. Page views normally use `space-y-*` for vertical rhythm and semantic `header`, `section`, `article`, `nav`, `ol`, or `ul` elements.

- `.surface`: bordered, elevated content container.
- `.surface-interactive`: hover elevation for a genuinely clickable surface.
- `.card-target` with `.card-link`: whole-card or whole-row click target. The container carries `.card-target`, the single real `<Link>` inside carries `.card-link` and stretches over the container, and the container shows the focus ring while that link has focus. Put content that must stay independently interactive or selectable in `.card-above`. Pair it with `.surface-interactive` so the hover affordance and the click target describe the same area, and keep a visible textual cue such as an arrow so the card reads as navigation.
- `.empty-state`: dashed, quiet container for absent data.
- `.section-link`: compact accent link for secondary navigation.
- `.text-link`: inline link inside body copy or a heading, underlined so it does not rely on color alone. Evidence citations use it for the source title and for URLs found inside quoted source text.
- `.field-label` and `.select-control`: form label and native-select treatment.
- `.nav-link`, `.icon-button`, and `.brand-mark`: shell-specific patterns.

Keep shell classes in global CSS. Prefer a React primitive under `components/ui/` when a pattern has props, accessibility behavior, variants, or repeated markup. Keep one-page composition local to `components/pages/`.

## Workspace navigation

`PrimaryNavigation` carries the sections a reader acts on. Each is a destination someone opens to answer a question about competitors, not a view of how the system executed.

| Section       | Route          | Purpose                                                            |
| ------------- | -------------- | ------------------------------------------------------------------ |
| Dashboard     | `/`            | Active monitors, material updates, scans needing attention, digest |
| Competitors   | `/competitors` | Monitored companies; `/competitors/new` is the guided setup        |
| Updates       | `/findings`    | One detected change per row, filterable, each with linked evidence |
| Weekly Digest | `/briefs`      | Per-week narrative whose sections cite the updates behind them     |
| Settings      | `/settings`    | Profile, default schedule, usage totals, troubleshooting           |

Updates and the Weekly Digest are the same intelligence at two granularities: the atomic feed to search and cite, and the synthesized read for a week. Keep that relationship visible by linking digest sections back to individual updates.

Operator surfaces stay out of primary navigation. `/runs` and `/runs/{id}` render Scout Run lifecycle timelines, child agent tasks, and per-run token and cost usage, which is execution detail rather than intelligence. They remain fully routed and reachable in context — from Settings troubleshooting, dashboard scan warnings, a competitor's recent scans, guided setup during a first scan, and the provenance links on evidence, finding, and brief detail — so a reader arrives with a reason instead of browsing there. Apply the same rule to any future diagnostic view.

### Interface vocabulary

User-facing copy uses the reader's words, while routes, API paths, and schema fields keep the backend contract's names.

| Interface     | Contract     |
| ------------- | ------------ |
| update        | finding      |
| Weekly Digest | weekly brief |
| scan          | run          |

Renaming a surface is a copy change only; do not rename routes or Zod fields to match, because the backend Pydantic model is the contract's source of truth.

A section's name is a proper noun and keeps title case everywhere it names the section, including inside a sentence and inside a persisted string: `Weekly Digest`, `No Weekly Digest yet.`, `Weekly Digest: no material changes`. Common nouns for what a section contains stay lowercase in prose, as in "backed by the updates behind it" or "the scan that produced this digest". Sentence case remains the default for every other heading, label, button, and empty state.

Scan failure and partial-scan copy is backend-authored in the same way: `failure_summary` and `partial_summaries` carry reader-facing sentences, while `failure_code` and `partial_reasons` stay machine codes. Views render the sentences and fall back to the humanized code only when the backend has no copy for a reason yet, so new copy belongs in `services/runs.py`, not in a view. The vocabulary also governs strings the backend or the model authors and the interface renders verbatim, such as a weekly brief's title. Those are not frontend copy and cannot be corrected in a view, so check them when a surface is renamed. See `docs/architecture/agent-runtime.md` for the canonical empty-brief value and the migration it requires.

## Component ownership

| Need                                                      | Preferred owner                       |
| --------------------------------------------------------- | ------------------------------------- |
| Accessible behavior already provided and used             | HeroUI component with product styling |
| Generic repeated visual/interaction pattern               | `src/components/ui/`                  |
| Reusable product concept such as evidence or run timeline | `src/components/`                     |
| Page data fetching and composition                        | `src/components/pages/`               |
| Route metadata and parameter wiring                       | `src/app/`                            |

Do not wrap HeroUI solely to rename a prop. A wrapper is justified when it centralizes tokens, accessibility requirements, variants, or product behavior.

## States and status

Async features must account for loading, empty, error, and populated states. Mutations must also cover disabled/submitting, success feedback when needed, and recoverable failure.

Use these semantic roles consistently:

- Completed/healthy: success.
- Partial/attention: warning.
- Failed/destructive: danger.
- Running/selected/primary action: accent.
- Queued/inactive/secondary metadata: neutral slate.

Always pair color with a text label, icon, shape, or position. Use `role="alert"` for errors requiring immediate attention and `role="status"` or an appropriate `aria-live` region for non-interruptive updates. Avoid announcing decorative skeleton rows repeatedly; provide one meaningful loading label.

### Source management

A competitor's sources are settings, not a review queue, so the detail page never re-asks a decision the reader already made. `SourceManagementList` groups them by whether scans use them — Monitored, Awaiting review, Not monitored — and offers only the action that changes the current state: Stop monitoring for a monitored source, Monitor for one that is not, and Monitor plus Dismiss for a source still awaiting review. The `suggested` / `approved` / `rejected` contract values stay on the API; the interface names the reader's state.

Copy states the consequence next to the control: removing the last monitored source pauses daily monitoring, because the backend returns the competitor to discovering when no approved source remains. A source added from the detail page arrives awaiting review rather than silently entering the next scan.

## Forms and interaction

- Give every control a visible label or an equivalent accessible name.
- Connect help and error text with `aria-describedby`; set `aria-invalid` when validation fails.
- Preserve a visible `:focus-visible` treatment and keyboard-operable controls.
- Use a minimum practical target height of 40px for primary controls.
- Disable controls during in-flight mutations when duplicate submission is unsafe and expose submitting text.
- Do not rely only on placeholder text or native browser validation for domain rules.
- Do not ask for a machine identifier a reader would have to look up. Offer the recognizable choice and store the identifier the API needs.

A native `<select>` renders its open list through the operating system, which ignores page CSS, so `.select-control` can style the closed control but never the dropdown itself. Use HeroUI's `Select` with a `ListBox` whenever the list needs product styling or grouping. Keep a native `<select>` only where an element must submit inside a plain GET form without JavaScript, as the Updates and competitor-detail filters do.

`src/components/ui/TimezoneSelect.tsx` is the reference for a themed grouped dropdown. It shows 39 region-grouped zones by default and reveals the full IANA set on request. `@vvo/tzdb` supplies current offsets, region grouping, and alias groups; a unit test asserts every short-list zone is still canonical, so a tzdata rename fails the suite instead of shipping a dead option. Two cases it handles deliberately, worth repeating in any picker over an evolving external list: a stored value that is a deprecated alias resolves to its canonical entry, and a stored value the database no longer knows stays visible as its own option rather than being silently reassigned.

Animations should be brief and reinforce causality. The global reduced-motion query suppresses transitions and animations; new motion must remain compatible with it.

## Responsive behavior

Design narrow layouts first. Allow navigation and filter controls to wrap or scroll without hiding actions. Test long competitor names, URLs, findings, error messages, and translated-length text. Use `min-w-0`, truncation, and overflow handling deliberately rather than globally clipping content.

## Adding a pattern

Use the repository skill `add-ui-pattern`. Search existing components and HeroUI first, choose the smallest ownership level, reuse semantic tokens, implement accessibility and all relevant states, then add behavior-focused Testing Library coverage. Use Playwright for critical cross-page behavior rather than visual details.

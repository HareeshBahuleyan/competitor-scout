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

### Typography

The sans stack begins with Avenir Next and falls back to system sans fonts. Page titles use `text-4xl font-semibold` with tight tracking supplied by `.app-content`. Section titles usually use `text-xl font-semibold`. Body text uses slate-600/700 with comfortable line height. `.eyebrow` is the standard compact uppercase contextual label.

Do not communicate hierarchy by shrinking important text below readable sizes. Uppercase labels should remain short and use deliberate letter spacing.

## Layout and surfaces

`AppShell` owns the responsive navigation and a content column capped at 1120px. Page views normally use `space-y-*` for vertical rhythm and semantic `header`, `section`, `article`, `nav`, `ol`, or `ul` elements.

- `.surface`: bordered, elevated content container.
- `.surface-interactive`: hover elevation for a genuinely clickable surface.
- `.empty-state`: dashed, quiet container for absent data.
- `.section-link`: compact accent link for secondary navigation.
- `.nav-link`, `.icon-button`, and `.brand-mark`: shell-specific patterns.

Keep shell classes in global CSS. Prefer a React primitive under `components/ui/` when a pattern has props, accessibility behavior, variants, or repeated markup. Keep one-page composition local to `components/pages/`.

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

## Forms and interaction

- Give every control a visible label or an equivalent accessible name.
- Connect help and error text with `aria-describedby`; set `aria-invalid` when validation fails.
- Preserve a visible `:focus-visible` treatment and keyboard-operable controls.
- Use a minimum practical target height of 40px for primary controls.
- Disable controls during in-flight mutations when duplicate submission is unsafe and expose submitting text.
- Do not rely only on placeholder text or native browser validation for domain rules.

Animations should be brief and reinforce causality. The global reduced-motion query suppresses transitions and animations; new motion must remain compatible with it.

## Responsive behavior

Design narrow layouts first. Allow navigation and filter controls to wrap or scroll without hiding actions. Test long competitor names, URLs, findings, error messages, and translated-length text. Use `min-w-0`, truncation, and overflow handling deliberately rather than globally clipping content.

## Adding a pattern

Use the repository skill `add-ui-pattern`. Search existing components and HeroUI first, choose the smallest ownership level, reuse semantic tokens, implement accessibility and all relevant states, then add behavior-focused Testing Library coverage. Use Playwright for critical cross-page behavior rather than visual details.

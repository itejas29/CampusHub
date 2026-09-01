# CampusHub — Design System (Master Source of Truth)

Generated with `ui-ux-pro-max --design-system --variance 2 --motion 2 --density 8`,
then adapted to a **light-first** institutional palette (the raw match returned a
dark-tech palette; the "Research Lab / University Department" palette from
`--domain color` was substituted as the better product fit).

## Dials
| Dial | Value | Meaning |
|---|---|---|
| Variance | 2/10 | Centered, minimal, grid-based. No asymmetric/brutalist layouts. |
| Motion | 2/10 | Subtle micro-interactions only (150–250ms). No scroll choreography. |
| Density | 8/10 | Dense dashboard spacing scale (4 → 32px). |

## Style — Minimalism & Swiss
Clean, spacious, functional, high contrast, geometric, grid-based.
Best for: enterprise apps, dashboards, SaaS platforms, professional tools.
Light + dark both supported. Accessibility risk: low. Requires 4.5:1 text
contrast, keyboard nav, visible focus, reduced-motion support.

## Colour tokens (light)

Values below are the **as-shipped** ones. The status colours were darkened from
the initial palette after a measured contrast audit: 12px badge text on a soft
surface (e.g. `text-warning` on `bg-warning-soft`) sat at 4.2–4.4:1, just under
the 4.5:1 requirement.

| Token | Value | Notes |
|---|---|---|
| `--c-brand` | `#1E3A5F` | Institutional navy |
| `--c-accent` | `#1D4ED8` | Action blue — 5.49:1 on `accent-soft` |
| `--c-canvas` | `#F8FAFC` | Page background |
| `--c-surface` | `#FFFFFF` | Cards, sidebar, topbar |
| `--c-surface-muted` | `#F1F5F9` | Table headers, inset panels |
| `--c-ink` | `#0F172A` | Primary text |
| `--c-ink-muted` | `#475569` | Secondary text |
| `--c-ink-subtle` | `#556274` | Tertiary text — 5.93:1 on canvas |
| `--c-line` | `#E2E8F0` | Hairline |
| `--c-line-strong` | `#CBD5E1` | Input borders |
| `--c-success` | `#166534` | 6.49:1 on `success-soft` |
| `--c-warning` | `#854D0E` | 6.15:1 on `warning-soft` |
| `--c-danger` | `#B91C1C` | |
| `--c-info` | `#075985` | 6.59:1 on `info-soft` |

Each status colour also has a `-soft` surface and a `-fg` foreground. The `-fg`
pair matters in dark mode, where `--c-danger`/`--c-success`/`--c-info` become
*light* tints and therefore need dark text on top.

`.dark` redefines the same names. A component writes `bg-surface text-ink`,
never a raw hex.

## Typography — "Corporate Trust"
- Headings: **Lexend** (designed for reading proficiency; strong a11y)
- Body/UI: **Source Sans 3**
- Data/IDs: **JetBrains Mono** (roll numbers, codes, marks)
- Base 16px, body line-height 1.5, never below 12px.

## Spacing (density 8)
`4, 8, 12, 16, 24, 32, 48` — Tailwind `1,2,3,4,6,8,12`. Page gutter 24px desktop,
16px mobile. Card padding 20–24px. Table cell 12px × 16px.

## Anti-patterns to avoid
Gradients as decoration, glassmorphism, oversized hero graphics, emoji as icons,
fake statistics, decorative animation, one-off page styling, card-in-card nesting.

## Pre-delivery checklist
- [ ] SVG icons only (Lucide)
- [ ] `cursor-pointer` on every clickable
- [ ] Hover transitions 150–250ms
- [x] Text contrast ≥ 4.5:1 in both themes — audited programmatically across
      15 routes in light and dark; 0 failures
- [ ] Visible focus rings (never `outline:none` alone)
- [ ] `prefers-reduced-motion` respected
- [x] Responsive at 375 / 768 / 1024 / 1440 — `scrollWidth` measured on all 27
      routes at 375px; 0 horizontal overflow
- [x] Tables wrapped in `overflow-x-auto` (with `min-w-0` on the container, or a
      wide table stretches its grid parent instead of scrolling)
- [ ] Every list has empty / loading / error states


## Implementation notes worth keeping

- **Quote font families containing a digit.** Tailwind emits the stack verbatim,
  and an unquoted `Source Sans 3` is invalid CSS — the browser drops the whole
  `font-family` declaration and falls back to Times.
- **Do not set a colour on the global heading rule.** `h1..h4 { @apply text-ink }`
  overrides inheritance, so a heading inside a coloured surface renders dark on
  dark. Headings inherit from `body`, which already carries `text-ink`.
- **`min-w-0` on cards and scroll wrappers.** As grid/flex children the default
  `min-width: auto` lets wide content stretch the container.

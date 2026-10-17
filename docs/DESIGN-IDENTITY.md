# CampusHub visual identity

A record of the visual elements designed for CampusHub, and of the ones that
belong to others. Keep it current when the identity changes.

## Original to CampusHub

| Element | Where it lives | Description |
|---|---|---|
| **CampusHub mark** | `frontend/src/components/brand/Brand.tsx` (`CampusHubMark`), `frontend/public/favicon.svg` | A ring left open on the right (a "C", for Campus) carrying three nodes, each wired to a central hub, on a rounded tile with a navy → blue → indigo gradient. |
| **Energy-grid motif** | `Brand.tsx` (`EnergyGrid`) | Thin circuit traces with nodes that fade out from the right, a nod to PDEU as an energy university. Used in page headers and the navy heroes. |
| **Signature page header** | `frontend/src/components/ui/Misc.tsx` (`PageHeader`) | A rounded band with a 3 px brand-gradient rule on top and the energy grid on the right. |
| **Navy hero** | Student and faculty dashboards, sign-in page | The brand gradient (`#0B2545` → `#0F3B6C` → `#2563EB`) with the energy grid. |
| **Colour system** | `frontend/src/styles/index.css`, `frontend/tailwind.config.js` | Institutional navy `#0B2545`, interactive blue `#2563EB`, electric `#4F7CFF`, indigo `#6366F1`, violet `#8B5CF6`, on a `#F5F7FC` canvas, with a matching dark theme. |
| **Curriculum journey** | `frontend/src/features/academics/CurriculumPage.tsx` | The eight-semester step strip with credit progress and colour-dot requirement types. |

## Not ours — do not claim

- **PDEU's logo** (`frontend/public/pdeu_logo.png`) and the **campus photograph** (`frontend/public/pdeu_campus.jpg`) belong to Pandit Deendayal Energy University. They appear on the sign-in page with that meaning.
- **Fonts:** Lexend, Source Sans 3 and JetBrains Mono (Google Fonts, SIL Open Font License).
- **Icons:** Lucide (ISC licence).
- **Libraries:** React, Tailwind CSS, Framer Motion, TanStack Query (their own open-source licences).

Performance rule for the identity: decoration is static SVG and CSS only — no
looping animation, no large blur — so it never costs frames.

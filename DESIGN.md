# Design system

Working design system for the Clarke's Express Shoe Repair site, set at the template stage
on 2026-10-17. Reference, adopted traits and media roles: [design brief](kb/design-brief.md).
Feature behavior: [features](kb/features.md). The API contract in `docs/API.md` decides
data and routes; nothing here overrides it.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--paper` | `#F5F1EA` | Page ground |
| `--card` | `#FFFFFF` | Form cards, location cards, admin panels |
| `--tint` | `#ECE6DB` | Page ground behind form cards, status band |
| `--ink` | `#1B1A17` | Text, primary buttons |
| `--ink-soft` | `#5A554C` | Helper text, meta (meets 4.5:1 on paper and card) |
| `--rule` | `#D9D2C5` | Decorative hairlines only (1.5:1, not for controls) |
| `--field` | `#857E72` | Input, dropzone and chip borders (4.0:1 on card, 3.6:1 on paper) |
| `--oxblood` | `#6B1E1A` | Links, focus ring, error text and borders, selected states |
| `--open` | `#EBD46A` | Open-now pill only (ink text) |
| `--ok` | `#2F5D3A` | Success text and icons |

Type: `Libre Caslon Display` (headings, regular, tracking 0.08em) and `Hanken Grotesk`
(400/500/600 for body, labels, controls), both OFL and self-hosted as WOFF2 in
`app/public/fonts/`. Scale: hero 88/96 (phone 44/52), h2 48/58 (32/40), h3 24/29 (22/28),
body 16/24, small 14/20, label 13/16 uppercase tracking 0.08em.

Space: 8 px base; steps 4, 8, 12, 16, 24, 32, 48, 72, 128. Gutters 40 px desktop, 20 px
phone; content max 1360 px; reading measure 64ch; form card 640 px with 48 px padding
(24 px at 375 px).

Shape and depth: 2 px radius on buttons and inputs, 0 on photos, 4 px on cards; no shadows;
cards take a 1 px `--rule` border and controls a 1 px `--field` border; focus is a 2 px `--oxblood` outline with 2 px offset.

Motion: 150 ms `cubic-bezier(.4,0,.2,1)` for colour and border; 600 ms ease-out fade plus
8 px rise for sections entering view, replaying on re-entry; 700 ms 1.03 scale on photo
tiles; 280 ms slide for in-card view switches. `prefers-reduced-motion: reduce` removes
movement and keeps opacity changes under 150 ms. No autoplaying carousels or ribbons.

## Components and their states

- **Button**: primary (ink fill, paper text, uppercase label), secondary (text link with
  underline on hover), icon button (44 px target). States: hover, active, focus, disabled,
  busy (spinner replaces nothing; width locked, no layout shift).
- **Field**: label above, helper below, error replaces helper in `--oxblood` with an icon
  and `aria-describedby`; 48 px height; native `select`, `date`, `radio`, `checkbox`.
- **Choice group**: item type and "what it needs" as native radio/checkbox chips that wrap
  inside the card at 375 px and at 200% text.
- **Photo dropzone**: dashed `--field` border, native file input button inside; thumbnail
  chips with progress bar, remove button, error line (type, size, limit). No counters.
- **Location switch**: two-option segmented control (native radios); Dundalk reveals the
  call and text actions with a slide, input kept.
- **Notice band**: full-width, ink text on `--open` tint or `--tint`, one line plus
  reopening text; dismiss is not offered for closures.
- **Location card**: photo, name, open state pill (Bel Air only), hours list, rear-entrance
  landmark note, Directions and Call (and Text for Dundalk).
- **Status line**: words only (Received, Being reviewed, Estimate ready, ...), current step
  emphasised in ink, past steps in `--ink-soft`, no numbers or step counts.
- **Estimate panel**: amount or range typed by staff, the fixed estimate wording, three
  native-button responses.
- **Before/after**: native `input type=range` driving a clip; only for aligned pairs.
- **SVG icons**: one 24 px stroke set (arrow, phone, message, map pin, upload, check,
  alert, close, chevron); no text arrows or emoji.

## Proposed frontend structure (build round; waits for committed `docs/API.md`)

Vite 7 multi-page build to `app/dist`, plain HTML, CSS and browser ES modules, no UI
framework, matching the contract's ownership table.

```
app/
  index.html                 home
  request.html               photo repair request (deep-linkable, ?item= preselect)
  status.html                status by token and lookup form
  admin/login.html           sign-in shell
  admin/index.html           inbox, detail, ticket, settings, team, outbox views
  vite.config.mjs            multi-page inputs, dev proxy per docs/API.md
  public/fonts/              self-hosted WOFF2 plus OFL texts
  public/media/              optimised AVIF/WebP/JPEG renditions (2-3 widths each)
  src/styles/tokens.css      the tokens above
  src/styles/base.css        reset, type, layout, focus, reduced motion
  src/styles/components.css  shared components
  src/styles/admin.css       admin layout using the same tokens
  src/lib/api.js             fetch wrapper: bootstrap/CSRF, idempotency keys, error shapes
  src/lib/motion.js          one IntersectionObserver for entrances, paused when hidden
  src/lib/hours.js           open-now rendering from /api/v1/locations (server is truth)
  src/pages/home.js
  src/pages/request.js       form state, local draft, validation messages
  src/pages/photo-upload.js  draft photo uploads, progress, retry, remove
  src/pages/status.js
  src/pages/admin/*.js       one module per admin view
  src/icons.svg              SVG sprite
```

Remove the placeholder `xs-stage` meta and fill `app/xs-check.json` required links
(tel, sms, Maps, social) when the real pages land.

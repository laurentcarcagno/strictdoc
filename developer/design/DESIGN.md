---
name: THOR · Hemeria Design System
description: Sharp, sovereign mission-console UI for an internal engineering reference tool. Hemeria Charte Graphique 2025.
colors:
  sovereign-deep-blue: "#12293A"
  tricolor-blue: "#174082"
  console-sky: "#006EB1"
  tricolor-red: "#C80A26"
  cold-mist: "#F0F7FC"
  instrument-white: "#FCFDFE"
  hover-mist: "#E6F3FA"
  muted-mist: "#DBE7F0"
  selection-veil: "#CEE5FC"
  console-border: "#C2DDF0"
  ink: "#001423"
  dim-ink: "#43474C"
  mute-ink: "#73777D"
  signal-success: "#1F8A4C"
  signal-warning: "#C68A00"
  signal-danger: "#BA1A1A"
  pill-success-bg: "#EAF6EE"
  pill-warning-bg: "#FBF3DC"
  pill-danger-bg: "#FBE9E9"
typography:
  display:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0.04em"
  h1:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "0.04em"
  h2:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    letterSpacing: "0.04em"
  h3:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "0.02em"
  body:
    fontFamily: "IBM Plex Sans, system-ui, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.12em"
  eyebrow:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.18em"
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontWeight: 500
    letterSpacing: "0.02em"
rounded:
  none: "0"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.console-sky}"
    textColor: "{colors.instrument-white}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "32px"
  button-deep:
    backgroundColor: "{colors.sovereign-deep-blue}"
    textColor: "{colors.instrument-white}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "32px"
  button-ghost:
    backgroundColor: "{colors.instrument-white}"
    textColor: "{colors.sovereign-deep-blue}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "32px"
  button-danger:
    backgroundColor: "{colors.instrument-white}"
    textColor: "{colors.signal-danger}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "32px"
  input-search:
    backgroundColor: "{colors.hover-mist}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "5px 10px"
  input-text:
    backgroundColor: "{colors.instrument-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "6px 10px"
  input-text-focus:
    backgroundColor: "{colors.instrument-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "5px 9px"
  input-text-disabled:
    backgroundColor: "{colors.hover-mist}"
    textColor: "{colors.mute-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "6px 10px"
  card:
    backgroundColor: "{colors.instrument-white}"
    rounded: "{rounded.none}"
  stat-card:
    backgroundColor: "{colors.instrument-white}"
    rounded: "{rounded.none}"
    padding: "18px 20px"
  pill-success:
    backgroundColor: "{colors.pill-success-bg}"
    textColor: "{colors.signal-success}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
  pill-warning:
    backgroundColor: "{colors.pill-warning-bg}"
    textColor: "{colors.signal-warning}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
  pill-danger:
    backgroundColor: "{colors.pill-danger-bg}"
    textColor: "{colors.signal-danger}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
  pill-info:
    backgroundColor: "{colors.hover-mist}"
    textColor: "{colors.console-sky}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
  chip-default:
    backgroundColor: "{colors.instrument-white}"
    textColor: "{colors.dim-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "5px 10px"
  chip-active:
    backgroundColor: "{colors.sovereign-deep-blue}"
    textColor: "{colors.instrument-white}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "5px 10px"
  tag-default:
    backgroundColor: "{colors.hover-mist}"
    textColor: "{colors.sovereign-deep-blue}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 6px"
    height: "18px"
  tag-solid:
    backgroundColor: "{colors.sovereign-deep-blue}"
    textColor: "{colors.instrument-white}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 6px"
    height: "18px"
  table-header:
    backgroundColor: "{colors.sovereign-deep-blue}"
    textColor: "{colors.instrument-white}"
    typography: "{typography.label}"
    padding: "9px 12px"
---

# Design System: THOR · Hemeria

## 1. Overview

**Creative North Star: "The Tricolor Console"**

THOR is built like an instrument panel for engineers, not a card library for managers. The Hemeria visual language fuses two things that rarely cohabit: the ceremonial weight of a tricolor (blue, white, red) and the live posture of a mission console. The page header is literally a 4px tricolor stripe; the sidebar is sovereign deep blue; the primary action color is a saturated console-sky that reads as "live signal." The work surface is an off-white tinted toward sky-blue (`#F0F7FC`), so even at rest the screen feels as if it sits inside a console rather than on a marketing site.

The system is sharp by doctrine. Every primitive in `apps/web/src/index.css` lines 1704-1999 ships with `border-radius: 0`. There are no shadows anywhere in the Hemeria block; depth comes from tonal layering (mist → surface → veil), 1px borders, and one signature 3px sky-blue top stripe on stat cards. Type does most of the talking: IBM Plex Sans for headings (SemiBold, tracked) and for body (Regular), IBM Plex Mono for identifiers, with uppercase wide-tracked labels acting as small mission patches across cards, tabs, and table headers.

Hemeria explicitly rejects the soft-SaaS aesthetic. No glassmorphism, no gradients, no rounded corners, no apologetic warmth. It also rejects the opposite trap: this is not Bloomberg Terminal black-and-amber maximalism. The palette is bright and instrumented, contrast is calm, the dominant color in any given screen is white space, and the brand red appears only as ceremony (tricolor stripe, brand-mark dot in the sidebar lockup). Confidence without bluster, per PRODUCT.md.

**Key Characteristics:**
- Sharp corners everywhere. No `border-radius` on any primitive.
- Flat surfaces. No shadows. Depth via 1px borders and tonal layering.
- Tricolor stripe as the page-level signature.
- IBM Plex Sans (SemiBold headings, Regular body) + IBM Plex Mono for identifiers.
- Uppercase wide-tracked labels as mission-patch chrome.
- Sky-blue is the only action color. Red is ceremonial only.

## 2. Colors: The Tricolor Console Palette

The palette is small, cold, and tightly governed. One brand triad (deep-blue, sky-blue, red) carries the identity; one tinted neutral ramp (mist → border → ink) carries the content; four signal colors (success, warning, danger, info) carry state. Every neutral is tinted toward sky-blue, never pure gray.

### Primary
- **Sovereign Deep Blue** (`#12293A`): The gravitas color. Sidebar background, page-header titles, table-header background, strong borders, deep button variant, ghost button text. Carries roughly 18-22% of any populated screen by area (the sidebar plus table headers). The system's center of mass.
- **Console Sky** (`#006EB1`): The action and live-signal color. Primary buttons, the 3px stripe atop stat cards, sidebar active-item indicator, focus rings, links, info pill. Used only where action or attention is intended; never for decoration.

### Tertiary (ceremonial)
- **Tricolor Blue** (`#174082`): Appears only inside the page-header stripe. Not interchangeable with Sovereign Deep Blue or Console Sky.
- **Tricolor Red** (`#C80A26`): Appears only in the page-header stripe and the brand-lockup dot in the sidebar (`THOR·` punctuation). It is not an action color, not a delete color, not an emphasis color. The danger semantic uses Signal Danger, not this.

### Neutral
- **Cold Mist** (`#F0F7FC`): App background. Tinted sky-blue at very low chroma — never neutral gray.
- **Instrument White** (`#FCFDFE`, canonical `oklch(99% 0.005 235)`): Working surfaces. Cards, tables, inputs against the mist. Technically a near-white tinted sky-blue at chroma 0.005 — invisible in normal use, visible against pure white as a faint cool cast. Per the tinted-neutrals doctrine.
- **Hover Mist** (`#E6F3FA`): Table row hover, search-field background, ghost-button hover. The "softer" mist.
- **Muted Mist** (`#DBE7F0`): Deeper fill, used sparingly for contrast against Hover Mist.
- **Selection Veil** (`#CEE5FC`): Active table row tint. Reads as "you are looking at this one."
- **Console Border** (`#C2DDF0`): The 1px outline on every card, table, input, toolbar, footrow.
- **Ink** (`#001423`): Body text. Near-black, tinted blue.
- **Dim Ink** (`#43474C`): Secondary text, table cells where mute is wrong.
- **Mute Ink** (`#73777D`): Helper text, eyebrows, table headers' subordinate elements.

### Signal (state, not decoration)
- **Signal Success** (`#1F8A4C`) on `#EAF6EE` for the success status pill.
- **Signal Warning** (`#C68A00`) on `#FBF3DC` for the warning status pill.
- **Signal Danger** (`#BA1A1A`) on `#FBE9E9` for the danger status pill and danger-button outline.
- **Console Sky** on Hover Mist for the info status pill (the action color does double duty here; this is intentional, signal=info means "look here, take action").

### Named Rules

**The Sky-Is-Action Rule.** Console Sky (`#006EB1`) means "do something" or "this is selected/active." It is reserved for primary buttons, the stat-card top stripe, the sidebar active indicator, focus rings, links, and the info status. It is never used as a decorative fill, gradient stop, or background tint.

**The Red-Is-Ceremony Rule.** Tricolor Red (`#C80A26`) appears only in the page-header stripe and the sidebar brand-lockup dot. It is not the danger color. It is not the destructive-action color. Engineers should not see it move or change in response to interaction.

**The Tinted-Neutrals Rule.** Every gray-feeling color in the system is tinted sky-blue at very low chroma. Pure neutral gray belongs to other systems, not this one.

## 3. Typography

**Display Font:** IBM Plex Sans SemiBold (system-ui fallback)
**Body Font:** IBM Plex Sans (system-ui fallback)
**Label/Mono Font:** IBM Plex Mono (ui-monospace fallback)

**Character:** One family does everything, which keeps the system sober: IBM Plex Sans is a grotesque with an engineered, technical feel, legible at 13px. Headings stand apart by weight (SemiBold) and tracking, labels by weight (Bold) and wide-tracked capitals. IBM Plex Mono carries the part numbers, document references, and tabular numerics that ARE the product, and shares its proportions with the Sans.

### Hierarchy

- **Display** (IBM Plex Sans 600, 32px / 1.15, `0.04em`): Reserved for the largest page titles. Rare in normal app use; appears in the dashboard or hero contexts. Color: Sovereign Deep Blue.
- **H1** (IBM Plex Sans 600, 26px / 1.15, `0.04em`): The page title rendered by `<PageHeader>`. Color: Sovereign Deep Blue.
- **H2** (IBM Plex Sans 500, 18px, `0.04em`): Section headings within a page. Color: Sovereign Deep Blue.
- **H3** (IBM Plex Sans 600, 15px, `0.02em`): Subsection headings, modal titles. Color: Ink (not Deep Blue — the smaller weight steps down).
- **Body** (IBM Plex Sans 400, 13px / 1.45): All running text, form values, table cells. Color: Ink. Cap prose at 65-75ch; tables and dense panels may exceed.
- **Label** (IBM Plex Sans 700, 11px, `0.12em`, UPPERCASE): Card titles, buttons, status pills, chips, table headers, footrow text. The mission-patch typography. Color: contextual.
- **Eyebrow** (IBM Plex Sans 700, 11px, `0.18em`, UPPERCASE): The line above a page title (e.g. *"Mission Console"* over the dashboard title). Wider tracking than Label. Color: Mute Ink.
- **Mono** (IBM Plex Mono 500, `0.02em`, `tabular-nums`): Part numbers, document references, codes, timestamps. Always tabular for column alignment. Color: contextual.

### Named Rules

**The Identifier-Is-Mono Rule.** Every part number, document reference, affaire code, user UUID, timestamp, and tabular numeric is rendered in IBM Plex Mono with `font-variant-numeric: tabular-nums`. This is non-negotiable. Identifiers are the lingua franca of THOR; they must be visually distinguishable from prose at a glance and column-alignable in tables.

**The Heading-Weight Rule.** Headings (H1-H3, Display) are IBM Plex Sans in SemiBold (500-600) with 0.02-0.04em tracking, in Sovereign Deep Blue. Wide tracking and UPPERCASE belong to labels and eyebrows only. Body text, button labels, form inputs, table cells, error messages, toasts: Regular or Bold, never the heading weight and tracking. Using the heading style for body text breaks the system.

**The Wide-Track Caps Rule.** All `text-transform: uppercase` text in the system uses 0.12em-0.18em letter-spacing (depending on size). Uppercase without wide tracking looks shouty; with the tracking it reads as official. The two go together.

## 4. Elevation

The system is **flat by doctrine.** There are no `box-shadow` declarations in the Hemeria token block. Depth is conveyed through three mechanisms, in this order:

1. **Tonal layering**: Cold Mist (page) → Instrument White (cards/tables) → Hover Mist (interaction) → Selection Veil (selected). Stepping the surface temperature, not adding lift.
2. **1px borders** in Console Border (light) or Sovereign Deep Blue (strong). The toolbar/table/footrow stack uses `margin-bottom: -1px` so adjacent panels share their edges into a single continuous frame.
3. **One signature accent: the 3px Console Sky top stripe on stat cards.** This is the system's only "decoration as depth," and it is reserved for stat cards. Adding it elsewhere dilutes it.

### Named Rules

**The No-Shadow Rule.** No element in the Hemeria layer carries a `box-shadow`. If something needs to feel "raised," step its surface tone (Instrument White on Cold Mist) or strengthen its border (Sovereign Deep Blue instead of Console Border). Drop shadows are forbidden, even subtle ones.

**The Reticle Rule.** The `<CornerFrame>` primitive draws four 12px corner brackets in Sovereign Deep Blue around its content (the aerospace-instrument tick frame). It is a heavy signature; use it sparingly — typically once per page on the most important content region. Wrapping every panel in it is wrong.

## 5. Components

Components are sharp-cornered, 1px-bordered, and inherit color from the palette above. Every interactive primitive has explicit hover and disabled states; transition duration is 120ms across the board.

### Buttons (`<Btn>` in Hemeria.tsx)
- **Shape:** Rectangular. `border-radius: 0`. Height 32px (sm: 26px, lg: 40px), padding `0 14px`.
- **Typography:** Label (IBM Plex Sans 700, 11-13px, `0.12em`, UPPERCASE).
- **Primary** (`variant="primary"`): Console Sky background + Instrument White text. The default.
- **Deep** (`variant="deep"`): Sovereign Deep Blue background + Instrument White text. For higher-gravitas actions (e.g. "Confirm migration").
- **Ghost** (`variant="ghost"`): Transparent background + Sovereign Deep Blue text + Sovereign Deep Blue border. For secondary actions (Export, Cancel).
- **Danger** (`variant="danger"`): Transparent background + Signal Danger text + Signal Danger border. Inverts to filled on hover.
- **Hover:** `filter: brightness(1.07)` for filled variants, Hover Mist background for ghost. No transform, no shadow.
- **Disabled:** `opacity: 0.55`, `cursor: not-allowed`. No color change.

### Status Pills (`<StatusPill kind="..." />`)
- **Shape:** Rectangular, `padding: 2px 8px`, 1px border in matching signal color.
- **Typography:** Label (IBM Plex Sans 700, 10px, `0.14em`, UPPERCASE).
- **Anatomy:** 7px square dot in `currentColor` + caps text. The dot is square, never round — sharp-corner doctrine extends to micro-elements.
- **Variants:** success / warning / danger / info / default. The four signal variants tint the background and use the matching signal color for border and text. The `default` variant (no modifier class) is a neutral "unspecified state" pill — Instrument White background, Sovereign Deep Blue 1px border, Dim Ink text. Use `default` when the state is genuinely unknown or when none of the four signal kinds applies; never use it as a fallback for "we forgot to map this value."

### Tags (`<Tag variant="..." />`)
- **Shape:** Rectangular, 18px tall, `padding: 0 6px`, 1px border.
- **Typography:** Label (IBM Plex Sans 700, 10px, `0.10em`, UPPERCASE).
- **Default:** Hover Mist background + Sovereign Deep Blue text.
- **Solid:** Sovereign Deep Blue background + Instrument White text. For categorical stress.
- **Accent:** Console Sky background + Instrument White text. For active filter selection.
- **Ghost:** Transparent background + Dim Ink text + Console Border.

### Filter Chips (`<FilterChip>`)
- **Default:** Instrument White background, Console Border outline, Dim Ink text. Label uppercase + value.
- **Active:** Sovereign Deep Blue background, white text. The chip becomes ceremonial when selected.
- Used in toolbars to express table filters (`Famille: ELEC`, `Affaire: AF001`).

### Search Input (`<SearchInput hotkey="⌘K">`)
- **Style:** Hover Mist background (no border on the input itself; sits inside the toolbar's outer border), 12px IBM Plex Sans body text.
- **Anatomy:** Lucide search icon (13px, Mute Ink) on the left + input + `⌘K` hotkey hint on the right (IBM Plex Mono 10px, Mute Ink).
- The hotkey hint is a system-wide commitment: the keyboard shortcut for search is always present in the chrome.

### Form Inputs (text, select, textarea)
No dedicated `<Input>` primitive in `Hemeria.tsx` yet, but the doctrine is clear from the Search Input and the broader system. Inputs follow these rules.

- **Shape:** Rectangular. `border-radius: 0`. `padding: 6px 10px` for text inputs, `padding: 5px 8px` for select-style controls.
- **Default:** Instrument White background, 1px Console Border, 13px IBM Plex Sans body text in Ink. Placeholder: Mute Ink.
- **Hover:** Border steps to Sovereign Deep Blue. No background change.
- **Focus:** Border to Console Sky, 2px solid (replacing the 1px Console Border, no offset). Background unchanged. No glow, no shadow ring.
- **Error:** Border to Signal Danger, with a Signal Danger 11px helper line below the field. Field background unchanged (no red tint).
- **Disabled:** Background to Hover Mist, text to Mute Ink, cursor `not-allowed`. Border unchanged.
- **Label:** Above the input, 11px IBM Plex Sans 700 0.12em UPPERCASE in Dim Ink. Always present; placeholder is supplementary, never a label substitute.
- **Select / dropdown:** Same shape as text input; the chevron (Lucide `ChevronDown` 14px) sits on the right in Mute Ink. Open-state options drop into a sharp Instrument White panel with 1px Console Border and Hover Mist hover rows.
- **Textarea:** Same shape; resize handle at bottom-right is the browser default (do not style away).

### Cards (`<Card title="..." meta="...">`)
- **Shape:** Rectangular, `border: 1px solid Console Border`, no radius, no shadow.
- **Header (optional):** `padding: 10px 14px`, bottom border in Console Border. Title in Label (uppercase Sovereign Deep Blue) on the left, meta in Mono (Mute Ink) on the right.
- **No nested cards.** A card contains content. If you find yourself wrapping a card inside a card, restructure.

### Stat Cards (`<StatCard label value icon delta?>`) — **signature**
- **Shape:** Rectangular, `padding: 18px 20px`, 1px Console Border, no shadow.
- **Signature:** A 3px Console Sky stripe across the top edge (`::before` pseudo-element). This is the only "decoration" in the system; it carries the live-signal feeling onto the dashboard.
- **Anatomy:** Label (uppercase Mute Ink) above a value rendered in Display IBM Plex Sans 700 30px Sovereign Deep Blue, with optional delta (Mono 11px Signal Success) and right-side icon framed by a 1px Strong Border square (40×40).
- This component is forbidden from being repeated identically in a 4-up "metric grid" — see Don'ts.

### Tables (`<Table>` + `<Th sort? w?>` + `<Td mono? mute? center?>`)
- **Header:** Sovereign Deep Blue background, Instrument White text, IBM Plex Sans 600, 9.5px, `0.18em`, UPPERCASE. Right border on each th in `rgba(255,255,255,.08)` for column dividers.
- **Body:** 12px IBM Plex Sans, 1px Console Border between rows and columns.
- **Hover:** Row tint to Hover Mist.
- **Selected row:** `.row-active` tints to Selection Veil. Stronger than hover, reads as state.
- **Mono cell:** `<Td mono>` switches the cell to IBM Plex Mono with tabular-nums. Use for every PN, DocRef, code, timestamp.

### Sortable Table Header (`<Th sort="asc" | "desc" | null>`)
The Hemeria `<Th sort>` is the canonical sortable-header primitive. Click cycles `null → asc → desc → null`.

- **Default (sortable, inactive):** Header text + a 5px chevron-pair indicator in Mute Ink to the right. Cursor: `pointer`.
- **Active asc:** Indicator becomes a 5px solid triangle pointing down (text top, triangle below) in Console Sky. Header text remains Instrument White.
- **Active desc:** Same triangle rotated 180°, still Console Sky.
- **Hover (any state):** Subtle background lift to a 6% white overlay on the deep-blue header (`rgba(255, 255, 255, 0.06)`), no other change.

The older `apps/web/src/components/SortableTableHeader.tsx` (raw `<th>` with Bootstrap classes and Lucide ArrowUpDown icons) is **migration debt**. New tables must use the Hemeria `<Th sort>`; existing call sites should be migrated.

### Tabs (`<Tabs tabs={[...]} active onChange>`)
- **Style:** Bottom border row in Console Border (2px). Active tab gets a Console Sky bottom border (2px) overlapping the row, and Sovereign Deep Blue text. Inactive: Mute Ink, IBM Plex Sans 600, 11px, `0.18em`, UPPERCASE.

### Modal (proposed Hemeria pattern)
There is no `<Modal>` primitive in Hemeria.tsx yet. The current modals in `PreferencesHeader.tsx` use Bootstrap classes (`modal d-block modal-dialog-centered modal-content modal-header modal-body modal-footer`) and are scheduled migration debt. The doctrinal Hemeria modal:

- **Backdrop:** `rgba(0, 20, 35, 0.55)` — Ink at 55% opacity. Sharp, non-blurred. No `backdrop-filter`.
- **Dialog:** Instrument White surface, 1px Sovereign Deep Blue border, no radius, no shadow. Width 480px (sm) / 640px (md) / 880px (lg). Centered.
- **Header:** Sovereign Deep Blue background, 14px padding, Instrument White H3 (IBM Plex Sans 600, 15px, `0.04em`) on the left + a square icon-button close (`<IconBtn>`, 24×24, `X` 14px) on the right. The header is the modal's mission patch.
- **Body:** 18px padding, Ink 13px IBM Plex Sans, normal flow content.
- **Footer:** 12px padding, 1px Console Border top, right-aligned action buttons. Order: Ghost (Cancel) then Primary (Confirm). Danger actions use the Danger button variant on the left.
- **Close affordances:** `Esc` key, click on backdrop, and the header X button. All three must work.
- **Focus trap:** required. Focus moves to the first interactive element on open and returns to the trigger on close.

### Toast (proposed Hemeria pattern)
The current `ToastContext.tsx` uses Bootstrap classes (`toast show text-bg-success`, `btn-close-white`) — also migration debt. The doctrinal Hemeria toast:

- **Stack position:** Top-right, 16px from edges, 8px gap between toasts. Stack grows downward.
- **Shape:** Rectangular, sharp corners, 1px border in matching signal color, no shadow.
- **Anatomy:** 18px Lucide icon (CheckCircle / XCircle / AlertTriangle / Info) in signal color on the left, message text (IBM Plex Sans 13px Ink) in the middle, `X` icon-button (14px Mute Ink) on the right. 10px vertical / 14px horizontal padding.
- **Background tint:** the same signal-tinted backgrounds as Status Pills (`#EAF6EE` for success, `#FBE9E9` for danger, `#FBF3DC` for warning, Hover Mist for info).
- **Auto-dismiss:** 5 seconds. Pause on hover.
- **Animation:** Fade-in from `opacity: 0` over 120ms; no slide, no scale, no bounce.
- **No "success!" exclamation marks.** Per PRODUCT.md tone: *"Préférences enregistrées."* not *"Préférences enregistrées !"*.

### Empty State
For tables and lists with zero results. The Hemeria empty state is forceful and instrumented, never apologetic.

- **Layout:** Centered within the data region, 60px vertical padding minimum.
- **Anatomy (top to bottom):** A 24px Lucide icon (Mute Ink) in a 1px Console Border 48×48 square frame; an Eyebrow (uppercase Mute Ink) saying the category (e.g. *"Aucun résultat"*); an H3 in Ink stating the condition (*"Aucune affaire ne correspond aux filtres."*); optionally one Ghost button (*"Réinitialiser les filtres"*). Maximum 280px content width.
- **No illustrations.** No friendly emoji, no cartoon mascots, no decorative graphics. The empty state is data, not consolation.

### Sidebar (`hem-sidebar` in `AppLayout.tsx`)
- **Background:** Sovereign Deep Blue. Text: white at 70% opacity, full white when active.
- **Brand lockup at top:** `THOR·ENGINE` in IBM Plex Sans 700 14px, `0.18em`, with the `·` separator in Tricolor Red (the only place red appears outside the page-header stripe). Subtitle below in 9px UPPERCASE at 45% opacity.
- **Nav item active state:** A 3px Console Sky left border + 18% Console Sky background tint + white text + sky-blue icon. This is a deliberate functional exception to the project-wide "no side-stripe borders" doctrine: it is the standard sidebar active affordance, not decoration.
- **User footer:** 28×28 sky-blue square avatar (sharp corners) with 2-letter initials in IBM Plex Sans 700 11px, name + role to the right, logout icon-button on the far right.
- **Collapsed state:** width drops to 64px, labels hide, icons remain.

### Page Header (`<PageHeader eyebrow title sub actions>`) — **signature**
- **Anatomy:** A 4px-wide tricolor stripe (vertical, blue / white-with-border / red, equal thirds) running the full height of the header block. To the right: an optional Eyebrow (uppercase Mute Ink, e.g. *"Mission Console"*), the page title (IBM Plex Sans H1 26px Sovereign Deep Blue), an optional sub-line (Dim Ink 13px). Action buttons sit on the far right.
- **Bottom border:** 1px Console Border, with 14px padding-bottom and 20px margin-bottom — the visual seam between header and content.
- **Used by every page** via `<PreferencesHeader>`, which wraps `<PageHeader>` and adds the user/preferences modal trigger on the right.

### Corner Frame (`<CornerFrame>`) — **signature**
- Four 12px reticle ticks (corner brackets) in Sovereign Deep Blue at the corners of the content. 2px stroke. Pure visual signal: this is an instrument readout.
- Used sparingly. Wrapping every panel in it dilutes it.

## 6. Do's and Don'ts

### Do:

- **Do** use the `<PageHeader>` (via `<PreferencesHeader>`) as the top of every page. The tricolor stripe is the project's signature — every screen earns it.
- **Do** render every part number, document reference, affaire code, user ID, and timestamp in IBM Plex Mono with tabular-nums. This is the identifier-is-mono rule.
- **Do** use sharp corners on every primitive. `border-radius: 0` is the default; do not introduce radius on new components.
- **Do** use 1px borders and tonal layering for depth. Cold Mist beneath Instrument White beneath Hover Mist beneath Selection Veil.
- **Do** stack toolbar / table / footrow with `margin-bottom: -1px` so adjacent panels share their edges into one continuous frame.
- **Do** write button labels and pill text in IBM Plex Sans 700, 0.12em UPPERCASE. The mission-patch register.
- **Do** keep transitions at 120ms on `filter`, `background`, and `color`. No transforms, no orchestration.
- **Do** use `<StatusPill>` with semantic `kind` for any state indication. `success` / `warning` / `danger` / `info` are the only options; do not invent new kinds.
- **Do** use Hover Mist for interactive feedback (table-row hover, ghost-button hover, search-field background). It is the system's "you are touching this" tint.

### Don't:

- **Don't** use glassmorphism. No `backdrop-filter: blur`, no frosted panels, no semi-transparent surfaces stacked over content. PRODUCT.md bans this by name.
- **Don't** use gradients. Not on buttons, not on backgrounds, not on text (`background-clip: text` is forbidden), not on accent decoration. Every fill is a single solid color.
- **Don't** introduce `border-radius` on any new component. The system is sharp-cornered as doctrine. Pills, tags, avatars, status dots, icons — all square.
- **Don't** add `box-shadow` for elevation. Use tonal layering or border weight instead. The no-shadow rule is non-negotiable.
- **Don't** use Tricolor Red (`#C80A26`) for danger semantics, delete buttons, or error states. Red is ceremonial (page-header stripe + brand-lockup dot only). Use Signal Danger (`#BA1A1A`) for state.
- **Don't** give body text, button text below 11px, table cells, form inputs, error messages, or toasts the heading style (SemiBold with tracking). The heading style is for headings and the eyebrow line; everywhere else is Regular or Bold at normal tracking.
- **Don't** use pure neutral gray. Every neutral in the system is tinted sky-blue at low chroma. Replacing a `--hem-border` value with `#cccccc` breaks the palette.
- **Don't** stack `<StatCard>` four-up in a uniform metric grid (the SaaS hero-metric template). The stat card is signature; arranging it as identical repeating tiles dissolves it. PRODUCT.md and the shared design laws ban this pattern.
- **Don't** wrap `<Card>` inside `<Card>`. Nested cards are always wrong here — use a single card with sectioned content (header divider) instead.
- **Don't** use side-stripe colored borders on cards, callouts, alerts, or list items as decoration. The sidebar nav-active indicator is a documented functional exception; do not extend the pattern to other surfaces.
- **Don't** write apologetic, warm, or chatty UX copy. *"Affaire introuvable. Vérifiez le code."* not *"Désolé, cette affaire n'existe pas."* No "Oops," no exclamation marks, no friendly suggestions. Per PRODUCT.md.
- **Don't** use the `<CornerFrame>` reticle on every panel. It is a heavy signature — once per page, on the most important region.
- **Don't** extend the Bootstrap residue. The following call sites are documented migration debt and must not be copied into new work: `class="modal d-block modal-dialog-centered"` (PreferencesHeader.tsx modals), `class="toast show text-bg-success"` (ToastContext.tsx), `<SortableTableHeader>` component (use Hemeria `<Th sort>` instead), `class="btn-close"` / `text-bg-*` / `text-muted` Bootstrap utility classes. New modals, toasts, and sortable tables follow the Hemeria patterns above.

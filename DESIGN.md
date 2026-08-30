---
name: GundHere
description: A measured hobby-shop inspection bench for finding the right Gunpla kit from imperfect names.
colors:
  work-surface: "#e9edeb"
  inspection-paper: "#f8faf8"
  paper-deep: "#dde4e0"
  ink-green: "#10251f"
  ink-soft: "#445a52"
  rule-line: "#9eaca6"
  rule-line-dark: "#536861"
  safety-orange: "#e34b22"
  safety-orange-dark: "#a72d10"
  signal-green: "#13724c"
  caution-amber: "#9b4b00"
  selection-wash: "#fff3ed"
typography:
  display:
    fontFamily: '"Barlow Condensed", "Arial Narrow", sans-serif'
    fontSize: "clamp(2.35rem, 4.6vw, 4.9rem)"
    fontWeight: 700
    lineHeight: 0.96
    letterSpacing: "-0.035em"
  title:
    fontFamily: '"Barlow Condensed", "Arial Narrow", sans-serif'
    fontSize: "1.22rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  body:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "0.72rem"
    fontWeight: 760
    lineHeight: 1.35
    letterSpacing: "0.06em"
rounded:
  panel: "12px"
  pill: "999px"
  round: "50%"
spacing:
  xs: "7px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "22px"
  2xl: "34px"
components:
  button-primary:
    backgroundColor: "{colors.safety-orange}"
    textColor: "#ffffff"
    padding: "14px 20px"
  button-primary-hover:
    backgroundColor: "{colors.safety-orange-dark}"
    textColor: "#ffffff"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.ink-green}"
    padding: "9px 12px"
  query-input:
    backgroundColor: "transparent"
    textColor: "{colors.ink-green}"
  result-row:
    backgroundColor: "rgba(248, 250, 248, 0.52)"
    textColor: "{colors.ink-green}"
    padding: "15px 10px 15px 4px"
  result-row-selected:
    backgroundColor: "{colors.selection-wash}"
    textColor: "{colors.ink-green}"
  inspector-sheet:
    backgroundColor: "{colors.inspection-paper}"
    textColor: "{colors.ink-green}"
    rounded: "0"
    padding: "22px"
  identity-chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.pill}"
    padding: "5px 8px"
---

# Design System: GundHere

## Overview

**Creative North Star: "The Hobby-Shop Inspection Bench"**

GundHere should feel like a precise work surface where a hobbyist compares box labels, catalog identities, and evidence—not like a generic analytics dashboard. Cool gray-green surfaces form the bench; dense ruled rows form the candidate rack; a warm paper sheet holds the selected kit's evidence. Ink green supplies authority, while safety orange behaves like a physical selection mark.

The system is compact, factual, and tactile. It favors one continuous scan path from lookup to ranked candidates to inspection detail. Expressiveness comes from condensed inventory typography, square marks, fine rules, tabular scores, and restrained industrial color rather than decoration.

**Key Characteristics:**
- Cool measured work surfaces with a subtle 24px bench grid.
- Condensed inventory-label typography paired with highly legible system text.
- Safety orange reserved for action, focus, rejection, and active selection.
- Ruled rows and paper sheets that keep ranking evidence visually inspectable.
- Compact desktop density that collapses deliberately for narrow screens.

## Colors

The palette combines workshop neutrals and green-black ink with a single safety-orange interaction signal.

### Primary
- **Safety Orange** (`#e34b22`): The decisive action and selection color for the search control, visible focus, selected candidates, and rejection markers.
- **Deep Safety Orange** (`#a72d10`): The darker interactive state for hover and linked retailer emphasis.

### Secondary
- **Signal Green** (`#13724c`): Positive match-reason marks and credible success signals.
- **Caution Amber** (`#9b4b00`): Penalty and warning evidence without competing with the active orange.

### Neutral
- **Measured Work Surface** (`#e9edeb`): The full-page bench and foundation for the grid texture.
- **Inspection Paper** (`#f8faf8`): Search fields, active rows, empty states, and the evidence sheet.
- **Deep Paper** (`#dde4e0`): Loading bars and low-contrast tonal separation.
- **Ink Green** (`#10251f`): Primary text, masthead, hard rules, and authoritative geometry.
- **Soft Ink** (`#445a52`): Explanatory copy, metadata, and supporting labels.
- **Rule Line** (`#9eaca6`): Row separators and internal paper divisions.
- **Dark Rule Line** (`#536861`): Stronger boundaries, console seams, and outlined chips.
- **Selection Wash** (`#fff3ed`): A quiet warm field under the orange selected-state rule.

**The Safety-Mark Rule.** Orange must identify an action, focus target, active choice, or rejection; it is never a decorative fill.

**The Ink-on-Paper Rule.** Long-form and diagnostic text stays ink green on paper or the measured work surface; do not introduce pure black panels into the workspace.

## Typography

**Display Font:** Barlow Condensed (with Arial Narrow and sans-serif fallback)
**Body Font:** System UI (with Apple and Segoe UI fallbacks)

**Character:** Barlow Condensed gives kit names, headings, and the wordmark the economy of inventory labeling. The system face handles filters, explanations, evidence, and numeric metadata with native clarity.

### Hierarchy
- **Display** (700, fluid `clamp(2.35rem, 4.6vw, 4.9rem)`, 0.96 line-height): One primary proposition per lookup surface; keep the measure tight at roughly 14–18 characters.
- **Title** (600–750, 0.98–1.25rem, 1.25 line-height): Section headings, candidate names, and empty-state titles.
- **Body** (400, 1rem, 1.55 line-height): Guidance and explanatory copy, generally held to 46–58 characters per line.
- **Label** (700–800, 0.68–0.76rem, 0.06–0.08em tracking): Uppercase field labels, sort labels, sheet codes, and inspection headings.
- **Numeric Evidence** (760–850, tabular numerals): Rankings, confidence values, margins, and score stamps.

**The Two-Voice Rule.** Use the condensed face for identity and hierarchy; use the system face for operation and evidence. Do not add a third typographic voice.

## Layout

The page is a centered fluid workbench capped at 1480px with 4vw side padding. The lookup header begins as an asymmetric two-column composition, while the primary workspace uses a wide candidate rack and a narrower sticky evidence sheet. Spacing follows a compact 7–22px component rhythm and opens to 30–70px between page regions.

At 1180px the lookup stacks while preserving its strong bottom rule. At 900px the candidate rack and inspector become a single column and the inspector stops sticking. At 680px page gutters become 18px, filters form a two-column grid, the primary action spans full width, retrieval-path detail hides, and the completed-search state collapses introductory copy to keep results near the query.

**The One Scan Path Rule.** Place query, retrieval summary, ranked candidates, and selected evidence in reading order; never make users jump between disconnected dashboards.

## Elevation & Depth

The system is flat by default and uses rules, paper tone, and the background grid for structure. Only the search console and inspection sheet lift from the bench with one ambient shadow; selected rows remain flat and use an inset orange rule instead.

### Shadow Vocabulary
- **Lifted Paper** (`0 12px 30px rgba(16, 37, 31, 0.12)`): Search console and sticky inspection sheet only.

**The Paper-Lift Rule.** Elevation marks active work surfaces, not every container. Lists, summaries, and metadata remain ruled and flat.

## Shapes

The form language is predominantly square and mechanical. Console cells, result rows, buttons, and the inspection sheet keep hard corners. The 12px radius is reserved as a general panel token but is not applied to the core inspection geometry. Full pills identify compact metadata, while circles are reserved for status lights and the deliberately rotated score stamp. The wordmark uses a clipped square bracket shape as its signature.

**The Functional Curve Rule.** Curves communicate status, compact tags, or stamped scoring; they do not soften the main workbench structure.

## Components

### Buttons
- **Shape:** Square, compact, and weighty, with no default corner radius.
- **Primary:** Safety-orange fill, white text, and 14px by 20px padding; the search icon is a simple 20px line mark.
- **Hover / Focus:** Hover darkens to deep safety orange. Keyboard focus uses a 3px orange outline with a 3px offset. Disabled state becomes muted brick and retains readable pale text.
- **Outline:** Transparent paper-adjacent action with a 1px ink border and 9px by 12px padding.

### Chips
- **Style:** Transparent, pill-shaped identity labels with a 1px dark rule and 5px by 8px padding.
- **State:** Chips describe grade, scale, and relationship; they are informational rather than clickable.

### Cards / Containers
- **Corner Style:** Square for the search console and inspection sheet.
- **Background:** Inspection paper over the measured work surface.
- **Shadow Strategy:** Only active work surfaces use Lifted Paper.
- **Border:** Console cells are separated by 1px dark seams; the inspection sheet begins with a 5px ink-green top rule.
- **Internal Padding:** 18–22px for primary paper regions.

### Inputs / Fields
- **Style:** Search and select controls are borderless inside ruled paper cells. The query is condensed, large, and bold; filters retain the body face.
- **Focus:** The query removes its internal outline because the global 3px safety-orange focus indicator defines keyboard focus at the control boundary.
- **Error / Disabled:** Missing query returns focus to the query field. Busy state disables only the submit button and labels the active operation.

### Navigation
- **Style:** A compact 58px ink-green masthead carries a clipped orange mark, tracked condensed wordmark, product purpose, and live index status. Supporting purpose text disappears below 680px; the operational wordmark and status remain.

### Candidate Row
- **Style:** A full-width ruled button aligns rank, canonical identity, retrieval path, and tabular score in a scan-friendly grid.
- **Selected State:** Warm selection wash plus a 2px inset safety-orange rule; rejected candidates lower opacity but remain readable.
- **Motion:** Fresh results reveal left-to-right over 420ms with a 24ms row stagger. Reduced-motion preference collapses animation duration to effectively zero.

### Inspection Sheet
- **Style:** A sticky paper panel with a heavy top rule, stamped circular score, pill identity tags, structured signals, reason marks, and retailer rows.
- **Behavior:** It becomes static below 900px and follows the candidate list in reading order.

## Do's and Don'ts

### Do:
- **Do** keep the interface anchored in the cool measured work surface, inspection paper, and green-black ink palette.
- **Do** reserve safety orange for action, focus, selection, and rejection.
- **Do** use tabular numerals and aligned columns wherever ranking evidence is compared.
- **Do** preserve the 3px visible focus outline and reduced-motion behavior.
- **Do** collapse secondary detail before shrinking primary labels beyond legibility.

### Don't:
- **Don't** turn the product into a rounded-card dashboard or distribute shadows across every region.
- **Don't** use orange as ambient decoration or a large page background.
- **Don't** add speculative badges, thresholds, prices, availability, or confidence claims.
- **Don't** replace ruled rows with isolated tiles; the rack metaphor depends on continuous comparison.
- **Don't** add ornamental typefaces, gradients, or glossy effects that break the inspection-bench character.

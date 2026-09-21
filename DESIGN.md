# DESIGN.md — COMMAND LABS brand guidelines

Source: https://www.cmdlabs.io

---

## 1. Color

### Core palette (use these)

- Ink [#101828] (Dominant text color — 134 uses. Deep navy-black, NOT pure black.)
- Kalygo blue [#165dfc] (Blue for conveying maturity)
- Pure black [#000000] (Section backgrounds only (17 of 22 uses are bg). Band color.)
- Near black [#0A0A0A] (Mid-stop of the black band gradient.)
- White [#FFFFFF] (Dominant background — 2,073,600px max area. Also inverted text.)
- Off-white [#F9FAFB] (Subtle section wash, bottom stop of white gradient.)
- Body grey [#4A5565] (Body copy, subheads.)
- Body grey dark [#364153] (Slightly stronger body text.)
- Muted grey [#99A1AF] (Captions, eyebrow labels, de-emphasized meta.)
- Hairline [#E5E7EB] (Card borders, dividers.)
- Surface [#D1D5DC] (Interactive chip / control backgrounds.)
- Accent blue [#165dfc] (CTAs, eyebrow labels, service icons. The only saturated color.)
- Accent dark red [#C10007] (Darker red state.)
- Proof green [#007A55] (Stat numbers only.)

### Band gradients

```css
/* light band */ linear-gradient(#FFFFFF 0%, #F9FAFB 100%)
/* dark band  */ linear-gradient(#000000 0%, #0A0A0A 50%, #000000 100%)
```

---

## 2. Typography

Glacial Indifference. A geometric sans with humanist warmth — wide round bowls, low contrast, slightly quirky. Reads as approachable-technical rather than corporate.

### Real font files (only these weights exist)

| File                        | Weight | Style  |
| --------------------------- | ------ | ------ |
| `d7a39b20506f82c2-s.p.woff2` | 400    | normal |
| `ee9d4749cd679e38-s.p.woff2` | 700    | normal |
| `e67ae7565fb7bb16-s.p.woff2` | 400    | italic |

### Scale as measured on the live site (1920px viewport)

| Role      | Size | Weight | Line height | Color     |
| --------- | ---- | ------ | ----------- | --------- |
| display   | 60px | 700    | 60px (1.0)  | gradient  |
| heading   | 30px | 700    | 36px (1.2)  | `#101828` |
| heading-3 | 24px | 700    | 32px        | `#101828` |
| heading-3 | 20px | 700    | 28px        | `#101828` |
| body      | 24px | 400    | 32px        | `#4A5565` |
| link      | 14px | 500→400| 20px        | `#4A5565` |

Display line-height is 1.0 — headline lines stack tight, nearly touching. This is the site's strongest typographic signature and should carry into the video.

### Video scale

Site type is sized for reading at desk distance; keynote type is sized for a room. Scale the display role up hard (160–260px) while keeping line-height at 1.0 and weight at 700.

Body/subhead stays proportionally much smaller — the site's hierarchy is a ~2.5:1 display-to-body ratio; in the video push it to 4:1 or more.

## 3. Components

### Buttons — fully pill-shaped

`border-radius: 1.67772e+07px` (an absurd number that just means "fully round"). Every button on the site is a pill. No square or slightly-rounded buttons exist.

| Variant       | Background | Text      | Padding    | Height | Weight |
| ------------- | ---------- | --------- | ---------- | ------ | ------ |
| Primary dark  | `#101828`  | `#FFFFFF` | `8px 20px` | 36px   | 600*   |
| Primary blue  | `##165dfc` | `#FFFFFF` | pill       | ~40px  | 600*   |
| Secondary     | `#F3F4F6`  | `#101828` | pill       | 40px   | 400    |
| Outline       | transparent| `#101828` | pill       | —      | 400    |

\* Site requests 600; render at **700** in video since 600 isn't a real file.

### Cards

White, hairline border `#E5E7EB`, generous internal padding, very soft shadow: `0 1px 3px rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)`. Low elevation — the site is flat, not floaty. Case-study card is 848×321 at 1920 wide.

### Shadows — only three exist, all subtle

Max elevation is `0 10px 15px -3px rgba(0,0,0,0.1)`. There is one red-tinted shadow on the primary red CTA. Do not invent deep shadows.

---

## 4. Layout

- Spacing scale: 8px base — `8, 12, 16, 20, 24, 32, 40, 48, 96`. The jump from 48 to 96 is the
  section-level gap.
- Page: 1920 × 3712 across 6 sections; nav is 57px tall.
- Alternating band rhythm — the site's structural signature:
  `white hero → BLACK logo band → white newsletter → white services → white stats/case study → BLACK CTA`
  Black bands are used for social proof and the ask. This alternation is a ready-made
  keynote cutting pattern.
- Centering: almost everything is center-aligned. Only the case-study card body is left-aligned.
- Content is generously inset from 1920 edges — wide margins, lots of air.

---

## 5. Do / Don't

### Do

- Use `#101828`, not `#000000`, for text. Pure black is a background color here.
- Keep display line-height at 1.0. Tight-stacked headline lines are the brand's signature.
- Make stat numbers green `#007A55`. They are the proof, and proof is green.
- Use the alternating white↔black band rhythm for scene changes.
- Keep everything pill-shaped if it's interactive.
- Keep red glows at 0.05–0.12 alpha, bleeding from an edge, never a defined shape.
- Use only weights 400 and 700.
- Leave lots of negative space — the site is confident enough to be empty.

### Don't

- Don't use font-weight 500 or 600 — those files don't exist and render as faux-bold.
- Don't put metrics in red or CTAs in green — it inverts the brand's meaning.
- Don't add deep shadows, heavy bevels, or glassmorphism — `glass: []`, the site has none.
- Don't introduce a second typeface. One family, two weights, all hierarchy from size and weight.
- Don't use square corners on anything button-like.
- Don't oversaturate the red glow — above ~0.15 alpha it stops looking like this brand.
- Don't tint the neutrals warm. The greys are cool/blue-leaning (`#4A5565`, `#99A1AF`).
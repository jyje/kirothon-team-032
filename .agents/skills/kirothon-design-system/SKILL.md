---
name: kirothon-design-system
description: Use when building or styling any KIROTHON 2026 UI (timer, pages, slides, components) so it matches the Kirothon sticker look. Provides the design tokens and usage rules extracted from https://kirothon-timer.vercel.app/.
---

# KIROTHON 2026 Design System

Source of truth for colors, type, spacing, shape, and motion in this repo.

## Files

- `design-system/tokens.css`: CSS custom properties. Import or copy into any page.
- `design-system/DESIGN.md`: full rules, component specs, and motion notes.

Read `design-system/DESIGN.md` before writing UI. Use the tokens; do not hard-code new colors.

## Rules

1. Use the token names (`var(--color-kiro)`, `var(--font-hand)`), not raw hex.
2. Outlines are 3px ink (`#0b0b0b`). Shadows are hard offsets, not blur. The Kiro glow is the only soft shadow.
3. Buttons are pills (`--radius-pill`) with white fill, ink text, and a 4px bottom shadow. Primary buttons use purple.
4. Keep text readable: white or lavender on ink, ink on white.
5. Accent is Kiro purple (`--color-kiro`). Party colors (pink, cyan, yellow) are for end-of-event effects only.
6. Use Rubik for UI, Rubik Mono One for numbers (tabular), Permanent Marker for labels and speech.
7. Always wrap decorative animation in `@media (prefers-reduced-motion: reduce)` and disable it.

## Checklist before finishing UI work

- [ ] Only token variables for color, radius, shadow, and font.
- [ ] Focus ring visible (3px lilac outline).
- [ ] Reduced-motion fallback present.
- [ ] Layout holds at 16:10 and under 700px width.

# KIROTHON 2026 Design System

Extracted from https://kirothon-timer.vercel.app/ (`style.css?v=15`). Tokens: `tokens.css`.

## Feel
Sticker style. Black rounded frame, thick outlines, hard shadows, hand-written accents, a purple night sky with the Kiro ghost.

## Color
| Token | Hex | Use |
|---|---|---|
| ink | #0b0b0b | frame, outline, text on light |
| purple | #5038a0 | ground, primary button |
| purple-dark | #2f2266 | flash |
| kiro | #9046ff | accent, progress, warning |
| lilac | #b79be0 | labels, focus ring |
| lavender | #dcc6ee | page bg, hover, hint |
| white | #fff | text on dark, buttons |

Party colors (pink #ff5fd2, cyan #4de1ff, yellow #ffd23f) are for the end-of-event party only.

## Type
- Rubik 500/700: UI, buttons.
- Rubik Mono One: big numbers. Use tabular numerals.
- Permanent Marker: labels, speech bubble, quips.
- Time 18cqw, sub 4.4cqw, label 3.4cqw (spaced .12em). Buttons 13 to 17px.

## Shape
- Pill buttons (999px). Frame 48px (28px on mobile). Bubble 1.2em.
- Border 3px ink. Button shadow `0 4px 0 ink`; pressed moves down 3px.

## Components
- Button: white, ink text, 3px border, hard shadow. Hover lavender. Active pressed. Focus: 3px lilac outline, 2px offset.
- Primary button: purple, white text, 17px, min-width 120px. Hover #6247bf.
- Small (13px) and icon (46px circle) variants.
- Segmented control: ink pill, selected segment is white with ink text.
- Progress bar: 2cqw tall, track #2a2140, fill kiro.
- Speech bubble: white, Permanent Marker, rotated -2deg.
- Clock states: normal (white), warn (kiro purple), final (pulse), boo (shake), party (rainbow).

## Layout
- Fixed 16:10 stage, centered, bottom-aligned. Extra space becomes sky or ground.
- Controls bottom center; hide when idle while running.
- Inset 12px (6px under 700px).

## Motion
- Press .08s, hover .2s, show/hide .4s.
- Idle: breathe 6s, float 5s, twinkle 3s.
- Urgent: frame glow 1s. Time up: flash 1s x5.
- Party: lights, mirror ball, confetti, dance .9s.
- Always honor `prefers-reduced-motion` (disable all animation).

## Rules
- Keep outlines ink and shadows hard. No soft blur except the Kiro glow.
- Accent is kiro purple; do not add new hues outside party mode.
- Keep contrast: white or lavender text on ink; ink on white.

## Not verified
Kiro and star SVG art, and JS-driven states, were read from CSS only. I did not render the page.

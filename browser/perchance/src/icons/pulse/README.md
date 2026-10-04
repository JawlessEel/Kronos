# Pulse — Othala rune pack (Crypto Pulse)

Same Othala geometry as Utterly/DadChat, recoloured **violet→cyan** to match
the terminal (`--a:#7c5cff`, `--c:#22d3ee`, logo gradient `#a78bfa→#22d3ee`).

| token | dark | light |
| --- | --- | --- |
| stop A | `#A78BFA` | `#6D28D9` |
| stop B | `#22D3EE` | `#0E7490` |
| glow | `rgba(124,92,255,.45)` | same |
| app backing | `#070B14` | — |

Cool violet/cyan vs Utterly's warm amber/rose — tabs never get confused at 16px.

## Files

- `pulse-rune.svg` — theme-aware via `prefers-color-scheme`. Main asset.
- `pulse-rune-dark.svg` — fixed dark gradient (PNG/favicon source).
- `pulse-rune-light.svg` — fixed light gradient.
- `pulse-rune-currentColor.svg` — inherits CSS `color`.
- `pulse-rune-animated.svg` — loader, tune with `--pulse-glow`.
- `published/` — exact bytes wired into `index.html` links.
- `preview.html` — visual check.

## Crypto extras (no equivalent in Utterly)

- `pulseTab(price, chg)` in `index.html` redraws the tab favicon on a canvas:
  rune + green/red ring + ▲/▼, and writes `document.title` with live price.
- `theme-color` follows market mood (green/red).

## Hosted copies wired into index.html

- SVG: https://user.uploads.dev/file/498fdad3b22de2f6db4d8ab8933e682c.svg
- PNG 32: https://user.uploads.dev/file/6cd87c3271b20498705a544f891abac4.png
- Apple 180: https://user.uploads.dev/file/39e79e68a7cf92d1607b955d5b3b81dc.png
- Social 1200x630 ($meta.image + og:image): https://user.uploads.dev/file/60ba6e38614adb3f4fc1fdef5fced878.jpg

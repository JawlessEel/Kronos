# Othala rune — icon pack

The mark used by **DadChat** (`dad-chat`): an **Othala rune** — a diamond with a
transparent diamond hole through its middle and two legs that cross below it.
The shape is a faithful vector trace of the rune supplied by the project owner
(IoU ≈ 0.98 against the source art), drawn on a **96×96 viewBox**.

## Files

| File | What it is |
| --- | --- |
| `othala-rune.svg` | **Main asset.** Theme-aware: teal→indigo on dark, and it swaps to the light pair via `@media (prefers-color-scheme: light)`. 96×96 intrinsic size. |
| `othala-rune-currentColor.svg` | Single colour, `fill="currentColor"` — inherits CSS `color`. Best for inlining into buttons/badges. |
| `othala-rune-dark.svg` | Fixed dark-theme gradient (`#00E5C3` → `#5B6EF5`). |
| `othala-rune-light.svg` | Fixed light-theme gradient (`#00B89E` → `#4558E8`). |
| `othala-rune-animated.svg` | Loader mark: rise-and-settle entry, then a slow breathing `drop-shadow` glow. Tune with `--othala-glow`. |
| `png/othala-16…512.png` | Transparent PNGs (16, 32, 48, 64, 128, 256, 512), dark-theme gradient. |
| `png/othala-appicon-180.png` | App-icon style: solid `#0A0D14` square, rune inset ~19% with a soft teal glow. |
| `published/othala-favicon.svg`, `published/othala-32.png`, `published/othala-180.png` | The exact bytes DadChat currently ships for the favicon / apple-touch-icon. |
| `preview.html` | Open it in a browser to see every variant on dark and light backgrounds. |

## Geometry (canonical path)

```
M48 3 L83.48 38.16 L58.81 63.32 L67.52 71.87 L78.32 61.39 L88.32 71.87 L67.52 93
L48 73.97 L28.48 93 L7.68 71.87 L17.68 61.39 L28.48 71.87 L37.19 63.32 L12.52 38.16 Z
M48 23.97 L62.36 38.32 L48 52.68 L33.64 38.32 Z
```

Always draw it with `fill-rule="evenodd"` so the second subpath punches the hole.

## Colours

| Token | Dark | Light |
| --- | --- | --- |
| gradient stop A | `#00E5C3` | `#00B89E` |
| gradient stop B | `#5B6EF5` | `#4558E8` |
| glow | `rgba(0,229,195,0.35)` | `rgba(0,184,158,0.28)` |
| app-icon backing | `#0A0D14` | — |

Gradient direction is `x1="0.1" y1="0" x2="0.9" y2="1"` (top-left → bottom-right).

## Usage

Inline SVG (inherits your text colour):

```html
<svg viewBox="0 0 96 96" width="32" height="32" fill="none" style="color:#00E5C3">
  <path fill="currentColor" fill-rule="evenodd"
        d="M48 3 L83.48 38.16 L58.81 63.32 L67.52 71.87 L78.32 61.39 L88.32 71.87 L67.52 93 L48 73.97 L28.48 93 L7.68 71.87 L17.68 61.39 L28.48 71.87 L37.19 63.32 L12.52 38.16 Z M48 23.97 L62.36 38.32 L48 52.68 L33.64 38.32 Z"/>
</svg>
```

Favicon set:

```html
<link rel="icon" type="image/svg+xml" href="othala-rune.svg">
<link rel="icon" type="image/png" sizes="32x32" href="png/othala-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="png/othala-appicon-180.png">
```

The animated loader mark (0.62s rise-and-settle, then a 3.4s breathing glow):

```css
svg.rune { overflow: visible; }
.rune-mark {
  transform-origin: 48px 48px;
  animation: othalaRise .62s cubic-bezier(.34,1.56,.64,1) both,
             othalaGlow 3.4s ease-in-out .62s infinite;
}
@keyframes othalaRise { from { transform: translateY(-6px) scale(.72); }
                        to   { transform: translateY(0) scale(1); } }
@keyframes othalaGlow { 0%,100% { filter: drop-shadow(0 0 3px var(--othala-glow)); }
                        50%     { filter: drop-shadow(0 0 11px var(--othala-glow)); } }
```

The entry animates transform only (not opacity) so the mark is never invisible if
animations are frozen. If you also want the project's original fade-in, add
`opacity: 0` → `1` to the `othalaRise` keyframes — safe when the SVG is inlined.

## Hosted copies (DadChat's live URLs)

- favicon SVG: https://user.uploads.dev/file/e47701fec9afb2d8caca8b8695047303.svg
- favicon PNG 32×32: https://user.uploads.dev/file/d672022a803029b9058fe257b450952f.png
- apple-touch 180×180: https://user.uploads.dev/file/9236f3c679c188fd4e2ee77a3afda325.png

Same URLs are wired into `dad-chat`'s `index.html` `<link>` tags, its
`src/manifest.json` `icons[]`, and `main.pjs` `$meta`.

---

## Sibling mark — UTTERLY

**Utterly** (this generator) uses the *same* Othala geometry in a **different
hue**, so a tab running Utterly is never mistaken for a tab running DadChat:
cool teal→indigo for Dad, warm **amber→rose** (`#FFC24B` → `#FF3D7F`) for Utterly.

Everything lives in **`utterly/`** — see `utterly/README.md` for the full token
table and the PNG rebuild recipe. The two marks share the canonical path, so any
geometry fix must be applied to both packs.

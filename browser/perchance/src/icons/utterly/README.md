# Utterly — Othala rune pack

**Utterly's** mark: the same **Othala rune** geometry as DadChat — a diamond with a
transparent diamond hole and two legs crossing below — recoloured so the two
generators are never confused in a browser tab.

| | DadChat | **Utterly** |
| --- | --- | --- |
| stop A (dark) | `#00E5C3` teal | **`#FFC24B` amber** |
| stop B (dark) | `#5B6EF5` indigo | **`#FF3D7F` rose** |
| stop A (light) | `#00B89E` | **`#D99500`** |
| stop B (light) | `#4558E8` | **`#D62066`** |
| glow (dark) | `rgba(0,229,195,.35)` | **`rgba(255,194,75,.38)`** |
| app-icon backing | `#0A0D14` | **`#140D12`** |

Cool cyan/blue vs warm amber/rose — the difference survives being shrunk to a
16 px favicon, which is the whole point.

## Files

| File | What it is |
| --- | --- |
| `utterly-rune.svg` | **Main asset.** Theme-aware: amber→rose on dark, darkened pair on light via `@media (prefers-color-scheme: light)`. 96×96 viewBox. |
| `utterly-rune-currentColor.svg` | Single colour, `fill="currentColor"` — inherits CSS `color`. Best for inlining into buttons/badges. |
| `utterly-rune-dark.svg` | Fixed dark-theme gradient. |
| `utterly-rune-light.svg` | Fixed light-theme gradient. |
| `utterly-rune-animated.svg` | Loader mark: rise-and-settle entry, then a slow breathing `drop-shadow`. Tune with `--utterly-glow`. |
| `png/utterly-16…512.png` | Transparent PNGs, dark-theme gradient. |
| `png/utterly-appicon-180.png` | App-icon style: solid `#140D12` square, rune inset ~19%, warm glow. |
| `published/utterly-favicon.svg`, `published/utterly-32.png`, `published/utterly-180.png` | The exact bytes wired into `index.html`'s `<link>` tags. |
| `preview.html` | Open in a browser to see every variant on dark and light backgrounds. |

## Geometry (canonical path — identical to DadChat's)

```
M48 3 L83.48 38.16 L58.81 63.32 L67.52 71.87 L78.32 61.39 L88.32 71.87 L67.52 93
L48 73.97 L28.48 93 L7.68 71.87 L17.68 61.39 L28.48 71.87 L37.19 63.32 L12.52 38.16 Z
M48 23.97 L62.36 38.32 L48 52.68 L33.64 38.32 Z
```

Always draw it with `fill-rule="evenodd"` so the second subpath punches the hole.
Gradient direction is `x1="0.1" y1="0" x2="0.9" y2="1"` (top-left → bottom-right).

## Rebuilding the PNGs

The PNGs are rasterised from `utterly-rune-dark.svg` in a browser (SVG cannot be
rasterised in a worker — `createImageBitmap(svgBlob)` throws "source image could
not be decoded"). Reproduce with, in `page_eval`:

```js
const img = new Image();
img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(SVG_TEXT);
await img.decode();
const c = document.createElement("canvas"); c.width = c.height = 512;
c.getContext("2d").drawImage(img, 0, 0, 512, 512);
c.toBlob((b) => { /* b is the transparent PNG */ }, "image/png");
```

For the app-icon variants, fill the canvas with `#140D12` first and draw the rune
inset (62 % of the canvas for `appicon-180`, 76 % for `published/180`) with
`ctx.shadowColor = "rgba(255,194,75,0.55)"` / `ctx.shadowBlur = size * 0.11`.

## Usage

Inline SVG (inherits your text colour):

```html
<svg viewBox="0 0 96 96" width="24" height="24" fill="none" style="color:#FFC24B">
  <path fill="currentColor" fill-rule="evenodd"
        d="M48 3 L83.48 38.16 L58.81 63.32 L67.52 71.87 L78.32 61.39 L88.32 71.87 L67.52 93 L48 73.97 L28.48 93 L7.68 71.87 L17.68 61.39 L28.48 71.87 L37.19 63.32 L12.52 38.16 Z M48 23.97 L62.36 38.32 L48 52.68 L33.64 38.32 Z"/>
</svg>
```

Favicon set (Utterly uses hosted copies so the links work before `src/` is saved):

```html
<link rel="icon" type="image/svg+xml" href="…/utterly-favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="…/utterly-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="…/utterly-180.png">
```

## Hosted copies (the URLs actually wired into the generator)

- favicon SVG: https://user.uploads.dev/file/9352e2125fe715034dc9d041966dcbbf.svg
- favicon PNG 32×32: https://user.uploads.dev/file/5e940fb9e7edfaa3a700feec7d00d49d.png
- apple-touch 180×180: https://user.uploads.dev/file/270a55cd6aebb3dcc6d97985757de278.png
- share card 1200×630 (also `main.pjs` `$meta.image`):
  https://user.uploads.dev/file/c15d94652129e9b04ba1d88d8fd4f5b6.jpg

Same URLs appear in `index.html`'s `<link>` tags and share meta, and in
`main.pjs` `$meta.image`. If you re-render the art, re-upload and update all three
places together.

## In-page usage

`index.html` declares the rune **once** as `<symbol id="runeSym">` inside a 0×0
`<svg class="rune-defs">` (0×0, never `display:none`, or `<use>` gradients stop
resolving), then references it everywhere:

```html
<svg class="rune" viewBox="0 0 96 96"><use href="#runeSym"></use></svg>
```

The `--rune-a`, `--rune-b` and `--rune-glow` custom properties live in `:root`. The
breathing-glow animation (`.rune-live .rune-mark`) is skipped under
`prefers-reduced-motion`.

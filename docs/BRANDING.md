# Vyom branding

Owner-approved on 4 October 2026: the supplied blue telescope, helm and clouds illustration is Vyom's canonical logo. Use it for the README, application branding, diagrams, documents and the future website. This selects the brand asset; it does not schedule or build the website.

![Vyom logo](../assets/branding/vyom-logo.png)

## Canonical asset

[assets/branding/vyom-logo.png](../assets/branding/vyom-logo.png) is the original supplied PNG, preserved byte for byte. It is 481 × 461 pixels and has an opaque light background. Keep this file as the source for future deliverables.

- Reuse the supplied artwork; do not substitute a generated logo, emoji or unrelated mark.
- Preserve its aspect ratio and the entire illustration. Set one display dimension and let the other scale naturally; avoid stretching, cropping, recoloring or upscaling beyond the source resolution.
- Keep its existing light background. On dark surfaces, use a light logo area; do not claim this asset is transparent.
- Pair it with the name **Vyom**. Use `alt="Vyom logo"` when the image conveys the brand; use empty alt text only when an adjacent label already provides equivalent accessible text.
- For the future app/site, import or copy the canonical asset through the chosen build workflow. Create favicon/social/transparent variants only when that surface needs them; retain the original source and verify derived variants remain recognizable.

## Circular mark for the dark console

Owner-supplied on 12 October 2026 with the [frontend design spec](design/DESIGN.md): [design/vyom-logo.png](design/vyom-logo.png), a 256 × 256 circular crop of the same artwork on a transparent background. The application uses it in the sidebar and as the favicon (`frontend/src/assets/vyom-mark.png`, the same bytes), at 40–44px with the spec's faint blue halo. It is a variant for dark surfaces, not a replacement: the canonical PNG above stays the source for the README, documents and diagrams.

README uses a 128px display width. The standalone architecture SVG embeds the same PNG bytes so the diagram remains portable. Refresh that embedded copy if the owner replaces the canonical asset. Other existing diagram drafts retain their current output until their next regeneration; use this logo in newly created or refreshed brand headers.

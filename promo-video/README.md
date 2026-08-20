# DeepResearch promo video

30-second, 1920×1080, 30 fps product promo built from deterministic Remotion
scenes and network-isolated captures of the real frontend components.

## Deliverables

- `out/deepresearch-promo-bgm.mp4`
- `out/deepresearch-promo-no-bgm.mp4` (designed SFX retained)

Both outputs share the same H.264 video stream. The fixtures and report data
are fictional Orion-7 examples; no backend, production account, or external
service is used during capture.

## Rebuild

```bash
npm ci
npm run typecheck
npm run capture
npm run render:deliverables
```

`npm run capture` imports the current frontend components and theme, serves the
official `frontend/public/research-mark.svg`, and uses only fictional Orion-7
fixtures. It captures into a unique staging directory, validates every page,
selector, crop, PNG dimension, data marker, and source fingerprint, then swaps
the complete texture set and `src/live-layout.json` into place. A failed capture
leaves the previously published textures untouched. Browser traffic is limited
to the loopback Vite harness plus an in-process `/api/models` fixture.

Set `REMOTION_BROWSER_EXECUTABLE` to a local Chromium/Chrome binary when one is
already installed. Otherwise Remotion downloads its supported headless shell.
Audio sources and license URLs are listed in `public/audio/ATTRIBUTION.md`.

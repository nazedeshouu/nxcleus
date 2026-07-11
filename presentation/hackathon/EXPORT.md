# Export — Nxcleus AMD deck

Run from `presentation/hackathon/`. Requires Google Chrome (headless) and, for the
review step, `pdftoppm` (poppler: `brew install poppler`).

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 1. Deck -> PDF  (1280x720 slides, backgrounds preserved, fonts embedded)
"$CHROME" --headless --disable-gpu --no-pdf-header-footer --no-margins \
  --print-to-pdf="nxcleus-amd-deck.pdf" "file://$(pwd)/deck.html"

# 2. Cover -> PNG  (2560x1440, i.e. 16:9 at 2x)
"$CHROME" --headless --disable-gpu --hide-scrollbars \
  --window-size=1280,720 --force-device-scale-factor=2 \
  --screenshot="cover.png" "file://$(pwd)/cover.html"
```

Verify (optional):

```sh
pdffonts nxcleus-amd-deck.pdf                       # every Lenia/Arcel row: emb=yes sub=yes
pdftoppm -png -r 90 nxcleus-amd-deck.pdf /tmp/slide # eyeball /tmp/slide-*.png
```

## Files
- `deck.html` — 10 slides, one commented `<section>` each. Design tokens are CSS
  variables in `:root` at the top (accent color, type scale, spacing). Retune there.
- `cover.html` — standalone 16:9 gallery cover (mirrors the title slide).
- `assets/` — colored `bg-*.png` backgrounds (light slides: bg-light*; dark: bg-wall3
  cover / bg-dark AMD / bg-planes close), `qr.svg` (nxcleus.tech). `cover-hero.png` /
  `close-hero.png` are unused (superseded monochrome art).
- Screenshots pulled live from `../../frontend/screenshots/`.

## Notes
- Art direction: single cyan accent (`--accent` #1c7aa3 / `--accent-dk` #38a6d2 on dark)
  over the colored blueprint/glass backgrounds. Keep it single-accent; cyan only.
- The AMD architecture slide (05) is the mandatory "use of AMD" gate. Keep MI300X,
  ROCm, vLLM, and the Fireworks AMD-hosted line visible.
- Chrome's `--print-to-pdf` prints backgrounds by default; no extra flag needed.

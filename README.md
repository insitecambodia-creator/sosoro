# SOSORO book reproduction — Stage 1: photo restoration

Turns a raw photo of an open two-page book spread into two clean,
print-ready single-page images: rotated upright, split at the spine,
perspective/skew corrected, cropped to the page, color- and
contrast-corrected, and resized to a consistent page size for the whole
book.

Stage 2 (OCR to text/Word) is not built yet — see "Next: Stage 2" below.

## Setup

```bash
# System dependency (for reliable auto-rotation detection):
sudo apt-get install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-osd
# (macOS: brew install tesseract tesseract-lang)

pip install -r scripts/requirements.txt
```

The tool still works without Tesseract installed (it falls back to a
simpler rotation heuristic), but installing it makes upright/upside-down
detection much more reliable.

## Usage

```bash
# Process one or more spread photos into output/
python3 scripts/restore_pages.py IMG_4274.jpg IMG_4275.jpg -o output/

# Whole folder of scans, glob-style
python3 scripts/restore_pages.py "scans/*.jpg" -o output/

# Quick check of just the rotate+flatten step, before committing to a full run
python3 scripts/restore_pages.py IMG_4274.jpg -o output/ --preview-only
```

Each `IMG_xxxx.jpg` spread produces two files: `IMG_xxxx_pa.tif` (left
page) and `IMG_xxxx_pb.tif` (right page), full color, ready to lay out
for print.

### Useful options

| Flag | Default | What it does |
|---|---|---|
| `--rotate {0,90,180,270}` | auto-detect | Force a rotation instead of detecting it. Handy if your whole batch was shot the same way. |
| `--dpi` | 400 | Output resolution. |
| `--page-width-in` / `--page-height-in` | 6.0 / 9.25 | Target single-page size — set this to the book's actual trim size for accurate print dimensions. |
| `--gutter-trim-pct` | 2.5 | How much to trim off the spine-facing edge of each split page, to remove the spine shadow. Raise it if shadow remains; lower it if it's eating into text. |
| `--bw` | off | Convert to grayscale (for a plain text reproduction rather than a photographic-fidelity copy). |
| `--no-split` | off | Treat each input image as a single page instead of a two-page spread. |

Run `python3 scripts/restore_pages.py --help` for the full list.

## What the pipeline does

1. **Rotate upright** — auto-detected (Tesseract OSD if available).
2. **Flatten perspective** — finds the photographed page/spread against
   its background and perspective-corrects it to a flat rectangle.
3. **Split at the spine** — locates the gutter shadow (robust to normal
   lighting vignette) and cuts the spread into two pages.
4. **Crop to the page** — removes background/table visible around the
   edges, then trims the spine-shadow edge.
5. **Deskew** — corrects the page's overall rotation using a
   projection-profile analysis of the text.
6. **Colorimetry** — flattens uneven lighting (e.g. shadow falling across
   the page), neutralizes the paper's color cast to a clean white, and
   stretches contrast — while keeping it a photographic color image, not
   a pure black/white scan.
7. **Normalize size** — every output page is resized onto the same
   canvas at the chosen DPI, so the whole book comes out consistent.

## Known limitations (v1)

- A defect confined to just one corner (e.g. a curled page tip exposing
  a sliver of table) can't be fully removed by a rectangular crop
  without also cutting real content along that edge — usually a very
  minor, cosmetic residual.
- Pages with heavy physical curling/bowing (not just camera-angle
  rotation) may keep a small amount of visible curve — a single rotation
  angle can straighten overall tilt but not a genuine bow in the paper.
  For best results, flatten the book as much as possible when
  photographing (a book weight/glass pane helps a lot).
- Photograph each spread with consistent, even lighting and the book
  as flat as the binding allows — this matters more than anything the
  software can fix afterward.

## Next: Stage 2 (OCR → text/Word)

Once you're happy with the photo restoration quality across the book,
the next stage is OCR (Tesseract, French-language data already
installed via `tesseract-ocr-fra`) to produce a searchable `.txt`/`.docx`
version. That's a separate script to build once stage 1 output is
finalized — happy to build it next.

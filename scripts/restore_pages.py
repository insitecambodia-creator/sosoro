#!/usr/bin/env python3
"""
restore_pages.py — Stage 1 of the SOSORO book reproduction pipeline.

Takes a raw photo of an open two-page book spread (as photographed from
direct scans) and produces two clean, print-ready single-page images:

  1. Auto-rotate the photo to an upright, readable orientation.
  2. Find the spread against its background and split it into a left and
     right page at the spine (gutter).
  3. Correct perspective/keystone distortion and deskew each page so text
     lines run straight and horizontal.
  4. Crop tightly to the page edges.
  5. Fix colorimetry: flatten uneven lighting (shadow near the spine),
     white-balance the paper to neutral, and stretch contrast — without
     crushing the image to pure black & white, so it still reads as a
     faithful photographic reproduction.
  6. Normalize every output page to the same pixel size / DPI so the whole
     book comes out as a consistent print-ready set.

Usage:
    python3 restore_pages.py IMG_4274.jpg IMG_4275.jpg -o output/
    python3 restore_pages.py scans/*.jpg -o output/ --rotate 90
    python3 restore_pages.py IMG_4274.jpg -o output/ --preview-only

Run with --help for all options.
"""
import argparse
import glob
import os
import sys
from dataclasses import dataclass

import cv2
import numpy as np

try:
    import pytesseract
    HAVE_TESSERACT = True
except ImportError:
    HAVE_TESSERACT = False


# --------------------------------------------------------------------------
# 1. Rotation
# --------------------------------------------------------------------------

def _projection_variance_score(gray: np.ndarray) -> float:
    """Higher score = more likely text runs horizontally (rows = lines)."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    row_sums = bw.sum(axis=1).astype(np.float64)
    return float(row_sums.var())


def detect_rotation(img: np.ndarray) -> int:
    """Return the rotation (degrees, clockwise) needed to make the page upright.

    Prefers Tesseract's orientation-and-script-detection (OSD), which reads
    actual letterforms and reliably tells right-side-up from upside-down.
    Falls back to a text-projection heuristic (which can find the 0/90 axis
    but not which of the two 180-apart candidates is upright) if Tesseract
    isn't available.
    """
    if HAVE_TESSERACT:
        try:
            osd = pytesseract.image_to_osd(img)
            for line in osd.splitlines():
                if line.startswith("Rotate:"):
                    return int(line.split(":")[1].strip())
        except Exception:
            pass  # fall through to heuristic

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, None, fx=0.25, fy=0.25)
    best_angle, best_score = 0, -1.0
    for angle in (0, 90, 180, 270):
        rotated = np.rot90(small, k=-angle // 90)
        score = _projection_variance_score(rotated)
        if score > best_score:
            best_angle, best_score = angle, score
    return best_angle


def rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    if angle % 360 == 0:
        return img
    k = (angle // 90) % 4
    return np.rot90(img, k=-k).copy()


# --------------------------------------------------------------------------
# 2. Locate the spread against its background, split into 2 pages
# --------------------------------------------------------------------------

def find_spread_quad(img: np.ndarray) -> np.ndarray | None:
    """Find the 4-corner quadrilateral of the paper against the background."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Paper is usually the brighter region; make sure foreground==paper.
    if bw.mean() < 127:
        bw = cv2.bitwise_not(bw)

    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.2 * img.shape[0] * img.shape[1]:
        return None  # didn't find a plausible page region

    rect = cv2.minAreaRect(c)
    box = cv2.boxPoints(rect)
    return box.astype(np.float32)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def warp_to_rect(img: np.ndarray, quad: np.ndarray, pad: int = 0) -> np.ndarray:
    """Perspective-correct the quad region of img to a flat rectangle."""
    tl, tr, br, bl = order_corners(quad)
    w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    w, h = max(w, 1), max(h, 1)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
    warped = cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
    if pad:
        warped = warped[pad:-pad or None, pad:-pad or None]
    return warped


def find_gutter_split(img: np.ndarray) -> int:
    """Find the column index of the spine/gutter shadow near the horizontal
    center of a flattened two-page spread, to split it into 2 pages.

    Overall page lighting is rarely flat (photos tend to have a left-right
    brightness gradient/vignette that is much larger than the local spine
    shadow), so we detrend the column-brightness profile with a wide
    Gaussian blur first and look for the darkest *local dip* relative to
    that trend, restricted to a band around the horizontal center.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    band = gray[int(h * 0.1):int(h * 0.9), :]
    col_brightness = band.mean(axis=0).astype(np.float64)

    k = (w // 10) | 1  # wide odd kernel to capture the lighting trend only
    baseline = cv2.GaussianBlur(col_brightness.reshape(1, -1), (k, 1), 0).flatten()
    detrended = col_brightness - baseline

    lo, hi = int(w * 0.35), int(w * 0.65)
    search = detrended[lo:hi]
    gutter = lo + int(np.argmin(search))
    return gutter


# --------------------------------------------------------------------------
# 3. Per-page: crop to content, deskew
# --------------------------------------------------------------------------

def crop_to_content(img: np.ndarray, margin_frac: float = 0.01) -> np.ndarray:
    """Crop to the bounding box of the largest bright (paper) region.

    Note: a rectangular crop can only remove a background border that runs
    the full width/height of an edge — a defect confined to one corner
    (e.g. a curled page tip exposing a sliver of table) can't be excluded
    without also cutting real content along that same row/column. That's
    an acceptable, minor v1 limitation; `--gutter-trim-pct` (applied
    before this) handles the one edge defect that *is* systematic: the
    spine shadow.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    k = (h // 60) | 1
    blur = cv2.GaussianBlur(gray, (k, k), 0)
    # No brightness-fraction flip here: paper is always the brighter class
    # (ink and any residual background are darker), unlike find_spread_quad
    # where a dark background can occupy the majority of the frame. Using
    # an area-fraction heuristic here previously flipped polarity on
    # text-dense pages, keeping the ink and discarding half the page.
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img
    c = max(contours, key=cv2.contourArea)
    x, y, cw, ch = cv2.boundingRect(c)
    mx, my = int(cw * margin_frac), int(ch * margin_frac)
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(w, x + cw + mx), min(h, y + ch + my)
    return img[y0:y1, x0:x1]


def trim_edge(img: np.ndarray, side: str, frac: float) -> np.ndarray:
    """Cut a fixed fraction of width/height off one edge (e.g. to remove a
    spine shadow along the gutter-facing edge of a split page)."""
    if frac <= 0:
        return img
    h, w = img.shape[:2]
    if side == "left":
        return img[:, int(w * frac):]
    if side == "right":
        return img[:, :w - int(w * frac)]
    if side == "top":
        return img[int(h * frac):, :]
    if side == "bottom":
        return img[:h - int(h * frac), :]
    raise ValueError(side)


def _projection_score(bw: np.ndarray, angle: float) -> float:
    h, w = bw.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(bw, M, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    row_sums = rotated.sum(axis=1).astype(np.float64)
    return float(row_sums.var())


def _estimate_skew_angle(gray: np.ndarray, search_deg: float = 8.0) -> float:
    """Find the rotation that best aligns text into horizontal lines.

    Classic projection-profile deskew: at the correct angle, each text
    line's ink lands in a narrow band of rows, so the row-sum profile has
    sharp peaks (paragraph text) and troughs (line gaps) — i.e. maximum
    variance. Any residual tilt smears ink across more rows and flattens
    that profile. This is coarse-to-fine: a wide 0.5-degree sweep finds
    the right neighborhood, then a narrow 0.05-degree sweep refines it.

    Line-by-line techniques (fitting individual detected text lines) were
    tried first but proved unreliable here — italic running headers and
    ink-density noise threw off per-line angle estimates. Measuring the
    whole page's projection profile at once sidesteps that.
    """
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    best_angle, best_score = 0.0, -1.0
    for i in range(int(-search_deg / 0.5), int(search_deg / 0.5) + 1):
        angle = i * 0.5
        score = _projection_score(bw, angle)
        if score > best_score:
            best_angle, best_score = angle, score

    for i in range(-9, 10):
        angle = best_angle + i * 0.05
        score = _projection_score(bw, angle)
        if score > best_score:
            best_angle, best_score = angle, score

    return best_angle


def _estimate_row_dependent_angle(gray: np.ndarray, nbands: int = 6) -> tuple[float, float]:
    """Estimate text-line tilt as a function of vertical page position:
    angle(y) = m*y + k.

    A single global angle assumes every line needs the same correction,
    but that's often not true on a photographed page — e.g. a page
    propped at a slight angle to the camera produces a genuine
    perspective shear where lines near the top of the frame need a
    different correction than lines near the bottom. Measuring baseline
    position pixel-by-pixel to detect this directly turned out to be too
    noisy (ascenders/descenders swing a single column's ink centroid by
    dozens of pixels). Instead, this reuses the robust whole-page
    projection-profile method (`_estimate_skew_angle`), just run
    independently on horizontal bands of the page — still an aggregate,
    noise-resistant measurement, but now localized enough to reveal how
    the tilt changes with row position. Falls back to a flat line (pure
    global rotation, m=0) if there isn't enough text to split into bands
    reliably.
    """
    h, w = gray.shape
    band_h = h // nbands
    centers, angles = [], []
    for i in range(nbands):
        y0, y1 = i * band_h, min(h, (i + 1) * band_h)
        band = gray[y0:y1, :]
        _, bw = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if (bw > 0).mean() < 0.01:
            continue  # near-blank band — not enough text to measure
        centers.append((y0 + y1) / 2)
        angles.append(_estimate_skew_angle(band))

    if len(centers) < 4:
        return 0.0, _estimate_skew_angle(gray)

    centers_arr, angles_arr = np.array(centers), np.array(angles)
    A = np.vstack([centers_arr, np.ones(len(centers_arr))]).T
    m, k = np.linalg.lstsq(A, angles_arr, rcond=None)[0]
    return float(m), float(k)


def deskew(img: np.ndarray) -> np.ndarray:
    """Straighten the page using a (possibly row-position-dependent)
    text-line angle (see `_estimate_row_dependent_angle`)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    m, k = _estimate_row_dependent_angle(gray)

    cx = w / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    angle_per_row = m * yy + k
    ratio_per_row = np.tan(np.radians(angle_per_row)).astype(np.float32)
    map_y = yy + ratio_per_row * (xx - np.float32(cx))
    return cv2.remap(img, xx, map_y, interpolation=cv2.INTER_CUBIC,
                      borderMode=cv2.BORDER_REPLICATE)


# --------------------------------------------------------------------------
# 4. Colorimetry
# --------------------------------------------------------------------------

def flatten_illumination(img: np.ndarray, blur_frac: float = 0.15) -> np.ndarray:
    """Remove uneven lighting / shadow gradients (e.g. darker near the
    spine) by dividing out a heavily-blurred estimate of the background."""
    h, w = img.shape[:2]
    k = int(max(h, w) * blur_frac) | 1  # force odd
    img_f = img.astype(np.float32)
    background = cv2.GaussianBlur(img_f, (k, k), 0)
    background = np.clip(background, 1, 255)
    corrected = img_f / background * 255.0
    return np.clip(corrected, 0, 255).astype(np.uint8)


def white_balance_paper(img: np.ndarray, percentile: float = 90.0) -> np.ndarray:
    """Neutralize the paper's color cast using the brightest percentile of
    pixels (assumed to be paper, not ink) as the white reference."""
    img_f = img.astype(np.float32)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = np.percentile(gray, percentile)
    mask = gray >= thresh
    if mask.sum() < 100:
        return img
    ref = img_f[mask].mean(axis=0)  # BGR
    ref = np.clip(ref, 1, None)
    gain = ref.max() / ref
    balanced = img_f * gain
    return np.clip(balanced, 0, 255).astype(np.uint8)


def stretch_contrast(img: np.ndarray, black_pct: float = 0.5, white_pct: float = 99.5,
                      gamma: float = 1.0) -> np.ndarray:
    """Per-channel percentile-based levels stretch (like Photoshop Auto Levels)."""
    out = np.empty_like(img)
    for c in range(3):
        chan = img[:, :, c].astype(np.float32)
        lo, hi = np.percentile(chan, [black_pct, white_pct])
        if hi <= lo:
            hi = lo + 1
        stretched = (chan - lo) / (hi - lo)
        stretched = np.clip(stretched, 0, 1)
        if gamma != 1.0:
            stretched = stretched ** (1.0 / gamma)
        out[:, :, c] = np.clip(stretched * 255, 0, 255).astype(np.uint8)
    return out


def sharpen(img: np.ndarray, amount: float = 0.6) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 2.0)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def correct_colorimetry(img: np.ndarray) -> np.ndarray:
    img = flatten_illumination(img)
    img = white_balance_paper(img)
    img = stretch_contrast(img)
    img = sharpen(img)
    return img


# --------------------------------------------------------------------------
# 5. Normalize size
# --------------------------------------------------------------------------

def normalize_size(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Fit the page onto a fixed canvas (letterboxing if aspect ratio
    doesn't exactly match) so every page in the book is the same size."""
    h, w = img.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return canvas


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

@dataclass
class Options:
    rotate: int | None
    dpi: int
    page_width_in: float
    page_height_in: float
    bw: bool
    no_split: bool
    preview_only: bool
    gutter_trim_pct: float = 2.5


def process_page(page_img: np.ndarray, opts: Options, gutter_side: str | None) -> np.ndarray:
    if gutter_side:
        page_img = trim_edge(page_img, gutter_side, opts.gutter_trim_pct / 100.0)
    page_img = crop_to_content(page_img)
    page_img = deskew(page_img)
    page_img = crop_to_content(page_img)
    page_img = correct_colorimetry(page_img)
    if opts.bw:
        gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
        page_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    target_w = int(opts.page_width_in * opts.dpi)
    target_h = int(opts.page_height_in * opts.dpi)
    return normalize_size(page_img, target_w, target_h)


def process_spread(path: str, out_dir: str, opts: Options) -> list[str]:
    img = cv2.imread(path)
    if img is None:
        raise IOError(f"Could not read image: {path}")

    angle = opts.rotate if opts.rotate is not None else detect_rotation(img)
    img = rotate_image(img, angle)

    quad = find_spread_quad(img)
    flat = warp_to_rect(img, quad) if quad is not None else img

    base = os.path.splitext(os.path.basename(path))[0]
    outputs = []

    if opts.preview_only:
        prev_path = os.path.join(out_dir, f"{base}_preview_rotated.jpg")
        cv2.imwrite(prev_path, flat, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return [prev_path]

    if opts.no_split:
        pages = [(flat, None)]
    else:
        gutter = find_gutter_split(flat)
        left = flat[:, :gutter]
        right = flat[:, gutter:]
        # Each page's gutter-facing (spine) edge: right edge of the left
        # page, left edge of the right page.
        pages = [(left, "right"), (right, "left")]

    suffixes = ["a", "b"] if len(pages) > 1 else [""]
    for (page_img, gutter_side), suf in zip(pages, suffixes):
        processed = process_page(page_img, opts, gutter_side)
        name = f"{base}_p{suf}.tif" if suf else f"{base}.tif"
        out_path = os.path.join(out_dir, name)
        cv2.imwrite(out_path, processed)
        outputs.append(out_path)

    return outputs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", help="Input spread photo(s); globs OK")
    ap.add_argument("-o", "--out-dir", default="output", help="Output directory")
    ap.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=None,
                     help="Force rotation instead of auto-detecting (degrees CW)")
    ap.add_argument("--dpi", type=int, default=400, help="Output resolution")
    ap.add_argument("--page-width-in", type=float, default=6.0,
                     help="Target single-page width in inches")
    ap.add_argument("--page-height-in", type=float, default=9.25,
                     help="Target single-page height in inches")
    ap.add_argument("--bw", action="store_true",
                     help="Convert to grayscale (for text-only reproduction)")
    ap.add_argument("--no-split", action="store_true",
                     help="Don't split spreads into 2 pages (process as one image)")
    ap.add_argument("--preview-only", action="store_true",
                     help="Only auto-rotate and flatten; skip split/crop/color for a quick check")
    ap.add_argument("--gutter-trim-pct", type=float, default=2.5,
                     help="Percent of page width to trim off the spine-facing edge of each "
                          "split page, to remove the gutter shadow (default 2.5)")
    args = ap.parse_args()

    paths = []
    for pattern in args.images:
        matches = sorted(glob.glob(pattern))
        paths.extend(matches if matches else [pattern])

    os.makedirs(args.out_dir, exist_ok=True)
    opts = Options(rotate=args.rotate, dpi=args.dpi,
                   page_width_in=args.page_width_in, page_height_in=args.page_height_in,
                   bw=args.bw, no_split=args.no_split, preview_only=args.preview_only,
                   gutter_trim_pct=args.gutter_trim_pct)

    if not HAVE_TESSERACT:
        print("Note: pytesseract not found; using fallback rotation heuristic "
              "(install `tesseract-ocr` + `pip install pytesseract` for more reliable "
              "auto-rotation).", file=sys.stderr)

    for path in paths:
        try:
            outputs = process_spread(path, args.out_dir, opts)
            print(f"{path} -> {', '.join(outputs)}")
        except Exception as e:
            print(f"FAILED: {path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

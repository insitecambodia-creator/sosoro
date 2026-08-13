#!/usr/bin/env python3
"""
build_pdf.py — Stage 1 (final step): assemble processed page images
(from restore_pages.py) into a single print-ready PDF, in book order, at
their true physical page size.

Usage:
    python3 build_pdf.py "output/*.tif" -o book.pdf
    python3 build_pdf.py "output/*.tif" -o book.pdf --dpi 400
    python3 build_pdf.py --order-file page_order.txt -o book.pdf

By default, input files are sorted "naturally" (IMG_4274_pa, IMG_4274_pb,
IMG_4275_pa, ... in that order) — this matches restore_pages.py's output
naming as long as spreads were photographed in book order. If filenames
don't sort into the right order (e.g. camera file numbers don't match
page order), list the exact page order yourself in a text file (one
image path per line) and pass it via --order-file instead.

--dpi must match whatever --dpi was used when running restore_pages.py,
so the PDF page size comes out at the pages' true physical size rather
than being computed from the wrong DPI.
"""
import argparse
import glob
import re
import sys

import img2pdf


def natural_key(path: str):
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", path)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="*",
                     help="Page image files/globs (sorted naturally unless --order-file is given)")
    ap.add_argument("-o", "--output", default="book.pdf", help="Output PDF path")
    ap.add_argument("--dpi", type=int, default=400,
                     help="DPI the page images were produced at — must match restore_pages.py --dpi")
    ap.add_argument("--order-file",
                     help="Text file listing image paths in exact desired order, one per line "
                          "(overrides automatic natural-sort ordering)")
    args = ap.parse_args()

    if args.order_file:
        with open(args.order_file) as f:
            paths = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        if not args.images:
            print("No input images given (pass file globs, or use --order-file).", file=sys.stderr)
            sys.exit(1)
        paths = []
        for pattern in args.images:
            matches = glob.glob(pattern)
            paths.extend(matches if matches else [pattern])
        paths = sorted(set(paths), key=natural_key)

    if not paths:
        print("No input images matched.", file=sys.stderr)
        sys.exit(1)

    print(f"Assembling {len(paths)} pages into {args.output} (in this order):")
    for p in paths:
        print(f"  {p}")

    layout_fun = img2pdf.get_fixed_dpi_layout_fun((args.dpi, args.dpi))
    with open(args.output, "wb") as f:
        f.write(img2pdf.convert(paths, layout_fun=layout_fun))

    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()

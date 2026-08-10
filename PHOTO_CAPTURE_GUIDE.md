# Capture guide — photographing the SOSORO books for reproduction

Since the books must stay bound and intact, the goal is to get every
spread as flat, evenly lit, and consistently framed as possible *at
capture time*. Software (our `restore_pages.py` pipeline) can fix
rotation, perspective, and color cast — but it can't fully undo real
page curvature or uneven lighting baked into the photo. Fixing capture
gets you 90% of the way there; software cleans up the rest.

## Recommended: a dedicated overhead book scanner

For a bound, one-of-a-kind book, purpose-built overhead scanners are the
best money-to-quality ratio. They include a V-shaped cradle, built-in
even lighting, and — critically — automatic software dewarping that
flattens the curve of a photographed page far better than we can after
the fact.

- **Fujitsu ScanSnap SV600** — no cradle required, book just rests open
  on the table under the scanner head; has a "book image correction"
  mode specifically for the page-curl-near-spine problem.
- **CZUR Aura Pro / ET-series** — comes with a V-shaped cradle, foot
  pedal for hands-free page turns, auto-flatten + auto-crop + auto-split
  of the spread into two pages, and even has built-in OCR (useful later
  for Stage 2).

Both are usually sold via Amazon/global electronics retailers; check
shipping to Cambodia and expect import duties — a shipping forwarder
may be worth it if there's no local distributor. If budget allows, this
is the option I'd pick: it solves the curvature and lighting problems
at the source instead of fighting them in software.

## DIY alternative (cheaper, more manual, still needs the software cleanup)

If a dedicated scanner isn't practical, this setup gets much better
results than handheld phone photos:

**1. Camera position — fixed, overhead, perpendicular**
- Mount the camera on a copy stand, or a tripod with a horizontal boom
  arm, directly above the book and aimed straight down. Handheld shots
  can't hold a consistent angle/distance from page to page, which is
  part of what made splitting and cropping harder on the samples.
- Keep the same height/zoom for every spread so pages come out a
  consistent size — makes batch processing much more reliable.
- Use a 2-second timer or remote shutter so pressing the button doesn't
  shake the shot.

**2. Flatten the book — this is the single biggest fix**
- A book cradle (~$20–50) that opens the book to about 100–120° reduces
  the page bulge near the spine dramatically compared to laying it flat
  open on a table.
- Press a sheet of clear anti-reflective (museum) glass or acrylic
  gently over the open pages. This is what actually flattens the
  curvature that our software had to fight with a rotation/deskew
  correction on your sample photos — a physically flat page needs
  almost none of that correction, and looks much sharper.

**3. Lighting — even, diffused, symmetric**
- Two continuous LED panels or softboxes, one on each side, at roughly
  45° to the page, same distance and brightness. This is what avoids
  the warm/uneven cast and the shadow gradient we corrected in
  software — better to not need that correction at all.
- Avoid: a single overhead light or window light (causes the gradient
  we saw), and avoid camera flash (creates a hot glare spot and glass
  reflections if you're using a flattening sheet).

**4. Camera settings — manual, locked, consistent**
- **Focus:** manual, or autofocus locked once and not re-triggered per
  shot — refocusing each time introduces small framing drift.
- **Exposure:** manual or locked (AE-L), so brightness stays consistent
  across the whole book instead of drifting page to page.
- **White balance:** set manually using a gray/white card once at the
  start, rather than auto — auto white balance is likely why the two
  sample photos had a slightly different color cast from each other.
- **Orientation:** keep the camera in the same physical orientation for
  every shot (matching the book, not rotated) if your camera supports
  it — avoids relying on auto-rotate detection.
- Shoot the highest resolution/RAW your camera supports; more detail
  now costs nothing and can't be recovered later if the originals are
  ever lost again.

**5. Framing**
- Fill the frame with the spread, leaving a small margin of background
  around all four edges — the software uses that margin to find the
  page boundary.

## What to send me once you've got a new setup

One test spread (or a couple) shot with the new setup — I'll run it
through the pipeline and we can check whether the deskew/color
correction steps need retuning for the new, cleaner input before
processing the full book.

# DXF → Filled SVG: Replication Steps

Turn an Onshape-exported 2D DXF track diagram into a clean, **filled** (solid
black tracks on white), editable SVG overlay for a printed control-panel
transparency. LED holes become true cutouts inside the track bands.

---

## 1. Prerequisites (one-time setup)

Tools used in this workspace:

| Tool | Purpose | Location / install |
| --- | --- | --- |
| Homebrew | package manager | `/opt/homebrew` |
| Inkscape 1.4+ | render / verify / edit SVG | `/Applications/Inkscape.app` |
| Python 3.8+ venv | run the converter | `.venv/` in this folder |
| ezdxf | parse DXF geometry | `pip install` |
| shapely | polygonize + boolean fill | `pip install` |

Create the environment (only needed once):

```zsh
cd /Users/dougfy/Documents/OnShape
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # ezdxf, shapely
```

Load Homebrew in a fresh shell if needed:

```zsh
eval "$(/opt/homebrew/bin/brew shellenv zsh)"
```

---

## 2. Export the DXF from Onshape

1. In the Part Studio, right-click the sketch (or a planar face) → **Export as DXF/DWG**.
2. Export the 2D sketch that contains the track outlines and the LED circles.
3. Save it into this folder, e.g. `Panel 3.dxf`.

Notes:
- The sketch is a loose collection of `LINE` / `ARC` / `CIRCLE` entities — not
  closed polygons. That is fine; the converter closes the gaps.
- Onshape DXFs are often **unitless**. The converter assumes millimetres and
  warns you. Use `--units` to override (see step 4).

---

## 3. Run the converter

```zsh
cd /Users/dougfy/Documents/OnShape
.venv/bin/python dxf_to_editable_svg.py "Panel 3.dxf"
```

This writes `Panel 3.svg` next to the DXF and prints a summary, e.g.:

```
Canvas: 44.00 × 19.00 mm; 75 entities; unitless DXF assumed to be mm.
Filled 5 narrow track region(s); left 1 broad region(s) white.
```

### Options

| Option | Default | When to use |
| --- | --- | --- |
| `output_svg` (positional) | same name as DXF | write to a different path |
| `--units {mm,cm,in,inch}` | auto / mm | DXF has wrong or missing units |
| `--height-mm <mm>` | — | scale so the **total drawing height** equals this many mm |
| `--width-mm <mm>` | — | scale so the **total drawing width** equals this many mm |
| `--tolerance <mm>` | `0.08` | curve flattening quality (smaller = smoother arcs) |

Example with an inch-scaled DXF and custom output:

```zsh
.venv/bin/python dxf_to_editable_svg.py "Panel 3.dxf" "Panel 3.svg" --units in
```

### Setting the real-world size

Onshape DXFs are often unitless, so the safest way to lock the scale is to give
the converter the real physical height or width of the drawing (measured across
the outer outline). Use only one — the other dimension follows proportionally:

```zsh
# the panel outline is 15 cm tall
.venv/bin/python dxf_to_editable_svg.py "Panel 3.dxf" --height-mm 150
```

The width/height thresholds that classify "narrow track" vs "broad background"
scale automatically with this, so the fill is correct at any size. The printed
SVG carries real `mm` units, so it prints at true scale.

---

## 4. How the fill works (so the result is reproducible)

The core logic lives in `build_filled_regions()` in
[dxf_to_editable_svg.py](dxf_to_editable_svg.py):

1. **Flatten** every non-circle entity (`LINE`, `ARC`, `SPLINE`, …) into point
   lists via `ezdxf` `make_path().flattening()`.
2. **Node** the outline: build Shapely `LineString`s → `unary_union` so all
   crossings split into shared endpoints.
3. **Snap** (`snap(noded, noded, 0.2 mm)` + re-union) to bridge the sub-0.1 mm
   gaps between rail ends. This is what fills the triangular wedges at turnouts.
4. **Polygonize** the noded network into planar faces.
5. **Classify** each face by `2 × area / perimeter` (its effective width):
   - `≤ 1.2 mm` → a narrow **track band** → keep and fill black.
   - larger → the broad background between routes → leave white.
6. **Union** the kept faces, then **subtract** the LED circles
   (`Point(center).buffer(radius)` via `difference`). Holes become real cutouts
   inside the fill and never protrude into white space.
7. Emit one compound SVG `<path>` (fill `#000000`, `fill-rule="evenodd"`), with
   the Y axis flipped from CAD-up to SVG-down.

Design rules (do **not** regress these):
- No stroke-widening to fake fills.
- No junction "fill pad" circles.
- Circles are subtracted geometrically, not masked over the whole layer.

---

## 5. Verify the output

Render a high-res PNG headlessly and inspect it:

```zsh
/Applications/Inkscape.app/Contents/MacOS/inkscape "Panel 3.svg" \
  --export-filename="/tmp/panel3.png" --export-width=2200
open /tmp/panel3.png
```

Checklist:
- [ ] Tracks are **solid black** bands.
- [ ] Junction/turnout wedges are filled (no white triangles).
- [ ] Background (center negative space) is **white**.
- [ ] LED holes are white, **fully inside** the tracks (no protrusion).

---

## 6. Edit in Inkscape

```zsh
open -a /Applications/Inkscape.app "Panel 3.svg"
```

Layers in the SVG:
- **Filled artwork** — the visible solid-black track layer (the compound path).
- **Source entities (editable; hidden)** — one SVG element per DXF entity,
  hidden by default. Toggle it on to select/tweak individual imported curves.

The document is in real millimetres (`width`/`height` in `mm`, `viewBox` in mm),
so it prints at true scale.

---

## 7. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Whole panel black, tracks white (inverted) | width threshold too large; the broad face is being filled. Lower `max_width_mm` in `build_filled_regions`. |
| Triangular gaps unfilled at junctions | endpoint gaps bigger than snap tolerance. Raise `snap_tol_mm` (currently `0.2`). |
| Arcs look faceted | lower `--tolerance` (e.g. `0.02`). |
| Wrong physical size | DXF units; pass `--units in`/`--units cm`, or set `--height-mm`/`--width-mm` to the measured outline size. |
| Circles poke outside tracks | ensure circle subtraction is active (it is in `build_filled_regions`); do not re-add a mask. |

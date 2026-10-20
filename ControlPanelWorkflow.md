# Control Panel → Printed Transparency Overlay (Model‑Railroad Panel)

This document describes, concretely, how to go from an Onshape control‑panel model to a
printed **transparency overlay** that looks like the target diagram (the "Julian Engine
Yard" style panel). It is written to remove the ambiguity in the earlier version.

Read this first — it resolves the three things that were unclear:

1. **Onshape only models physical hardware.** The plate, the holes, and the turnout
   switch mounts. Nothing about the *picture* (tracks, text, logo, colors) is modeled in
   Onshape. Those are **not parts**. See "The one idea that makes this work" below.
2. **Only turnouts need positions.** You do not design a full symbol library. You export
   the X/Y of each turnout/LED hole. Everything else in the diagram is drawn freely in a
   2D tool, using those few hole positions as anchors.
3. **You never use a 3D Onshape drawing of the assembly as the artwork.** That is why you
   were seeing hole geometry, the messy switch‑mount body, and a legend you can't delete.
   The artwork is built in a 2D graphics program from a clean coordinate list. The Onshape
   drawing is at most an optional 1:1 registration template, stripped to hole centers only.

---

## The one idea that makes this work

There are **two completely separate deliverables**, and they must not be mixed:

| Deliverable | Lives in | Contains | Output |
|---|---|---|---|
| **A. The physical panel** | Onshape (Part Studio + Assembly) | Plate, button/LED holes, turnout switch mounts | STL/STEP → slicer → 3D print |
| **B. The diagram overlay** | A 2D art tool (Inkscape / Illustrator / Affinity) | Track lines, turnout graphics, text, logo, block colors, the green/red LED rings | PDF or ≥600 DPI PNG → transparency print |

The **only** thing that connects A and B is a short list of coordinates:
the **X/Y (in mm) of each hole** (turnout switch, and its green/red LED holes), measured
from the **bottom‑left corner of the panel = (0, 0)**.

So the entire job is:

1. In Onshape, model the plate + holes + switch mounts. (Deliverable A.)
2. Export the hole coordinates as a small table.
3. In the 2D tool, draw the diagram (Deliverable B) and drop the LED rings / turnout
   graphics exactly on those coordinates so the print lines up with the real holes.

"Create all the parts for the diagram" in the old version was wrong/confusing. **The
diagram has no Onshape parts.** The track lines and labels you see in the target image are
vector objects in the art tool, not thin bodies in Onshape.

---

## Coordinate convention (do this once, never change it)

- Units: **millimeters**.
- Origin: **bottom‑left corner of the panel face = (0, 0)**.
- Axes: **+X to the right, +Y upward**, looking at the printed face.
- Panel face is on the **Top plane**, top surface at z = 0.

> Note on the current `Control Panel` feature: it draws the rectangle **centered on the
> origin**, so its corners are at `(−x/2, −y/2)` and `(+x/2, +y/2)`. For a bottom‑left
> origin you want the corners at `(0, 0)` and `(x, y)`. Either (a) update the feature to
> anchor the rectangle at the origin, or (b) keep it centered and add half the panel size
> when you export coordinates: `x_bottomLeft = x_center + xSize/2`,
> `y_bottomLeft = y_center + ySize/2`. Option (a) is cleaner — recommended.

---

## Phase A — Model the physical panel in Onshape

1. **Plate.** Use the `Control Panel` feature to make the panel rectangle, then extrude to
   plate thickness (e.g. `3 mm`). Keep it one part. This is what prints.
2. **Decide what each turnout control is.** On the target diagram each turnout has a
   **toggle/push position number (1–4)** and a **green + red LED pair**. So each turnout
   cell needs, physically:
   - 1 hole for the switch/button, and
   - 2 small holes for the green and red LEDs (or one hole if you use a bi‑color LED).
3. **Map the iTrain panel to cells.** The iTrain panel is already a grid. Read off which
   **cell (row, column)** each turnout sits in. Make a list like:
   `Turnout 1 → row 1, col 9`, `Turnout 2 → row 2, col 6`, etc. This is your authoritative
   placement list — it is the only positioning data you need.
4. **Build the cell grid as mate connectors.** Put one **Mate connector** at the first
   cell center on the top face, then **Linear pattern → Feature pattern**:
   - Direction 1 = X edge → column spacing × column count.
   - Direction 2 = Y edge → row spacing × row count.
   Name connectors by cell, e.g. `R1C9`, so you can select the right one later.
5. **Cut the holes on the turnout cells only.** For each turnout from step 3, cut the
   switch hole (and LED holes) into the plate, located on that cell's mate connector.
   Non‑turnout cells get nothing — you are not placing buttons everywhere.

At the end of Phase A you have: a printable plate with holes exactly where the turnouts
and their LEDs go, and named mate connectors at each turnout cell.

---

## Phase B — Insert and mate the turnout switches in the Assembly

This is the explicit sequence you asked for. Assume you have (1) the panel part and (2) a
turnout switch part (your toggle/button model, with the messy insert mount in image 2).

**Prepare the switch part once (in its Part Studio):**

1. Open the switch part's Part Studio.
2. Add a **Mate connector** on the switch at its **mounting datum** — the point/axis that
   should sit on the panel hole (typically the center of its threaded shaft, on the face
   that contacts the plate). Orient its Z along the shaft axis.
3. Name it `switchMount`. This single connector is how it will snap to the panel.

**In the Assembly:**

1. **Insert the panel** (`Insert` → the panel Part Studio → the plate part).
2. **Fix the panel** so it can't move: right‑click it → **Fix** (grounds it).
3. **Insert the turnout switch** (`Insert` → the switch part). It drops in loose.
4. Click **Fastened mate**.
5. For the **first mate connector**, pick the switch's `switchMount` connector.
6. For the **second mate connector**, pick the panel grid connector for that turnout's
   cell — e.g. `R1C9` for Turnout 1. Hover until the correct named connector highlights,
   then click.
7. Onshape snaps the switch onto the hole. If it faces the wrong way or sinks into the
   plate, **edit the mate** and set a **Z offset** (= plate thickness or mount depth) and
   a **rotation** so the toggle points the right way.
8. **Repeat steps 3–7 for each turnout**, each time choosing the grid connector that
   matches its iTrain cell. Because the connectors are named by cell, you just pick the
   matching name.

Result: all turnout switches are mounted at the correct cells. You can keep these as the
physical assembly for fit‑checking. **None of this is the diagram** — it is just hardware.

> Tip: if a specific grid connector is hard to select in the graphics area, open the
> feature/instance list and pick the named connector there instead of clicking in 3D.

---

## Phase C — Get clean hole positions OUT of Onshape (no messy drawing)

You need the **X/Y of each hole**, in mm, from the bottom‑left origin. Do **not** make a
full assembly drawing for this — that is exactly what produced the hole clutter, the
switch‑mount body, and the legend you couldn't remove.

Pick one of these two clean methods:

**Method 1 — Coordinate list via FeatureScript (most reliable).**
In a small FeatureScript feature, evaluate each hole/cell mate connector and print its
location in mm from the bottom‑left corner, e.g.:

```
name, x_mm, y_mm, kind
Turnout1_switch, 243.0, 180.0, switch
Turnout1_LEDgreen, 243.0, 192.0, led_green
Turnout1_LEDred,   243.0, 168.0, led_red
...
```

Paste that into a `holes.csv`. This table is the single source of truth for the artwork.
(If you want, this can be added to the panel feature so it auto‑prints the list.)

**Method 2 — Clean 1:1 vector template (if you prefer to trace visually).**
Make a **dedicated sketch** on the top face named `ArtworkRegistration` that contains
**only** the panel outline and a small **point at each hole center** — nothing else, no
bodies, no switch mounts. Export **that sketch** to **DXF or SVG** at **1:1**. You get a
clean outline + dots, with none of the 3D hardware.

### About the legend you can't delete

The legend/title block is **not part of your geometry** — it belongs to the **drawing sheet
template**. To get rid of it:

- Best: **don't use a Drawing at all.** Use Method 1 (CSV) or export the
  `ArtworkRegistration` **sketch** to DXF/SVG (Method 2). Sketch/DXF export has no title
  block or legend.
- If you must use a Drawing: when creating it, choose a **blank / no‑title‑block
  template**, or after creation right‑click the sheet → **Edit sheet / Properties** and
  switch to a blank template, or select and **delete the title‑block border**. The legend
  is that template object, so removing/replacing the template removes the legend.

Either way, the goal of Phase C is just: **a clean list (or dots) of hole centers in mm.**

---

## Phase D — Build the diagram overlay in a 2D tool (this is image 3)

This is where the actual picture is made. **Nothing here is an Onshape part.** Every track
line, label, logo and LED ring is a vector object you draw/arrange in the art tool.

1. **Set the canvas to the panel size**, 1:1 (e.g. 305 × 203 mm). Put its origin at the
   bottom‑left to match Onshape.
2. **Import the hole anchors.** Either place a dot at each `holes.csv` coordinate, or
   import the `ArtworkRegistration` DXF/SVG as a locked background layer. These dots are
   where real holes/LEDs are — your art must line up to them.
3. **Draw the track schematic** (the black lines in the target image): straight runs,
   the diagonal ladder, the branch to each turnout. You draw these **freely**, snapping
   the branch/turnout points to the imported hole anchors. The tracks themselves have no
   physical counterpart — they are purely graphic, so they don't need Onshape coordinates
   beyond touching the turnout anchors.
4. **Place the turnout graphics / LED rings** exactly on the switch and LED anchors, so
   the green/red LEDs show through their holes and the toggle sticks through its hole.
5. **Add the text and branding**: track names ("East Storage Track", etc.), the big title,
   the logo, the numbered tags (1–4), the border and corner screws — all as vector/text
   objects. This is the part Onshape deliberately does not do.
6. **Keep hole areas clear** (no ink over the switch holes) so hardware passes through;
   the LED rings can be colored because light shines through.

> Why this is easier: you only had to get **a handful of turnout/LED coordinates** exact.
> The rest of the diagram is ordinary drawing, which a 2D tool does far better and faster
> than modeling thin bodies in Onshape ever could.

---

## Phase E — Print the transparency and register it

1. Hide/delete the registration/anchor layer; keep only the finished artwork layer.
2. Export **one flattened layer** to **PDF** (vector — crisp lines/text) or **≥600 DPI
   PNG** if your printer needs raster. The page is 1:1 with the panel.
3. If the overlay goes on the **underside** of a clear panel, **mirror** it so ink is
   protected and text reads correctly through the material.
4. Print on clear transparency film / clear adhesive stock. Trim to the panel outline.
5. **Register using the holes** — they are the most reliable physical fiducials. Line the
   printed LED rings and switch openings to the real holes, then adhere.
6. Verify 2–3 hole centers with calipers against `holes.csv` before a full run.

---

## What each tool is responsible for (summary)

- **Onshape (physical only):** plate, turnout switch holes, LED holes, switch mounts,
  assembly fit of the switches, and a clean list of hole X/Y in mm. Nothing graphic.
- **2D art tool (diagram only):** tracks, turnout/LED graphics, text, logo, colors,
  border — the entire look of image 3 — placed onto the hole anchors from Onshape.
- **Slicer / printer:** plate from STL/STEP; transparency from the single exported layer.

## Checklist

- [ ] Convention fixed: mm, bottom‑left = (0,0), +X right, +Y up.
- [ ] Plate modeled and extruded (one part).
- [ ] iTrain cells mapped: each turnout → (row, col).
- [ ] Grid mate connectors created and **named by cell** (`R#C#`).
- [ ] Turnout switch holes + green/red LED holes cut on turnout cells only.
- [ ] Switch part has a named `switchMount` mate connector.
- [ ] Assembly: panel fixed, each turnout Fastened‑mated to its cell connector.
- [ ] Hole coordinates exported as `holes.csv` (Method 1) or clean DXF/SVG (Method 2).
- [ ] No Drawing/legend used for artwork (or template stripped to blank).
- [ ] Diagram drawn in 2D tool on hole anchors (tracks, LEDs, text, logo).
- [ ] Single flattened layer exported (PDF or ≥600 DPI PNG), mirrored if underside.
- [ ] Printed on clear film, registered to holes, verified with calipers.

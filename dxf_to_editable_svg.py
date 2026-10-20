#!/usr/bin/env python3
"""Convert a 2D DXF sketch into an editable, layered SVG for Inkscape.

The output contains a visible filled-artwork layer (closed contours use the
 even-odd fill rule, so nested contours become transparent holes) and a hidden
source layer with one editable SVG object per DXF entity.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import ezdxf
from ezdxf.entities import DXFGraphic
from ezdxf.path import make_path
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, snap, unary_union

# DXF $INSUNITS values, converted to millimetres.
UNIT_TO_MM = {
    0: 1.0,       # unitless: assume mm; a warning is emitted
    1: 25.4,      # inches
    2: 304.8,      # feet
    3: 1609344.0,  # miles
    4: 1.0,        # millimetres
    5: 10.0,       # centimetres
    6: 1000.0,     # metres
    7: 1000000.0,  # kilometres
    8: 0.0000254,  # microinches
    9: 0.0254,     # mils
    10: 914.4,     # yards
    13: 0.001,     # microns
    14: 100.0,     # decimetres
    15: 10000.0,   # decametres
    16: 100000.0,  # hectometres
    17: 1.0e12,    # gigametres
    21: 304.8006096012,  # US survey feet
    22: 25.4000508001,   # US survey inches
    23: 0.9144018288,    # US survey yards
}

SUPPORTED_PATH_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "ELLIPSE", "SPLINE"}


def safe_id(value: str) -> str:
    """Return a stable SVG-safe identifier fragment."""
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value or "unnamed"


def attr_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def flatten_entity(entity: DXFGraphic, scale: float, tolerance_mm: float) -> tuple[list[tuple[float, float]], bool]:
    """Flatten a DXF curve into SVG-ready mm points and report whether closed."""
    path = make_path(entity)
    distance = max(tolerance_mm / scale, 1e-9)
    points = [(float(p.x) * scale, float(p.y) * scale) for p in path.flattening(distance=distance, segments=8)]
    if len(points) < 2:
        return points, False
    closed = bool(path.is_closed)
    if closed and math.dist(points[0], points[-1]) > tolerance_mm * 0.1:
        points.append(points[0])
    return points, closed


def svg_path_data(points: Iterable[tuple[float, float]], min_x: float, max_y: float) -> str:
    """Create SVG path data, mapping CAD's upward Y to SVG's downward Y."""
    converted = [(x - min_x, max_y - y) for x, y in points]
    if not converted:
        return ""
    parts = [f"M {converted[0][0]:.6f},{converted[0][1]:.6f}"]
    parts.extend(f"L {x:.6f},{y:.6f}" for x, y in converted[1:])
    if math.dist(converted[0], converted[-1]) < 1e-5:
        parts.append("Z")
    return " ".join(parts)


def build_filled_regions(
    items: list[tuple[DXFGraphic, str, bool, list[tuple[float, float]]]],
    circle_defs: list[tuple[float, float, float]],
    scale: float = 1.0,
    max_width_mm: float = 1.2,
    snap_tol_mm: float = 0.2,
) -> tuple[list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]], int, int]:
    """Turn the DXF outline into filled track polygons using robust 2D geometry.

    The outline curves are noded and snapped (to bridge tiny endpoint gaps),
    polygonised into planar faces, and only the narrow track-band faces are
    kept (the broad enclosed background between routes stays white). LED circles
    are subtracted, so holes appear only inside filled track and never poke out.
    Returns (polygons, filled_face_count, broad_face_count) where each polygon is
    (exterior_ring, [hole_rings]). Width/snap thresholds track the drawing scale
    so the classifier works at any physical size.
    """
    max_width = max_width_mm * scale
    snap_tol = snap_tol_mm * scale
    lines = [
        LineString(points)
        for entity, _, _, points in items
        if entity.dxftype() != "CIRCLE" and len(points) >= 2
    ]
    if not lines:
        return [], 0, 0

    noded = unary_union(lines)
    # Snapping closes the sub-threshold gaps between rail ends that otherwise
    # leave a face open, which is what produced the unfilled triangular wedges.
    noded = unary_union(snap(noded, noded, snap_tol))

    track_faces: list[Polygon] = []
    broad_face_count = 0
    for face in polygonize(noded):
        perimeter = face.length
        if perimeter <= 1e-9:
            continue
        effective_width = 2.0 * face.area / perimeter
        if effective_width <= max_width:
            track_faces.append(face)
        else:
            broad_face_count += 1

    if not track_faces:
        return [], 0, broad_face_count

    filled = unary_union(track_faces)
    if circle_defs:
        holes = unary_union([Point(cx, cy).buffer(r, quad_segs=48) for cx, cy, r in circle_defs])
        filled = filled.difference(holes)

    if filled.is_empty:
        return [], 0, broad_face_count
    geoms = list(filled.geoms) if isinstance(filled, MultiPolygon) else [filled]

    polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]] = []
    for geom in geoms:
        if geom.is_empty or not isinstance(geom, Polygon):
            continue
        exterior = [(float(x), float(y)) for x, y in geom.exterior.coords]
        interiors = [[(float(x), float(y)) for x, y in ring.coords] for ring in geom.interiors]
        polygons.append((exterior, interiors))

    return polygons, len(track_faces), broad_face_count


def virtual_entities(entity: DXFGraphic) -> list[DXFGraphic]:
    """Expand block inserts for conversion without modifying the DXF."""
    if entity.dxftype() == "INSERT":
        try:
            return list(entity.virtual_entities())
        except (AttributeError, ezdxf.DXFError):
            return []
    return [entity]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a 2D DXF sketch into a layered, editable SVG for Inkscape."
    )
    parser.add_argument("input_dxf", type=Path, help="DXF file to convert")
    parser.add_argument("output_svg", type=Path, nargs="?", help="output SVG (defaults to same name as DXF)")
    parser.add_argument("--units", choices=("mm", "cm", "in", "inch"), help="override DXF units if they are missing or wrong")
    parser.add_argument("--height-mm", type=float, help="scale so the drawing's total height equals this many mm")
    parser.add_argument("--width-mm", type=float, help="scale so the drawing's total width equals this many mm")
    parser.add_argument("--tolerance", type=float, default=0.08, help="curve flattening tolerance in mm (default: 0.08)")
    args = parser.parse_args()

    source = args.input_dxf.expanduser()
    destination = args.output_svg or source.with_suffix(".svg")
    if not source.is_file():
        parser.error(f"DXF file not found: {source}")
    if args.tolerance <= 0:
        parser.error("--tolerance must be greater than zero")

    try:
        doc = ezdxf.readfile(source)
    except (OSError, ezdxf.DXFError) as exc:
        print(f"Could not read DXF: {exc}", file=sys.stderr)
        return 2

    if args.height_mm is not None and args.width_mm is not None:
        parser.error("use only one of --height-mm or --width-mm")

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    unit_scales = {"mm": 1.0, "cm": 10.0, "in": 25.4, "inch": 25.4}
    if args.units:
        scale = unit_scales[args.units]
        unit_note = f"units overridden to {args.units}"
    else:
        scale = UNIT_TO_MM.get(insunits)
        if scale is None:
            print(f"Unsupported DXF unit code {insunits}; use --units mm or --units in.", file=sys.stderr)
            return 2
        unit_note = "unitless DXF assumed to be mm" if insunits == 0 else f"DXF unit code {insunits} converted to mm"
        if insunits == 0 and args.height_mm is None and args.width_mm is None:
            print("Warning: DXF has no declared units; assuming millimetres. Use --units or --height-mm/--width-mm if that is wrong.", file=sys.stderr)

    msp = doc.modelspace()

    # Scale so the drawing's real extent matches a requested physical size.
    if args.height_mm is not None or args.width_mm is not None:
        raw_x: list[float] = []
        raw_y: list[float] = []
        for raw in msp:
            for item in virtual_entities(raw):
                if item.dxftype() not in SUPPORTED_PATH_TYPES and item.dxftype() != "CIRCLE":
                    continue
                try:
                    for p in make_path(item).flattening(distance=0.5, segments=4):
                        raw_x.append(float(p.x))
                        raw_y.append(float(p.y))
                except (TypeError, ValueError, ezdxf.DXFError):
                    continue
        if not raw_x or not raw_y:
            parser.error("cannot measure drawing extent for --height-mm/--width-mm")
        span_x = max(raw_x) - min(raw_x)
        span_y = max(raw_y) - min(raw_y)
        if args.height_mm is not None:
            if span_y <= 0:
                parser.error("drawing has zero height; cannot apply --height-mm")
            scale = args.height_mm / span_y
            unit_note = f"scaled so height = {args.height_mm:g} mm"
        else:
            if span_x <= 0:
                parser.error("drawing has zero width; cannot apply --width-mm")
            scale = args.width_mm / span_x
            unit_note = f"scaled so width = {args.width_mm:g} mm"
    entities: list[tuple[DXFGraphic, str, str, bool]] = []
    skipped = Counter()
    bounds: list[tuple[float, float]] = []
    flattened_cache: dict[int, tuple[list[tuple[float, float]], bool]] = {}

    for original in msp:
        expanded = virtual_entities(original)
        if not expanded:
            skipped[original.dxftype()] += 1
            continue
        for entity in expanded:
            kind = entity.dxftype()
            layer = entity.dxf.get("layer", "0")
            if kind == "CIRCLE":
                center = entity.dxf.center
                radius = float(entity.dxf.radius)
                cx, cy, r = float(center.x) * scale, float(center.y) * scale, radius * scale
                points = [
                    (cx + r * math.cos(2 * math.pi * step / 96),
                     cy + r * math.sin(2 * math.pi * step / 96))
                    for step in range(97)
                ]
                closed = True
            elif kind in SUPPORTED_PATH_TYPES:
                try:
                    points, closed = flatten_entity(entity, scale, args.tolerance)
                except (TypeError, ValueError, ezdxf.DXFError):
                    skipped[kind] += 1
                    continue
            else:
                skipped[kind] += 1
                continue
            if len(points) < 2:
                skipped[kind] += 1
                continue
            bounds.extend(points)
            flattened_cache[id(entity)] = (points, closed)
            entities.append((entity, layer, kind, closed))

    if not entities or not bounds:
        print("No supported 2D line/curve entities found in the DXF modelspace.", file=sys.stderr)
        return 2

    min_x = min(p[0] for p in bounds)
    min_y = min(p[1] for p in bounds)
    max_x = max(p[0] for p in bounds)
    max_y = max(p[1] for p in bounds)
    margin = 2.0
    width = max(max_x - min_x, 0.1) + 2 * margin
    height = max(max_y - min_y, 0.1) + 2 * margin
    # Include the margin in the origin transform without changing the CAD-relative placement.
    view_min_x = min_x - margin
    view_max_y = max_y + margin

    by_layer: dict[str, list[tuple[DXFGraphic, str, bool, list[tuple[float, float]]]]] = defaultdict(list)
    for entity, layer, kind, closed in entities:
        points = flattened_cache[id(entity)][0]
        by_layer[layer].append((entity, kind, closed, points))

    output: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"',
        '     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',
        f'     width="{width:.6f}mm" height="{height:.6f}mm" viewBox="0 0 {width:.6f} {height:.6f}">',
        f'  <title>{attr_escape(source.stem)} — editable DXF conversion</title>',
        f'  <desc>Converted from {attr_escape(source.name)}; {attr_escape(unit_note)}. Geometry is millimetres.</desc>',
    ]

    # LED circles become true cutouts subtracted from the filled track polygons,
    # so a hole only appears where it overlaps filled track and never protrudes
    # into the white background.
    circle_defs: list[tuple[float, float, float]] = []
    for entity, _, kind, _ in entities:
        if kind != "CIRCLE":
            continue
        center = entity.dxf.center
        circle_defs.append(
            (float(center.x) * scale, float(center.y) * scale, float(entity.dxf.radius) * scale)
        )

    # The visible artwork is a solid-filled track layer. Narrow outline faces are
    # polygonised and unioned into solid regions; LED circles are cut out.
    output.append(
        '  <g inkscape:groupmode="layer" inkscape:label="Filled artwork" id="filled_artwork">'
    )
    filled_loop_count = 0
    omitted_broad_faces = 0
    for layer_name, items in by_layer.items():
        polygons, face_count, broad_faces = build_filled_regions(items, circle_defs, scale)
        omitted_broad_faces += broad_faces
        filled_loop_count += face_count
        layer_id = safe_id(layer_name)
        ring_paths: list[str] = []
        for exterior, interiors in polygons:
            ring_paths.append(svg_path_data(exterior, view_min_x, view_max_y))
            ring_paths.extend(svg_path_data(ring, view_min_x, view_max_y) for ring in interiors)
        if ring_paths:
            compound = " ".join(ring_paths)
            output.append(
                f'    <path id="fill_{layer_id}" inkscape:label="{attr_escape(layer_name)} filled tracks" '
                f'd="{compound}" fill="#000000" fill-rule="evenodd" stroke="none"/>'
            )
    output.append('  </g>')

    # Hidden source layer retains one independently editable SVG element per DXF entity.
    output.append('  <g inkscape:groupmode="layer" inkscape:label="Source entities (editable; hidden)" '
                  'id="source_entities" style="display:none">')
    output.append('    <desc>Toggle this layer on to inspect or edit individual imported DXF entities.</desc>')
    object_number = 0
    for layer_name, items in by_layer.items():
        layer_id = safe_id(layer_name)
        output.append(f'    <g inkscape:label="DXF layer: {attr_escape(layer_name)}" id="source_{layer_id}">')
        for entity, kind, closed, points in items:
            object_number += 1
            entity_handle = entity.dxf.get("handle", f"item{object_number}")
            label = f"{kind} {entity_handle} — {layer_name}"
            if kind == "CIRCLE":
                center = entity.dxf.center
                cx = float(center.x) * scale - view_min_x
                cy = view_max_y - float(center.y) * scale
                radius = float(entity.dxf.radius) * scale
                output.append(
                    f'      <circle id="entity_{object_number}" inkscape:label="{attr_escape(label)}" '
                    f'cx="{cx:.6f}" cy="{cy:.6f}" r="{radius:.6f}" fill="none" '
                    'stroke="#000000" stroke-width="0.25"/>'
                )
            else:
                data = svg_path_data(points, view_min_x, view_max_y)
                fill = "#000000" if closed else "none"
                stroke = "none" if closed else "#000000"
                output.append(
                    f'      <path id="entity_{object_number}" inkscape:label="{attr_escape(label)}" '
                    f'd="{data}" fill="{fill}" fill-rule="evenodd" stroke="{stroke}" '
                    'stroke-width="0.25" stroke-linecap="round" stroke-linejoin="round"/>'
                )
        output.append('    </g>')
    output.append('  </g>')
    output.append('</svg>')

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")

    counts = Counter(kind for _, _, kind, _ in entities)
    print(f"Created editable SVG: {destination}")
    print(f"Canvas: {width:.2f} × {height:.2f} mm; {len(entities)} entities; {unit_note}.")
    print(f"Filled {filled_loop_count} narrow track region(s); left {omitted_broad_faces} broad region(s) white.")
    print("Entity counts: " + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())))
    if skipped:
        print("Skipped unsupported entities: " + ", ".join(f"{kind}={count}" for kind, count in sorted(skipped.items())))
    print("Open the SVG in Inkscape. The visible Filled artwork layer is black; turn on Source entities to select individual imported objects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a backlit waterslide-decal panel template from a 2D DXF sketch.

The output is a layered SVG designed for *clear* decal film transferred onto
clear / frosted acrylic and lit from behind:

  * Backlight mask   - a solid black field that BLOCKS light, with the track
                       diagram and LED spots knocked out so those areas glow.
  * Track glow       - an optional pale tint painted into the track windows so
                       the illuminated routes read as warm lines.
  * LED windows      - fully clear circles on exact LED centres; the real
                       red/green LEDs shine straight through.
  * Gold frame/text  - translucent coloured ink that glows softly (decorative).
  * Cut & bleed      - trim outline plus bleed, so the decal trims cleanly.

Because black = opaque and clear = lit, the artwork is a *mask*, not paint on
black. Registration and physical size come straight from the DXF geometry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ezdxf
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

import dxf_to_editable_svg as conv


def _ring_to_path(ring, view_min_x: float, view_max_y: float) -> str:
    return conv.svg_path_data(list(ring.coords), view_min_x, view_max_y)


def _polygon_paths(geom, view_min_x: float, view_max_y: float) -> list[str]:
    """Flatten a (Multi)Polygon into SVG ring paths (exterior + holes)."""
    paths: list[str] = []
    geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in geoms:
        if poly.is_empty or not isinstance(poly, Polygon):
            continue
        paths.append(_ring_to_path(poly.exterior, view_min_x, view_max_y))
        paths.extend(_ring_to_path(ring, view_min_x, view_max_y) for ring in poly.interiors)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a backlit decal-mask panel SVG from a 2D DXF sketch."
    )
    parser.add_argument("input_dxf", type=Path, help="DXF file to convert")
    parser.add_argument("output_svg", type=Path, nargs="?", help="output SVG (defaults to '<name> decal panel.svg')")
    parser.add_argument("--height-mm", type=float, default=150.0, help="real drawing height in mm (default: 150)")
    parser.add_argument("--bleed-mm", type=float, default=3.0, help="bleed added around the panel in mm (default: 3)")
    parser.add_argument("--tolerance", type=float, default=0.08, help="curve flattening tolerance in mm (default: 0.08)")
    parser.add_argument("--track-tint", default="#FFE7B3", help="glow colour painted into the track windows")
    parser.add_argument("--gold", default="#C9A227", help="frame / title colour")
    args = parser.parse_args()

    source = args.input_dxf.expanduser()
    destination = args.output_svg or source.with_name(f"{source.stem} decal panel.svg")
    if not source.is_file():
        parser.error(f"DXF file not found: {source}")
    if args.height_mm <= 0:
        parser.error("--height-mm must be greater than zero")

    try:
        doc = ezdxf.readfile(source)
    except (OSError, ezdxf.DXFError) as exc:
        print(f"Could not read DXF: {exc}", file=sys.stderr)
        return 2

    msp = doc.modelspace()

    # Gather flattened geometry and LED circles with the same logic the converter
    # uses, so the decal lines up perfectly with the exported sketch.
    items: list[tuple[conv.DXFGraphic, str, bool, list[tuple[float, float]]]] = []
    circle_centres: list[tuple[float, float, float]] = []  # in raw drawing units
    raw_pts: list[tuple[float, float]] = []
    for raw in msp:
        for entity in conv.virtual_entities(raw):
            kind = entity.dxftype()
            if kind == "CIRCLE":
                c = entity.dxf.center
                circle_centres.append((float(c.x), float(c.y), float(entity.dxf.radius)))
                raw_pts.append((float(c.x), float(c.y)))
                items.append((entity, "0", True, []))
                continue
            if kind not in conv.SUPPORTED_PATH_TYPES:
                continue
            try:
                points, closed = conv.flatten_entity(entity, 1.0, args.tolerance)
            except (TypeError, ValueError, ezdxf.DXFError):
                continue
            if len(points) < 2:
                continue
            raw_pts.extend(points)
            items.append((entity, "0", closed, points))

    if not raw_pts:
        print("No supported 2D geometry found in the DXF modelspace.", file=sys.stderr)
        return 2

    span_y = max(p[1] for p in raw_pts) - min(p[1] for p in raw_pts)
    if span_y <= 0:
        parser.error("drawing has zero height; cannot apply --height-mm")
    scale = args.height_mm / span_y

    # Re-flatten at the real scale so the shapely geometry is in millimetres.
    scaled_items: list[tuple[conv.DXFGraphic, str, bool, list[tuple[float, float]]]] = []
    bounds: list[tuple[float, float]] = []
    for entity, layer, closed, _ in items:
        if entity.dxftype() == "CIRCLE":
            scaled_items.append((entity, layer, closed, []))
            continue
        points, is_closed = conv.flatten_entity(entity, scale, args.tolerance)
        scaled_items.append((entity, layer, is_closed, points))
        bounds.extend(points)
    led_defs = [(cx * scale, cy * scale, r * scale) for cx, cy, r in circle_centres]
    bounds.extend((cx, cy) for cx, cy, _ in led_defs)

    min_x = min(p[0] for p in bounds)
    min_y = min(p[1] for p in bounds)
    max_x = max(p[0] for p in bounds)
    max_y = max(p[1] for p in bounds)
    panel_w = max_x - min_x
    panel_h = max_y - min_y

    bleed = args.bleed_mm
    canvas_w = panel_w + 2 * bleed
    canvas_h = panel_h + 2 * bleed
    view_min_x = min_x - bleed
    view_max_y = max_y + bleed

    # Build the lit regions. build_filled_regions already drops the broad
    # background and subtracts LEDs; unioning the LED discs back in gives the
    # full clear (light-passing) region.
    polygons, face_count, _ = conv.build_filled_regions(scaled_items, led_defs, scale)
    track_polys = [Polygon(ext, holes) for ext, holes in polygons if len(ext) >= 4]
    tracks_union = unary_union(track_polys) if track_polys else Polygon()
    leds_union = unary_union([Point(cx, cy).buffer(r, quad_segs=64) for cx, cy, r in led_defs]) if led_defs else Polygon()
    clear_region = unary_union([tracks_union, leds_union])

    panel = box(min_x, min_y, max_x, max_y)
    black_mask = panel.difference(clear_region)

    mask_paths = _polygon_paths(black_mask, view_min_x, view_max_y)
    track_paths = _polygon_paths(tracks_union, view_min_x, view_max_y)

    def rect(x, y, w, h):
        return (x - view_min_x, view_max_y - (y + h), w, h)

    panel_x, panel_y, _, _ = rect(min_x, min_y, panel_w, panel_h)
    cut = (panel_x, panel_y, panel_w, panel_h)
    title_cx = canvas_w / 2
    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"',
        '     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',
        f'     width="{canvas_w:.4f}mm" height="{canvas_h:.4f}mm" viewBox="0 0 {canvas_w:.4f} {canvas_h:.4f}">',
        f'  <title>{conv.attr_escape(source.stem)} — backlit decal panel</title>',
        f'  <desc>Clear-decal backlight mask from {conv.attr_escape(source.name)}; '
        f'panel {panel_w:.1f}×{panel_h:.1f} mm, {bleed:g} mm bleed. Black blocks light; clear glows.</desc>',
    ]

    # 1. Backlight mask: the solid black field with track + LED windows knocked out.
    out.append('  <g inkscape:groupmode="layer" inkscape:label="Backlight mask (black)" id="mask">')
    if mask_paths:
        out.append(
            f'    <path id="backlight_mask" d="{" ".join(mask_paths)}" '
            'fill="#000000" fill-rule="evenodd" stroke="none"/>'
        )
    out.append('  </g>')

    # 2. Track glow: pale tint inside the track windows (LED holes stay pure clear).
    out.append('  <g inkscape:groupmode="layer" inkscape:label="Track glow (tint)" id="track_glow">')
    if track_paths:
        out.append(
            f'    <path id="track_tint" d="{" ".join(track_paths)}" '
            f'fill="{conv.attr_escape(args.track_tint)}" fill-rule="evenodd" fill-opacity="0.55" stroke="none"/>'
        )
    out.append('  </g>')

    # 3. LED windows: thin rings on exact centres (the clear hole already lets the LED through).
    out.append('  <g inkscape:groupmode="layer" inkscape:label="LED windows" id="leds">')
    for i, (cx, cy, r) in enumerate(led_defs, 1):
        sx = cx - view_min_x
        sy = view_max_y - cy
        out.append(
            f'    <circle id="led_{i}" cx="{sx:.4f}" cy="{sy:.4f}" r="{r:.4f}" '
            'fill="none" stroke="#FFFFFF" stroke-width="0.3" stroke-opacity="0.6"/>'
        )
    out.append('  </g>')

    # 4. Gold frame (decorative translucent ink that glows softly).
    inset = max(bleed, 3.0)
    fx, fy = panel_x + inset, panel_y + inset
    fw, fh = panel_w - 2 * inset, panel_h - 2 * inset
    out.append('  <g inkscape:groupmode="layer" inkscape:label="Frame (gold)" id="frame">')
    out.append(
        f'    <rect id="gold_frame" x="{fx:.4f}" y="{fy:.4f}" width="{fw:.4f}" height="{fh:.4f}" '
        f'rx="2" fill="none" stroke="{conv.attr_escape(args.gold)}" stroke-width="0.8"/>'
    )
    out.append('  </g>')

    # 5. Text placeholders (editable; move / rename to taste).
    label_y = panel_y + panel_h - 4
    out.append('  <g inkscape:groupmode="layer" inkscape:label="Text (gold / white)" id="text">')
    out.append(
        f'    <text id="title" x="{title_cx:.4f}" y="{panel_y + 10:.4f}" text-anchor="middle" '
        f'font-family="Georgia, \'Times New Roman\', serif" font-size="11" fill="{conv.attr_escape(args.gold)}">'
        'JULIAN ENGINE YARD</text>'
    )
    out.append(
        f'    <text id="label_east" x="{panel_x + 6:.4f}" y="{panel_y + panel_h/2:.4f}" '
        'font-family="Georgia, serif" font-size="6" fill="#FFFFFF">East Storage</text>'
    )
    out.append(
        f'    <text id="label_west" x="{panel_x + panel_w - 6:.4f}" y="{panel_y + panel_h/2:.4f}" '
        'text-anchor="end" font-family="Georgia, serif" font-size="6" fill="#FFFFFF">West Storage</text>'
    )
    out.append(
        f'    <text id="label_uncoupler" x="{title_cx:.4f}" y="{label_y:.4f}" text-anchor="middle" '
        'font-family="Georgia, serif" font-size="5" fill="#FFFFFF">Uncoupler</text>'
    )
    out.append(
        f'    <text id="label_company" x="{panel_x + 6:.4f}" y="{label_y:.4f}" '
        f'font-family="Georgia, serif" font-size="5" fill="{conv.attr_escape(args.gold)}">Julian RR Co.</text>'
    )
    out.append('  </g>')

    # 6. Cut & bleed guides (non-printing reference; delete or hide before printing).
    out.append('  <g inkscape:groupmode="layer" inkscape:label="Cut &amp; bleed (guide)" id="guides">')
    out.append(
        f'    <rect id="bleed" x="0" y="0" width="{canvas_w:.4f}" height="{canvas_h:.4f}" '
        'fill="none" stroke="#00AEEF" stroke-width="0.2" stroke-dasharray="1,1"/>'
    )
    out.append(
        f'    <rect id="cut" x="{cut[0]:.4f}" y="{cut[1]:.4f}" width="{cut[2]:.4f}" height="{cut[3]:.4f}" '
        'fill="none" stroke="#FF00FF" stroke-width="0.25" stroke-dasharray="2,1"/>'
    )
    out.append('  </g>')

    out.append('</svg>')
    destination.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"Created decal panel SVG: {destination}")
    print(f"Panel: {panel_w:.1f} × {panel_h:.1f} mm (+{bleed:g} mm bleed) → canvas {canvas_w:.1f} × {canvas_h:.1f} mm")
    print(f"Lit: {face_count} track region(s) + {len(led_defs)} LED window(s) knocked out of the black mask.")
    print("Layers: Backlight mask, Track glow, LED windows, Frame, Text, Cut & bleed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

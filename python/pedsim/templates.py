"""Building templates for the field: circle or rectangle, then a door.

The Java editor draws freehand polygons. For Taş Tepeler fieldwork the useful
shapes are a round enclosure or a rectangular house, each with one entrance.
This module builds those footprints and places the entrance OD just outside
the door.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .building import STANDARD_BUILDING_HEIGHT, Building
from .phases import entrance_point

Point = Tuple[float, float]


def circle_polygon(cx: float, cy: float, radius_m: float, n: int = 24) -> List[Point]:
    """Regular n-gon approximating a circle. ``n`` ≥ 8."""
    n = max(8, int(n))
    r = abs(float(radius_m))
    if r <= 0:
        raise ValueError("circle radius must be positive")
    return [
        (cx + r * math.cos(2.0 * math.pi * i / n),
         cy + r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]


def rect_polygon(x0: float, y0: float, x1: float, y1: float) -> List[Point]:
    """Axis-aligned rectangle from two opposite corners."""
    xa, xb = sorted((float(x0), float(x1)))
    ya, yb = sorted((float(y0), float(y1)))
    if xb - xa < 1e-6 or yb - ya < 1e-6:
        raise ValueError("rectangle needs non-zero width and height")
    return [(xa, ya), (xb, ya), (xb, yb), (xa, yb)]


def building_centre(building: Building) -> Point:
    pts = building.footprint.as_xy()
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def nearest_edge(building: Building, x: float, y: float):
    """Closest facade segment and the projection of ``(x, y)`` onto it."""
    pts = list(building.footprint.as_xy())
    if len(pts) < 2:
        raise ValueError("building has no facade")
    ring = pts + [pts[0]]
    best = None
    best_d = float("inf")
    for a, b in zip(ring, ring[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 <= 0:
            t, proj = 0.0, a
        else:
            t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
            proj = (a[0] + t * dx, a[1] + t * dy)
        d = math.hypot(x - proj[0], y - proj[1])
        if d < best_d:
            length = math.sqrt(L2) if L2 > 0 else 0.0
            best_d = d
            best = (a, b, proj, dx, dy, length)
    return best


def entrance_from_door(building: Building, door_x: float, door_y: float,
                      offset_m: float = 3.0) -> Point:
    """OD just outside the door, offset along the outward normal of that facade.

    Falls back to the longest-facade rule if the footprint is degenerate.
    """
    try:
        a, b, mid, dx, dy, length = nearest_edge(building, door_x, door_y)
    except ValueError:
        return entrance_point(building, offset_m)
    if length <= 0:
        return entrance_point(building, offset_m)
    nx, ny = -dy / length, dx / length
    outward = (mid[0] + nx * offset_m, mid[1] + ny * offset_m)
    if building.contains(outward[0], outward[1]):
        outward = (mid[0] - nx * offset_m, mid[1] - ny * offset_m)
    return outward


def place_templated_building(
    sim,
    shape: str,
    a: Point,
    b: Point,
    door: Point,
    *,
    height: float = STANDARD_BUILDING_HEIGHT,
    function: str = "domestic",
    phase_ids: Optional[Sequence[str]] = None,
    offset_m: float = 3.0,
    circle_segments: int = 24,
) -> Tuple[Building, object]:
    """Add a circle or rectangle building and its entrance OD.

    Parameters
    ----------
    shape:
        ``circle`` — ``a`` is the centre, ``b`` a rim point (radius = |b−a|).
        ``rect`` — ``a`` and ``b`` are opposite corners.
    door:
        A point near the intended facade; snapped to the nearest edge, then
        the OD is placed ``offset_m`` outside.
    """
    shape = (shape or "").lower()
    if shape in ("circle", "round", "oval"):
        radius = math.hypot(b[0] - a[0], b[1] - a[1])
        poly = circle_polygon(a[0], a[1], radius, n=circle_segments)
    elif shape in ("rect", "rectangle", "box"):
        poly = rect_polygon(a[0], a[1], b[0], b[1])
    else:
        raise ValueError(f"unknown building template: {shape}")

    if phase_ids is not None:
        phases = list(phase_ids)
    else:
        phases = []
        research = getattr(sim, "research", None)
        if research is not None:
            current = research.current_phase_ids()
            if current:
                phases = list(current)
    building = sim.add_building(
        poly, height=height, function=function, phase_ids=phases,
    )
    ex, ey = entrance_from_door(building, door[0], door[1], offset_m=offset_m)
    kind = "house" if function == "domestic" else (
        "special" if function == "special" else "house"
    )
    od_index = sim.add_od(
        ex, ey,
        origin_weight=0.2, dest_weight=1.0,
        name=f"entrance {building.function}",
        kind=kind, phase_ids=phases,
        tags=["entrance", "door", shape],
    )
    return building, sim.ods[od_index]

"""Small 2D geometry helpers used by the simulation.

Coordinates are plain planar (x, y) in world units (e.g. metres). These helpers
mirror the behaviour of the original Java ``MyMath`` utilities closely enough to
reproduce the same walkability rasterisation.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]
Polygon = Sequence[Point]


def polygon_bounds(poly: Polygon) -> Tuple[float, float, float, float]:
    """Return the axis-aligned bounding box ``(min_x, min_y, max_x, max_y)``."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def point_in_polygon(x: float, y: float, poly: Polygon) -> bool:
    """Even-odd ray-casting point-in-polygon test.

    This is a direct translation of the ``pointInPoly`` routine used by the
    original project so that grid rasterisation matches.
    """
    odd = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[j]
        if (ay < y <= by) or (by < y <= ay):
            if ax + (y - ay) / (by - ay) * (bx - ax) < x:
                odd = not odd
        j = i
    return odd


def rasterize_polygons_mask(
    polygons: Iterable[Polygon],
    xs: np.ndarray,
    ys: np.ndarray,
) -> np.ndarray:
    """Return a boolean mask ``[nx, ny]`` that is True where a cell centre falls
    inside *any* of the given polygons.

    ``xs`` and ``ys`` are the 1D arrays of cell-centre coordinates along each axis.
    A bounding-box pre-filter keeps this reasonably fast for modest grids.
    """
    nx = xs.shape[0]
    ny = ys.shape[0]
    mask = np.zeros((nx, ny), dtype=bool)
    for poly in polygons:
        if len(poly) < 3:
            continue
        min_x, min_y, max_x, max_y = polygon_bounds(poly)
        i_lo = int(np.searchsorted(xs, min_x, side="left"))
        i_hi = int(np.searchsorted(xs, max_x, side="right"))
        j_lo = int(np.searchsorted(ys, min_y, side="left"))
        j_hi = int(np.searchsorted(ys, max_y, side="right"))
        for i in range(max(0, i_lo), min(nx, i_hi + 1)):
            x = xs[i]
            for j in range(max(0, j_lo), min(ny, j_hi + 1)):
                if not mask[i, j] and point_in_polygon(x, ys[j], poly):
                    mask[i, j] = True
    return mask


def polygon_centroid(poly: Polygon) -> Point:
    """Area-weighted centroid of a simple polygon (falls back to vertex mean)."""
    n = len(poly)
    if n == 0:
        raise ValueError("empty polygon")
    if n < 3:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def polygon_area(poly: Polygon) -> float:
    """Signed polygon area (positive = counter-clockwise), mirroring ``MyMath.area``."""
    r = 0.0
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        r += ax * by - ay * bx
    return r / 2.0


def clockwise(poly: Polygon) -> int:
    """Return 1 for CCW, -1 for CW, 0 for degenerate (matches ``MyMath.clockWise``)."""
    c = polygon_area(poly)
    if c > 0:
        return 1
    if c < 0:
        return -1
    return 0


def ensure_clockwise(poly: List[Point]) -> List[Point]:
    """Return the polygon reordered so its winding is clockwise (as the Java
    ``fixPolygonVertexOrder`` does for building footprints)."""
    pts = list(poly)
    if clockwise(pts) == 1:  # CCW -> reverse
        pts.reverse()
    return pts


def line_segment_intersection(
    ax: float, ay: float, bx: float, by: float,
    cx: float, cy: float, dx: float, dy: float,
) -> Optional[Point]:
    """Intersection of segment A-B with segment C-D, or ``None``.

    Direct port of ``MyMath.lineSegmentIntersection`` (rotate-and-project method).
    """
    if (ax == bx and ay == by) or (cx == dx and cy == dy):
        return None
    bx -= ax
    by -= ay
    cx -= ax
    cy -= ay
    dx -= ax
    dy -= ay
    dist_ab = math.hypot(bx, by)
    if dist_ab == 0:
        return None
    the_cos = bx / dist_ab
    the_sin = by / dist_ab
    new_x = cx * the_cos + cy * the_sin
    cy = cy * the_cos - cx * the_sin
    cx = new_x
    new_x = dx * the_cos + dy * the_sin
    dy = dy * the_cos - dx * the_sin
    dx = new_x
    if (cy < 0 and dy < 0) or (cy >= 0 and dy >= 0):
        return None
    ab_pos = dx + (cx - dx) * dy / (dy - cy)
    if ab_pos < 0 or ab_pos > dist_ab:
        return None
    return (ax + ab_pos * the_cos, ay + ab_pos * the_sin)


def line_poly_intersections(
    vertices: Polygon, fx: float, fy: float, x: float, y: float
):
    """Return ``(intersections, edge_indices)`` where a segment (fx,fy)->(x,y)
    crosses polygon edges. ``edge_indices`` is ``[i0, i0+1, i1, i1+1]`` for up to
    two crossings, matching ``MyMath.LinePolyIntersectons`` (used for splitting).
    """
    intersections: List[Point] = []
    edge_index = [0, 0, 0, 0]
    n = len(vertices)
    for i in range(n):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % n]
        inter = line_segment_intersection(fx, fy, x, y, ax, ay, bx, by)
        if inter is not None:
            intersections.append(inter)
            if len(intersections) < 2:
                edge_index[0] = i
                edge_index[1] = i + 1
            else:
                edge_index[2] = i
                edge_index[3] = i + 1
    return intersections, edge_index


def split_polygon(verts: Polygon, intersections, edge_index):
    """Split ``verts`` into two polygons along a cut defined by two edge
    crossings. Port of ``MyMath.splitPolygon``. Requires two intersections."""
    inter1, inter2 = intersections[0], intersections[1]
    verts1: List[Point] = []
    verts2: List[Point] = []
    for j in range(edge_index[1]):
        verts1.append((verts[j][0], verts[j][1]))
    verts1.append((inter1[0], inter1[1]))
    verts1.append((inter2[0], inter2[1]))
    for j in range(edge_index[3], len(verts)):
        verts1.append((verts[j][0], verts[j][1]))

    verts2.append((inter1[0], inter1[1]))
    for j in range(edge_index[1], edge_index[3]):
        verts2.append((verts[j][0], verts[j][1]))
    verts2.append((inter2[0], inter2[1]))
    return verts1, verts2

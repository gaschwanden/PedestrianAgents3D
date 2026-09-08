"""Small 2D geometry helpers used by the simulation.

Coordinates are plain planar (x, y) in world units (e.g. metres). These helpers
mirror the behaviour of the original Java ``MyMath`` utilities closely enough to
reproduce the same walkability rasterisation.
"""
from __future__ import annotations

from typing import Iterable, Sequence, Tuple

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

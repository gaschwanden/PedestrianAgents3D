"""Isovist: the polygon of space visible from a point.

Port of the Java ``Isovist`` class. From an origin, cast a dense fan of rays
(0..2pi) and clip each against every opaque footprint edge (buildings,
obstacles, landmarks). ``WATERBODY`` and ``STREETS`` obstacle layers are
transparent, exactly as in the original. The result is the ordered list of
clipped ray end-points -- the visibility polygon.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .geometry import line_segment_intersection

TRANSPARENT_LAYERS = {"WATERBODY", "STREETS"}


class Isovist:
    def __init__(self, sim, x: float, y: float, ray_step: float = 0.05,
                 ray_length: Optional[float] = None):
        self.sim = sim
        self.ox = x
        self.oy = y
        self.ray_step = ray_step
        self.ray_length = ray_length
        self.rays: List[Tuple[float, float]] = []
        self.made = False

    def _opaque_polygons(self) -> List[Sequence[Tuple[float, float]]]:
        polys: List[Sequence[Tuple[float, float]]] = []
        for b in self.sim.buildings:
            if b.footprint.floor_z <= 1.1 and len(b.footprint.vertices) >= 2:
                polys.append(b.footprint.as_xy())
        for o in self.sim.obstacles:
            if o.layer in TRANSPARENT_LAYERS:
                continue
            if len(o.footprint.vertices) >= 2:
                polys.append(o.footprint.as_xy())
        for lm in getattr(self.sim, "landmarks", []):
            for fp in lm.footprints:
                polys.append([(v[0], v[1]) for v in fp])
        return polys

    def make(self) -> "Isovist":
        g = self.sim.grid
        length = self.ray_length
        if length is None:
            length = 100.0 * max(g.max_x - g.min_x, g.max_y - g.min_y)
        polys = self._opaque_polygons()
        self.rays = []
        j = 0.0
        while j < 2 * math.pi:
            rx = self.ox + length * math.cos(j)
            ry = self.oy + length * math.sin(j)
            # clip against every edge, keeping the nearest hit
            for poly in polys:
                np_ = len(poly)
                # bounding-box quick reject
                pxs = [p[0] for p in poly]
                pys = [p[1] for p in poly]
                if self.ox > max(pxs) and rx > max(pxs):
                    continue
                if self.oy > max(pys) and ry > max(pys):
                    continue
                if self.ox < min(pxs) and rx < min(pxs):
                    continue
                if self.oy < min(pys) and ry < min(pys):
                    continue
                for k in range(np_):
                    ax, ay = poly[k]
                    bx, by = poly[(k + 1) % np_]
                    inter = line_segment_intersection(self.ox, self.oy, rx, ry, ax, ay, bx, by)
                    if inter is not None:
                        rx, ry = inter
            self.rays.append((rx, ry))
            j += self.ray_step
        self.made = True
        return self

    def polygon(self) -> List[Tuple[float, float]]:
        return list(self.rays)

    def area(self) -> float:
        pts = self.rays
        a = 0.0
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            a += x0 * y1 - x1 * y0
        return abs(a) / 2.0

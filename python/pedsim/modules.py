"""Reusable prefab *modules* (port of the Java ``Module`` class).

A module is a small piece of geometry (outline polygons plus a ``FOOTPRINT``
polygon) that can be instantiated at a point, rotated (with 90° snapping), and
snapped onto the site's insertion points. Placed modules can act as buildings.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]


class ModulePrototype:
    """A library module: outline polygons + footprint polygons, centred on 0,0."""

    def __init__(self, outlines: Sequence[Sequence[Point]],
                 footprints: Sequence[Sequence[Point]]):
        self.outlines = [list(p) for p in outlines]
        self.footprints = [list(p) for p in footprints]
        self._centre()

    @classmethod
    def from_dxf(cls, dxf) -> "ModulePrototype":
        outlines = []
        footprints = []
        for poly in dxf.polys:
            ring = [(v[0], v[1]) for v in poly.vertices]
            if poly.layer == "FOOTPRINT":
                footprints.append(ring)
            else:
                outlines.append(ring)
        for poly in dxf.lwpolys:
            ring = [(v[0], v[1]) for v in poly.vertices]
            if poly.layer == "FOOTPRINT":
                footprints.append(ring)
            else:
                outlines.append(ring)
        return cls(outlines, footprints)

    def _centre(self) -> None:
        pts = [p for poly in (self.outlines + self.footprints) for p in poly]
        if not pts:
            return
        minx = min(p[0] for p in pts)
        maxx = max(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        maxy = max(p[1] for p in pts)
        mx = minx + (maxx - minx) / 2.0
        my = miny + (maxy - miny) / 2.0
        self.outlines = [[(x - mx, y - my) for x, y in poly] for poly in self.outlines]
        self.footprints = [[(x - mx, y - my) for x, y in poly] for poly in self.footprints]


class PlacedModule:
    """An instance of a :class:`ModulePrototype` positioned in the scene."""

    def __init__(self, prototype: ModulePrototype, x: float, y: float, z: float = 0.0):
        self.prototype = prototype
        self.x = x
        self.y = y
        self.z = z
        self.rotation = 0.0

    def _transform(self, poly: Sequence[Point]) -> List[Point]:
        ca, sa = math.cos(self.rotation), math.sin(self.rotation)
        return [(self.x + px * ca - py * sa, self.y + px * sa + py * ca) for px, py in poly]

    def footprints_world(self) -> List[List[Point]]:
        return [self._transform(fp) for fp in self.prototype.footprints]

    def outlines_world(self) -> List[List[Point]]:
        return [self._transform(o) for o in self.prototype.outlines]

    def rotate_to(self, angle: float, snap_tol: float = 0.1) -> None:
        self.rotation = angle
        rot = self.rotation % (2 * math.pi)
        for target in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            if abs(rot - target) < snap_tol:
                self.rotation = target
                break

    def rotate_by(self, delta: float, snap_tol: float = 0.1) -> None:
        self.rotate_to(self.rotation + delta, snap_tol)

    def snap(self, insertion_points: Sequence[Point], snap_dist: float = 5000.0) -> bool:
        for sx, sy in insertion_points:
            if abs(sx - self.x) < snap_dist and abs(sy - self.y) < snap_dist:
                self.x, self.y = sx, sy
                return True
        return False

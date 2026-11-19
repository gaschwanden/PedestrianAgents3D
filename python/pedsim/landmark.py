"""Landmarks (port of the Java ``Landmark`` class).

A landmark carries display polylines (``LANDMARK_LINES``) and one or more
``FOOTPRINT`` polygons used as opaque geometry for the isovist. Landmarks do not
block pedestrian movement in the original model; they only occlude sight-lines.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

Point = Tuple[float, float]


class Landmark:
    def __init__(self, name: str = ""):
        self.name = name
        self.lines: List[Tuple[Point, Point]] = []
        self.footprints: List[List[Tuple[float, float, float]]] = []

    @classmethod
    def from_dxf(cls, dxf, name: str = "") -> "Landmark":
        lm = cls(name=name)
        for line in dxf.lines:
            if line.layer == "LANDMARK_LINES":
                lm.lines.append(((line.x1, line.y1), (line.x2, line.y2)))
        for poly in dxf.lwpolys:
            if poly.layer == "FOOTPRINT":
                lm.footprints.append([(v[0], v[1], v[2]) for v in poly.vertices])
        for poly in dxf.polys:
            if poly.layer == "FOOTPRINT":
                lm.footprints.append([(v[0], v[1], v[2]) for v in poly.vertices])
        return lm

    def move(self, dx: float, dy: float) -> None:
        self.lines = [((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)) for a, b in self.lines]
        self.footprints = [[(x + dx, y + dy, z) for x, y, z in fp] for fp in self.footprints]

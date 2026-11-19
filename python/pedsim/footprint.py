"""Building/obstacle footprint: a polygon plus the facade-segmentation used by
the facade-visibility analysis.

Port of the Java ``Footprint`` class. ``gridded_segments`` splits every facade
edge at the navigation-grid lines and records, for each little segment, the grid
cell it passes through -- the facade-visibility display colours each segment by
that cell's accumulated visibility.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .geometry import point_in_polygon

Point3 = List[float]


class Footprint:
    def __init__(self, thinning_tol: float = 0.01):
        self.vertices: List[Point3] = []
        self.thinning_tol = thinning_tol
        self.min_x = self.min_y = float("inf")
        self.max_x = self.max_y = float("-inf")
        # Facade segmentation (filled by gridded_segments):
        self.seg_points: List[List[Tuple[float, float]]] = []
        self.seg_pixrefs: List[List[Tuple[int, int]]] = []
        self.needs_update_segments = True

    def add_vertex(self, x: float, y: float, z: float = 0.0) -> None:
        if self.vertices:
            lx, ly, _ = self.vertices[-1]
            if abs(lx - x) < self.thinning_tol and abs(ly - y) < self.thinning_tol:
                return
            fx, fy, _ = self.vertices[0]
            if abs(fx - x) < self.thinning_tol and abs(fy - y) < self.thinning_tol:
                return
        self.vertices.append([x, y, z])
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def set_vertices(self, verts: List[Point3]) -> None:
        self.vertices = [list(v) if len(v) == 3 else [v[0], v[1], 0.0] for v in verts]
        self.set_bounding_rectangle()

    def set_bounding_rectangle(self) -> None:
        if not self.vertices:
            return
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)

    def as_xy(self) -> List[Tuple[float, float]]:
        return [(v[0], v[1]) for v in self.vertices]

    @property
    def floor_z(self) -> float:
        return self.vertices[0][2] if self.vertices else 0.0

    def contains(self, x: float, y: float) -> bool:
        if x < self.min_x or y < self.min_y or x > self.max_x or y > self.max_y:
            return False
        return point_in_polygon(x, y, self.as_xy())

    def move(self, dx: float, dy: float, dz: float = 0.0) -> None:
        for v in self.vertices:
            v[0] += dx
            v[1] += dy
            v[2] += dz
        for seg in self.seg_points:
            for k in range(len(seg)):
                sx, sy = seg[k]
                seg[k] = (sx + dx, sy + dy)
        self.set_bounding_rectangle()

    def gridded_segments(self, grid) -> None:
        """Split each edge at grid lines; record the grid cell each sub-segment
        passes through. Port of ``Footprint.calculateGriddedSegments``."""
        self.needs_update_segments = False
        n = len(self.vertices)
        self.seg_points = [[] for _ in range(n)]
        self.seg_pixrefs = [[] for _ in range(n)]
        gsize = grid.gridsize
        for i in range(n):
            a = (self.vertices[i][0], self.vertices[i][1])
            b = (self.vertices[(i + 1) % n][0], self.vertices[(i + 1) % n][1])
            segpoints: List[Tuple[float, float]] = [a, b]

            # crossings of vertical grid lines (constant x)
            if a[0] < b[0]:
                start, end = a, b
            else:
                start, end = b, a
            dirx = end[0] - start[0]
            diry = end[1] - start[1]
            if dirx != 0:
                minfieldx = grid.cell_x(start[0])
                xx = (grid.sx + minfieldx * gsize + gsize / 2.0)
                if xx <= start[0]:
                    xx += gsize
                while xx < end[0]:
                    t = (xx - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
                    yy = a[1] + t * (b[1] - a[1])
                    segpoints.append((xx, yy))
                    xx += gsize

            # crossings of horizontal grid lines (constant y)
            if a[1] < b[1]:
                start, end = a, b
            else:
                start, end = b, a
            if (end[1] - start[1]) != 0:
                minfieldy = grid.cell_y(start[1])
                yy = (grid.sy + minfieldy * gsize + gsize / 2.0)
                if yy <= start[1]:
                    yy += gsize
                while yy < end[1]:
                    t = (yy - a[1]) / (b[1] - a[1]) if b[1] != a[1] else 0.0
                    xx = a[0] + t * (b[0] - a[0])
                    segpoints.append((xx, yy))
                    yy += gsize

            # order the sub-segment points along the edge
            if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
                segpoints = [a] + sorted(segpoints[2:], key=lambda p: p[0]) + [b] if a[0] < b[0] \
                    else [a] + sorted(segpoints[2:], key=lambda p: -p[0]) + [b]
            else:
                segpoints = [a] + sorted(segpoints[2:], key=lambda p: p[1]) + [b] if a[1] < b[1] \
                    else [a] + sorted(segpoints[2:], key=lambda p: -p[1]) + [b]

            pixels: List[Tuple[int, int]] = []
            for k in range(1, len(segpoints)):
                p0 = segpoints[k - 1]
                p1 = segpoints[k]
                px = grid.cell_x(p0[0] + (p1[0] - p0[0]) / 2.0)
                py = grid.cell_y(p0[1] + (p1[1] - p0[1]) / 2.0)
                pixels.append((px, py))
            self.seg_pixrefs[i] = pixels
            self.seg_points[i] = segpoints

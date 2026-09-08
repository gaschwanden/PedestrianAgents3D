"""Building / obstacle: an extruded footprint.

Port of the Java ``Building`` class. A building has a footprint polygon, a
height (extrusion), a ``kind`` ("building" or "obstacle") and a DXF ``layer``
(e.g. ``OBSTACLES_LOW``, ``WATERBODY``, ``STREETS``, ``PARK``) that controls how
it renders and whether the isovist treats it as opaque.
"""
from __future__ import annotations

from typing import List, Tuple

from .footprint import Footprint
from .geometry import clockwise


class Building:
    def __init__(self, kind: str = "building", layer: str = "", height: float = 15.0,
                 num_floors: int = 1):
        self.footprint = Footprint()
        self.kind = kind
        self.layer = layer
        self.num_floors = num_floors
        self.height = height
        self.vertex_dragged = False

    @classmethod
    def from_polygon(cls, poly, kind: str = "building", layer: str = "",
                     height: float = 15.0) -> "Building":
        b = cls(kind=kind, layer=layer, height=height)
        for v in poly:
            z = v[2] if len(v) > 2 else 0.0
            b.footprint.add_vertex(v[0], v[1], z)
        b.fix_vertex_order()
        return b

    def copy(self) -> "Building":
        b = Building(self.kind, self.layer, self.height, self.num_floors)
        return b

    def fix_vertex_order(self) -> None:
        """Ensure the footprint is wound clockwise (Java ``fixPolygonVertexOrder``)."""
        if clockwise(self.footprint.as_xy()) == 1:  # CCW -> reverse
            self.footprint.vertices.reverse()

    def move(self, dx: float, dy: float, dz: float = 0.0) -> None:
        self.footprint.move(dx, dy, dz)

    def contains(self, x: float, y: float) -> bool:
        return self.footprint.contains(x, y)

    @property
    def on_ground(self) -> bool:
        """Only footprints resting on the ground block movement (threshold 1.5,
        as in the Java ``pointObstructed``)."""
        return self.footprint.floor_z <= 1.5

    def bbox(self) -> Tuple[float, float, float, float]:
        f = self.footprint
        return f.min_x, f.min_y, f.max_x, f.max_y

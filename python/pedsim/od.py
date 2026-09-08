"""Origin / Destination points.

An :class:`OD` is a place where pedestrians can be generated (a *source*) and/or
where they travel to (a *sink*). Each OD carries an origin weight and a
destination weight, exactly like the ``OD`` class in the original project:

* ``origin_weight`` -- relative probability of being chosen as a trip origin.
* ``dest_weight``   -- relative probability of being chosen as a trip destination.

Setting ``origin_weight`` to 0 turns a place into a pure sink; setting
``dest_weight`` to 0 turns it into a pure source.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OD:
    x: float
    y: float
    z: float = 0.0
    group: int = 0
    origin_weight: float = 1.0
    dest_weight: float = 1.0
    name: str = ""

    @property
    def is_source(self) -> bool:
        return self.origin_weight > 0

    @property
    def is_sink(self) -> bool:
        return self.dest_weight > 0

    def to_line(self) -> str:
        """Serialise to the ``OD,x,y,z,ow,dw,group`` text format used by the
        original tool (so files are interchangeable)."""
        return (
            f"OD,{self.x},{self.y},{self.z},"
            f"{self.origin_weight},{self.dest_weight},{self.group}"
        )

    @classmethod
    def from_line(cls, line: str) -> "OD | None":
        parts = [p.strip() for p in line.strip().split(",")]
        if not parts or parts[0] != "OD" or len(parts) < 6:
            return None
        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        ow, dw = float(parts[4]), float(parts[5])
        group = int(parts[6]) if len(parts) > 6 else 0
        return cls(x=x, y=y, z=z, group=group, origin_weight=ow, dest_weight=dw)

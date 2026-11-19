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

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OD:
    x: float
    y: float
    z: float = 0.0
    group: int = 0
    origin_weight: float = 1.0
    dest_weight: float = 1.0
    name: str = ""
    #: Catalogue site this place belongs to (cluster ODs). Empty at village scale.
    site: str = ""
    #: Empty means the OD belongs to every phase (older saves).
    phase_ids: List[str] = field(default_factory=list)
    #: gate / house / water / quarry / resource / site / gathering, or a
    #: qualified form such as ``quarry:chert`` or ``resource:plants``.
    kind: str = "site"
    capacity: Optional[float] = None
    tags: List[str] = field(default_factory=list)

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

    def to_dict(self) -> dict:
        """JSON form. The text line (``to_line``) stays the Java-compatible subset."""
        return {
            "x": self.x, "y": self.y, "z": self.z, "group": self.group,
            "origin_weight": self.origin_weight, "dest_weight": self.dest_weight,
            "name": self.name, "site": self.site, "phase_ids": list(self.phase_ids),
            "kind": self.kind, "capacity": self.capacity, "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OD":
        return cls(
            x=float(data["x"]), y=float(data["y"]), z=float(data.get("z", 0.0)),
            group=int(data.get("group", 0)),
            origin_weight=float(data.get("origin_weight", 1.0)),
            dest_weight=float(data.get("dest_weight", 1.0)),
            name=data.get("name", ""),
            site=data.get("site", ""),
            phase_ids=list(data.get("phase_ids") or []),
            kind=data.get("kind", "site"),
            capacity=data.get("capacity"),
            tags=list(data.get("tags") or []),
        )

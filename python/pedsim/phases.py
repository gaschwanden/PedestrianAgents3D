"""Building phases: named periods that can be switched, and that own ODs
and inhabitants.

An element with an empty ``phase_ids`` list belongs to every phase, which is
how a geometry saved before phases were added keeps its old behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .chronology import Interval


@dataclass
class Phase:
    id: str
    name: str
    start_bc: int
    end_bc: int
    source: str = ""
    confidence: str = "assumption"   # published / inferred / assumption
    colour: str = "#888888"
    state: str = ""                  # optional default state note

    @property
    def interval(self) -> Interval:
        return Interval(int(self.end_bc), int(self.start_bc))

    @property
    def assumption(self) -> bool:
        return (not self.source) or self.confidence == "assumption"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "start_bc": self.start_bc, "end_bc": self.end_bc,
            "source": self.source, "confidence": self.confidence,
            "colour": self.colour,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Phase":
        if "id" not in data:
            raise ValueError("phase is missing id")
        if data.get("start_bc") is None or data.get("end_bc") is None:
            raise ValueError(f"phase {data.get('id')!r} is missing start_bc/end_bc")
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            start_bc=int(data["start_bc"]),
            end_bc=int(data["end_bc"]),
            source=str(data.get("source", "")),
            confidence=str(data.get("confidence", "assumption")),
            colour=str(data.get("colour", data.get("color", "#888888"))),
        )


def polygon_area(points: Sequence[Tuple[float, float]]) -> float:
    """Absolute shoelace area of a ring. Units follow the coordinates."""
    if len(points) < 3:
        return 0.0
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(points, list(points[1:]) + [points[0]]):
        acc += x0 * y1 - x1 * y0
    return abs(acc) * 0.5


def phase_active(phase: Phase, window: Interval, override: str = "") -> bool:
    """``by_time`` rule: on when the phase interval meets the window.

    ``override`` ``on`` / ``off`` wins, and is what the HUD calls an override.
    """
    if override == "off":
        return False
    if override == "on":
        return True
    return phase.interval.overlaps(window)


def active_ids(phases: Sequence[Phase], mode: str, window: Optional[Interval],
               manual: Optional[Iterable[str]] = None,
               overrides: Optional[Dict[str, str]] = None) -> List[str]:
    """Ids that are on. ``manual`` is the explicit set when ``mode == 'manual'``."""
    overrides = overrides or {}
    if mode == "by_time":
        if window is None:
            raise ValueError("by_time phase mode needs a time window")
        return [p.id for p in phases if phase_active(p, window, overrides.get(p.id, ""))]
    if manual is None:
        return [p.id for p in phases]
    return [i for i in manual if any(p.id == i for p in phases)]


def member_on(phase_ids: Sequence[str], active: Optional[Iterable[str]]) -> bool:
    """Empty membership belongs to every phase. ``active is None`` means all on."""
    if not phase_ids:
        return True
    if active is None:
        return True
    live = set(active)
    return any(pid in live for pid in phase_ids)


def inhabitants(buildings: Sequence, active: Optional[Iterable[str]] = None,
                rule: str = "per_house", persons_per_house: float = 5.0,
                persons_per_m2: float = 0.1) -> float:
    """Sum of people in active domestic buildings.

    ``persons_per_house`` (default 5) and ``persons_per_m2`` (default 0.1, i.e.
    one person per 10 m²) are both ``ASSUMPTION``. A building's own
    ``inhabitants`` overrides the rule. Non-domestic buildings contribute 0.
    """
    total = 0.0
    for b in buildings:
        if getattr(b, "function", "unknown") != "domestic":
            continue
        if not member_on(getattr(b, "phase_ids", []), active):
            continue
        if getattr(b, "state", "standing") == "backfilled":
            continue
        override = getattr(b, "inhabitants", None)
        if override is not None:
            total += float(override)
            continue
        if rule == "per_m2":
            total += polygon_area(b.footprint.as_xy()) * float(persons_per_m2)
        else:
            total += float(persons_per_house)
    return total


def entrance_point(building, offset_m: float = 3.0) -> Tuple[float, float]:
    """A point just outside the longest facade, for an auto-generated door OD."""
    pts = list(building.footprint.as_xy())
    if len(pts) < 2:
        raise ValueError("building has no facade")
    ring = pts + [pts[0]]
    best = None
    best_len = -1.0
    for a, b in zip(ring, ring[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length > best_len:
            best_len = length
            best = (a, b, dx, dy, length)
    a, b, dx, dy, length = best
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    if length <= 0:
        return mid
    nx, ny = -dy / length, dx / length
    outward = (mid[0] + nx * offset_m, mid[1] + ny * offset_m)
    if building.contains(outward[0], outward[1]):
        outward = (mid[0] - nx * offset_m, mid[1] - ny * offset_m)
    return outward


def auto_entrances(buildings: Sequence, active: Optional[Iterable[str]] = None,
                   offset_m: float = 3.0) -> List[dict]:
    """One entrance OD per active building, inheriting its phases and function."""
    out = []
    for b in buildings:
        if not member_on(getattr(b, "phase_ids", []), active):
            continue
        if len(b.footprint.as_xy()) < 3:
            continue
        x, y = entrance_point(b, offset_m)
        kind = "house" if getattr(b, "function", "") == "domestic" else (
            "special" if getattr(b, "function", "") == "special" else "house"
        )
        out.append({
            "x": x, "y": y, "kind": kind,
            "phase_ids": list(getattr(b, "phase_ids", [])),
            "name": f"entrance {kind}",
        })
    return out


def migrate_geometry(data: dict) -> dict:
    """Fill fields added in geometry format 3. Missing ``phase_ids`` -> all phases.

    The returned dict is a shallow copy; nested building dicts are copied so
    the caller's object is not mutated.
    """
    out = dict(data)
    out.setdefault("format", 2)
    out.setdefault("phases", [])
    out.setdefault("population", {})
    out.setdefault("scenario_ref", "")

    def _elems(key: str) -> List[dict]:
        copied = []
        for item in data.get(key, []):
            e = dict(item)
            e.setdefault("phase_ids", [])
            if key == "buildings":
                e.setdefault("function", "unknown")
                e.setdefault("inhabitants", None)
                e.setdefault("state", "standing")
            if key == "obstacles":
                e.setdefault("state", "standing")
            copied.append(e)
        return copied

    out["buildings"] = _elems("buildings")
    out["obstacles"] = _elems("obstacles")
    return out

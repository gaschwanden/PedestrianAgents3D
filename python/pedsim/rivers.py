"""Rivers as seasonal landscape features.

At the settlement-cluster scale water is the dominant control on where people
walk, and it cuts both ways: a river is an **obstacle** to cross and an
**attractor** to follow. Which of the two dominates changes with the season --
most watercourses in the Şanlıurfa steppe are seasonal, so the same channel is
a dry, walkable bed in late summer, a costly wade at normal flow, and an
impassable barrier during the spring melt.

A :class:`River` is therefore a centreline plus a behaviour, not a fixed mask.
It rasterises into layers on demand for a given :class:`Season`:

* the **channel** adds crossing cost (or blocks outright when in flood),
* **fords** are cheap gaps in the channel -- the places traffic funnels through,
* a **bank corridor** *reduces* friction, so routes hug the water where going
  along the river is as useful as getting across it.

Nothing here reconstructs palaeo-channels: nobody has mapped those for the
Culap or the Mucid at 10 ka (see :mod:`pedsim.paleo`). Rivers keep their modern
planform and only their *behaviour* is modelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .layers import BLOCK, FRICTION, Layer

Point = Tuple[float, float]


class Season(str, Enum):
    """The three states that matter for a seasonal watercourse."""

    DRY = "dry"                    # late summer: seasonal beds walkable
    NORMAL = "normal"              # average flow: costly to wade, fords useful
    SPRING_FLOOD = "spring floods"  # snowmelt: channels impassable, fords gone

    @property
    def label(self) -> str:
        return self.value

    def next(self) -> "Season":
        order = list(Season)
        return order[(order.index(self) + 1) % len(order)]


#: Per-season multiplier on a river's crossing cost, and whether it blocks.
#: Seasonal (non-perennial) courses dry out completely; perennial ones drop to a
#: fraction of their normal cost but never disappear.
SEASON_EFFECT: Dict[Season, Dict[str, float]] = {
    Season.DRY: {"perennial": 0.4, "seasonal": 0.0, "blocks": 0.0},
    Season.NORMAL: {"perennial": 1.0, "seasonal": 0.7, "blocks": 0.0},
    Season.SPRING_FLOOD: {"perennial": 1.0, "seasonal": 1.0, "blocks": 1.0},
}


@dataclass
class River:
    """A watercourse defined by its centreline.

    Parameters
    ----------
    path:
        Centreline vertices in world coordinates. Drawn by the viewer's
        *add river* tool, or imported from hydrography.
    width:
        Channel width in metres. Cells within ``width/2`` of the centreline are
        the channel.
    perennial:
        ``True`` for year-round flow, ``False`` for a seasonal wadi that dries
        to a walkable bed (the normal case in this landscape).
    crossing_cost:
        Friction *added* in the channel at normal flow. 4.0 means a channel cell
        costs about five times an open one to cross.
    attraction:
        Friction *removed* in the bank corridor, as a fraction. 0.3 makes
        walking along the bank noticeably easier than open country, which is how
        a water source shapes routes without being a destination.
    bank_width:
        Width of that corridor on each side, in metres.
    fords:
        Points where the channel is crossable cheaply. ``ford_cost_frac`` of the
        normal crossing cost applies within ``ford_radius``.
    """

    name: str
    path: List[Point]
    width: float = 20.0
    perennial: bool = False
    crossing_cost: float = 4.0
    attraction: float = 0.3
    bank_width: float = 40.0
    fords: List[Point] = field(default_factory=list)
    ford_radius: float = 30.0
    ford_cost_frac: float = 0.1
    phase_ids: List[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "perennial" if self.perennial else "seasonal"

    def effect(self, season: Season) -> Tuple[float, bool]:
        """``(cost_multiplier, blocks)`` for this river in ``season``."""
        eff = SEASON_EFFECT[season]
        mult = eff[self.kind]
        return mult, bool(eff["blocks"]) and mult > 0.0

    def as_xy(self) -> List[Point]:
        return list(self.path)

    def length(self) -> float:
        return float(sum(np.hypot(b[0] - a[0], b[1] - a[1])
                         for a, b in zip(self.path, self.path[1:])))

    def to_dict(self) -> dict:
        return {
            "name": self.name, "path": [list(p) for p in self.path],
            "width": self.width, "perennial": self.perennial,
            "crossing_cost": self.crossing_cost, "attraction": self.attraction,
            "bank_width": self.bank_width, "fords": [list(p) for p in self.fords],
            "ford_radius": self.ford_radius, "ford_cost_frac": self.ford_cost_frac,
            "phase_ids": list(self.phase_ids),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "River":
        return cls(
            name=d.get("name", "river"),
            path=[tuple(p) for p in d.get("path", [])],
            width=d.get("width", 20.0),
            perennial=d.get("perennial", False),
            crossing_cost=d.get("crossing_cost", 4.0),
            attraction=d.get("attraction", 0.3),
            bank_width=d.get("bank_width", 40.0),
            fords=[tuple(p) for p in d.get("fords", [])],
            ford_radius=d.get("ford_radius", 30.0),
            ford_cost_frac=d.get("ford_cost_frac", 0.1),
            phase_ids=list(d.get("phase_ids") or []),
        )


def distance_field(xs: np.ndarray, ys: np.ndarray, path: Sequence[Point]) -> np.ndarray:
    """Distance from every grid cell centre to a polyline, as ``[nx, ny]``."""
    X, Y = np.meshgrid(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float),
                       indexing="ij")
    if len(path) == 0:
        return np.full(X.shape, np.inf)
    if len(path) == 1:
        return np.hypot(X - path[0][0], Y - path[0][1])
    best = np.full(X.shape, np.inf)
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 <= 0:
            d = np.hypot(X - x0, Y - y0)
        else:
            t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0.0, 1.0)
            d = np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy))
        np.minimum(best, d, out=best)
    return best


def _point_distance(xs: np.ndarray, ys: np.ndarray, pts: Sequence[Point]) -> np.ndarray:
    X, Y = np.meshgrid(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float),
                       indexing="ij")
    best = np.full(X.shape, np.inf)
    for px, py in pts:
        np.minimum(best, np.hypot(X - px, Y - py), out=best)
    return best


def build_layers(xs: np.ndarray, ys: np.ndarray, rivers: Sequence[River],
                 season: Season = Season.NORMAL) -> List[Layer]:
    """Rasterise ``rivers`` into layers for ``season``.

    Returns at most two layers, so the interface stays legible however many
    rivers there are:

    * ``"rivers"`` -- friction. Positive in the channels (scaled by season,
      discounted at fords), negative in the bank corridors where water draws
      traffic along it.
    * ``"flood"`` -- a block layer, present only when something is in flood.

    An empty list means the rivers have no effect in this season (every course
    dry), which is itself a meaningful answer.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    shape = (xs.shape[0], ys.shape[0])
    cost = np.zeros(shape, dtype=float)
    blocked = np.zeros(shape, dtype=bool)
    any_cost = False

    for r in rivers:
        if len(r.path) < 1:
            continue
        mult, blocks = r.effect(season)
        if mult <= 0.0:
            continue                      # dry bed: no cost, no attraction
        d = distance_field(xs, ys, r.path)
        half = max(r.width / 2.0, 1e-6)
        channel = d <= half
        if not channel.any():
            continue

        if blocks:
            blocked |= channel
            continue                      # in flood, cost is irrelevant

        # channel cost, discounted where there is a ford
        c = np.zeros(shape, dtype=float)
        c[channel] = r.crossing_cost * mult
        if r.fords:
            fd = _point_distance(xs, ys, r.fords)
            at_ford = channel & (fd <= r.ford_radius)
            c[at_ford] = r.crossing_cost * mult * r.ford_cost_frac
        # bank corridor: negative cost, i.e. easier going alongside the water
        if r.attraction > 0.0 and r.bank_width > 0.0:
            bank = (~channel) & (d <= half + r.bank_width)
            c[bank] = -r.attraction * mult
        cost = np.where(np.abs(c) > np.abs(cost), c, cost)
        any_cost = True

    out: List[Layer] = []
    if any_cost:
        out.append(Layer("rivers", cost, weight=1.0, kind=FRICTION,
                         color=(80, 150, 255),
                         description="channel crossing cost, fords, bank attraction"))
    if blocked.any():
        out.append(Layer("flood", blocked.astype(float), weight=1.0, kind=BLOCK,
                         color=(60, 110, 230),
                         description="channels impassable at this season"))
    return out


def summarise(rivers: Sequence[River], season: Season) -> str:
    """One-line description of what the rivers are doing this season."""
    if not rivers:
        return f"{season.label}: no rivers"
    blocking = [r.name for r in rivers if r.effect(season)[1]]
    dry = [r.name for r in rivers if r.effect(season)[0] <= 0.0]
    bits = [f"{len(rivers)} river(s)"]
    if blocking:
        bits.append(f"{len(blocking)} impassable")
    if dry:
        bits.append(f"{len(dry)} dry")
    return f"{season.label}: " + ", ".join(bits)

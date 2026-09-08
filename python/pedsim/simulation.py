"""Top-level simulation: the Python counterpart of ``Scene`` + ``Grid_Thread``.

It owns the navigation grid, the list of origin/destination places, and the
pool of pedestrian agents, and advances everything one tick at a time.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .agent import Agent
from .geometry import Polygon
from .grid import NavGrid
from .od import OD
from .topography import TerrainCost, Topography
from .weighted import weighted_draw


class Simulation:
    def __init__(
        self,
        bounds: Tuple[float, float, float, float],
        ods: Sequence[OD],
        gridsize: float = 4.0,
        buildings: Optional[Sequence[Polygon]] = None,
        obstacles: Optional[Sequence[Polygon]] = None,
        site_polygon: Optional[Polygon] = None,
        topography: Optional[Topography] = None,
        terrain_cost: Optional[TerrainCost] = None,
        num_agents: int = 300,
        release_rate: int = 20,
        speed: float = 0.5,
        cone_vision: int = 100,
        radius_divider: float = math.pi / 10.0,
        blur_occupancy: bool = True,
        blur_decay: float = 0.5,
        trace_percent: float = 10.0,
        seed: Optional[int] = None,
    ):
        self.ods: List[OD] = list(ods)
        self.num_agents = num_agents
        self.release_rate = release_rate
        self.speed = speed
        self.cone_vision = cone_vision
        self.radius_divider = radius_divider
        self.blur_occupancy = blur_occupancy
        self.blur_decay = blur_decay
        self.trace_percent = trace_percent
        self.rng = np.random.default_rng(seed)

        self.grid = NavGrid(
            bounds=bounds,
            gridsize=gridsize,
            buildings=buildings,
            obstacles=obstacles,
            site_polygon=site_polygon,
            topography=topography,
            terrain_cost=terrain_cost,
        )

        self.agents: List[Agent] = [Agent(self) for _ in range(num_agents)]
        self.running = True
        self.ticks = 0
        self._build_cost_fields()

    # ---------------------------------------------------------------- factory
    @classmethod
    def from_site(cls, site, gridsize: float = 4.0, **kwargs) -> "Simulation":
        """Build a simulation directly from an :class:`~pedsim.importers.ArchaeologicalSite`."""
        return cls(
            bounds=site.bounds(),
            ods=site.build_ods(),
            gridsize=gridsize,
            buildings=site.building_polygons(),
            obstacles=site.obstacle_polygons(),
            site_polygon=site.boundary,
            **kwargs,
        )

    # ------------------------------------------------------------ cost fields
    def _build_cost_fields(self) -> None:
        """(Re)compute the flood-fill / cost-to-destination field for every OD."""
        self.grid.clear_cost_fields()
        for k, od in enumerate(self.ods):
            self.grid.compute_cost_field(k, od.x, od.y)

    def reachable_targets(self) -> int:
        return sum(1 for od in self.ods if od is not None)

    # -------------------------------------------------------------- trip draw
    def draw_trip(self) -> Optional[Tuple[int, int]]:
        """Pick an (origin, destination) index pair by weighted random draw."""
        if len(self.ods) < 2:
            return None
        ow = [od.origin_weight for od in self.ods]
        dw = [od.dest_weight for od in self.ods]
        o = weighted_draw(ow, self.rng)
        if o == -1:
            return None
        d = weighted_draw(dw, self.rng, ignore_index=o)
        if d == -1:
            return None
        return o, d

    def weighted_index(self, weights: Sequence[float]) -> int:
        return weighted_draw(weights, self.rng)

    # ------------------------------------------------------------- agent pool
    def release_agents(self) -> int:
        """Activate up to ``release_rate`` idle agents, mirroring the gradual
        release used by the original background thread."""
        if self.reachable_targets() < 2:
            return 0
        released = 0
        for a in self.agents:
            if not a.active:
                if a.renew():
                    released += 1
                if released >= self.release_rate:
                    break
        return released

    @property
    def active_agents(self) -> List[Agent]:
        return [a for a in self.agents if a.active]

    # -------------------------------------------------------------------- step
    def step(self) -> None:
        """Advance the simulation by one tick.

        Order matches the original render loop: vision first (sets each agent's
        far-pixel waypoint from the flood-fill), then movement, then occupancy
        and arrival checks, then release new agents and decay the heat map.
        """
        for a in self.agents:
            if a.active:
                a.vision_scan()

        for a in self.agents:
            if not a.active:
                continue
            a.set_dir_to_target()
            if not a.active:
                continue
            a.move()
            a.mark_occupancy()
            a.target_check()

        self.release_agents()
        self.grid.decay_occupancy()
        self.ticks += 1

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    # --------------------------------------------------------------- snapshot
    def agent_positions_world(self) -> np.ndarray:
        """Return an ``(n, 2)`` array of active-agent positions in world units."""
        pts = []
        for a in self.active_agents:
            pts.append((self.grid.world_x(a.px), self.grid.world_y(a.py)))
        return np.array(pts, dtype=float) if pts else np.empty((0, 2))

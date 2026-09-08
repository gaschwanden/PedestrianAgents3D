"""The navigation grid: walkability rasterisation and cost-to-destination fields.

This is the Python counterpart of the Java ``Grid`` / ``Grid_Thread`` pair.

* Walkability is rasterised from the site boundary (inside = allowed) minus the
  building and obstacle footprints (inside = blocked), exactly as before.
* Instead of the original uniform-cost BFS flood fill, the cost-to-destination
  field is computed with Dijkstra so it can honour a slope-dependent
  :class:`~pedsim.topography.TerrainCost`. On flat terrain (no topography) the
  step cost is just the Euclidean step length, which reproduces straight-line
  least-distance routing.
"""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .geometry import Polygon, point_in_polygon, rasterize_polygons_mask
from .topography import TerrainCost, Topography

# 8-connected neighbour offsets and their horizontal (planar) step length in
# cell units.
_NEIGHBORS: List[Tuple[int, int, float]] = [
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
    (1, 1, math.sqrt(2.0)),
    (1, -1, math.sqrt(2.0)),
    (-1, 1, math.sqrt(2.0)),
    (-1, -1, math.sqrt(2.0)),
]


class NavGrid:
    def __init__(
        self,
        bounds: Tuple[float, float, float, float],
        gridsize: float,
        buildings: Optional[Sequence[Polygon]] = None,
        obstacles: Optional[Sequence[Polygon]] = None,
        site_polygon: Optional[Polygon] = None,
        topography: Optional[Topography] = None,
        terrain_cost: Optional[TerrainCost] = None,
    ):
        min_x, min_y, max_x, max_y = bounds
        self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y
        self.gridsize = float(gridsize)
        self.nx = max(1, math.ceil((max_x - min_x) / gridsize))
        self.ny = max(1, math.ceil((max_y - min_y) / gridsize))

        # Cell-centre coordinate of cell (0,0) -- matches the Java ``sx``/``sy``.
        self.sx = min_x + gridsize / 2.0
        self.sy = min_y + gridsize / 2.0
        self.xs = self.sx + np.arange(self.nx) * gridsize
        self.ys = self.sy + np.arange(self.ny) * gridsize

        self.buildings = list(buildings) if buildings else []
        self.obstacles = list(obstacles) if obstacles else []
        self.site_polygon = list(site_polygon) if site_polygon else None

        self.topography = topography
        self.terrain_cost = terrain_cost or TerrainCost()

        self.elevation: Optional[np.ndarray] = None
        if topography is not None:
            self.elevation = topography.sample_grid(self.xs, self.ys)

        self.walkable = self._build_walkable()
        self.occupancy = np.zeros((self.nx, self.ny), dtype=float)
        self.max_occupancy = 0.0
        self.occupancy_decay = 0.99

        self._cost_fields: Dict[int, np.ndarray] = {}

    # ------------------------------------------------------------------ build
    def _build_walkable(self) -> np.ndarray:
        walkable = np.ones((self.nx, self.ny), dtype=bool)
        if self.site_polygon is not None:
            inside_site = rasterize_polygons_mask([self.site_polygon], self.xs, self.ys)
            walkable &= inside_site
        blockers = list(self.buildings) + list(self.obstacles)
        if blockers:
            blocked = rasterize_polygons_mask(blockers, self.xs, self.ys)
            walkable &= ~blocked
        return walkable

    # -------------------------------------------------------------- transforms
    def cell_x(self, x: float) -> int:
        return int(round((x - self.sx) / self.gridsize))

    def cell_y(self, y: float) -> int:
        return int(round((y - self.sy) / self.gridsize))

    def world_x(self, i: float) -> float:
        return self.sx + i * self.gridsize

    def world_y(self, j: float) -> float:
        return self.sy + j * self.gridsize

    def in_bounds(self, i: int, j: int) -> bool:
        return 0 <= i < self.nx and 0 <= j < self.ny

    def is_walkable(self, i: int, j: int) -> bool:
        return self.in_bounds(i, j) and bool(self.walkable[i, j])

    # ------------------------------------------------------------- cost fields
    def cost_field(self, key: int) -> Optional[np.ndarray]:
        return self._cost_fields.get(key)

    def compute_cost_field(self, key: int, ox: float, oy: float) -> np.ndarray:
        """Dijkstra cost-to-destination field seeded at world point ``(ox, oy)``.

        The returned ``[nx, ny]`` array holds, for every walkable cell, the
        accumulated cost of the least-effort walk *from that cell to the
        destination*. Unreachable / blocked cells are ``inf``.

        When a topography is present the per-step cost reflects the direction the
        agent actually walks (uphill is expensive), so the search expands from
        the destination using the reversed step direction.
        """
        px = min(max(self.cell_x(ox), 0), self.nx - 1)
        py = min(max(self.cell_y(oy), 0), self.ny - 1)

        cost = np.full((self.nx, self.ny), np.inf, dtype=float)
        cost[px, py] = 0.0

        elev = self.elevation
        use_terrain = elev is not None
        gsize = self.gridsize
        tc = self.terrain_cost

        heap: List[Tuple[float, int, int]] = [(0.0, px, py)]
        while heap:
            c, i, j = heapq.heappop(heap)
            if c > cost[i, j]:
                continue
            for di, dj, planar in _NEIGHBORS:
                ni, nj = i + di, j + dj
                if not (0 <= ni < self.nx and 0 <= nj < self.ny):
                    continue
                if not self.walkable[ni, nj]:
                    continue
                horiz = planar * gsize
                if use_terrain:
                    # Agent walks neighbour -> current (towards destination).
                    dz = elev[i, j] - elev[ni, nj]
                    step = tc.step_cost(dz, horiz)
                else:
                    step = horiz
                if not math.isfinite(step):
                    continue
                nc = c + step
                if nc < cost[ni, nj]:
                    cost[ni, nj] = nc
                    heapq.heappush(heap, (nc, ni, nj))

        self._cost_fields[key] = cost
        return cost

    def clear_cost_fields(self) -> None:
        self._cost_fields.clear()

    # --------------------------------------------------------------- occupancy
    def add_occupancy(self, i: int, j: int, amount: float = 1.0) -> None:
        if self.in_bounds(i, j):
            self.occupancy[i, j] += amount

    def decay_occupancy(self) -> None:
        np.multiply(self.occupancy, self.occupancy_decay, out=self.occupancy)
        self.occupancy[self.occupancy < 1e-3] = 0.0
        self.max_occupancy = float(self.occupancy.max()) if self.occupancy.size else 0.0

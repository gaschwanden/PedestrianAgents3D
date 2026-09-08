"""The navigation grid: walkability, flood-fill cost fields, and the accumulated
occupancy / visibility analysis layers.

Python counterpart of the Java ``Grid`` / ``GridPoint`` / ``Grid_Thread`` trio.

* Walkability = inside the site boundary AND outside every building/obstacle
  footprint (``permablocked`` = outside site, ``openspace`` = not blocked;
  ``walkable`` = openspace and not permablocked). ``boundary`` marks blocked
  cells that touch open space (used by the facade-visibility analysis).
* The cost-to-destination field is either the faithful uniform-cost BFS flood
  fill with the original random diagonal bias (flat ground) or a slope-weighted
  Dijkstra when a topography is attached (least-effort routing).
* ``occupancy``, ``visibility`` and ``visibility_o`` accumulate agent traffic and
  sight-lines and decay every tick.
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .geometry import Polygon, point_in_polygon, rasterize_polygons_mask
from .topography import TerrainCost, Topography

_DIAG: List[Tuple[int, int, float]] = [
    (1, 1, math.sqrt(2.0)),
    (1, -1, math.sqrt(2.0)),
    (-1, 1, math.sqrt(2.0)),
    (-1, -1, math.sqrt(2.0)),
]
_ORTHO: List[Tuple[int, int, float]] = [
    (1, 0, 1.0),
    (-1, 0, 1.0),
    (0, 1, 1.0),
    (0, -1, 1.0),
]
_NEIGHBORS = _ORTHO + _DIAG


def _poly_of(obj) -> Polygon:
    """Accept either a raw polygon (list of points) or a Building-like object
    with a ``footprint`` and return its (x, y) ring."""
    fp = getattr(obj, "footprint", None)
    if fp is not None:
        return fp.as_xy()
    return obj


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
        num_groups: int = 3,
    ):
        min_x, min_y, max_x, max_y = bounds
        self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y
        self.gridsize = float(gridsize)
        self.nx = max(1, math.ceil((max_x - min_x) / gridsize))
        self.ny = max(1, math.ceil((max_y - min_y) / gridsize))
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

        self.permablocked = np.zeros((self.nx, self.ny), dtype=bool)
        self.openspace = np.ones((self.nx, self.ny), dtype=bool)
        self.boundary = np.zeros((self.nx, self.ny), dtype=bool)
        self.walkable = np.ones((self.nx, self.ny), dtype=bool)
        self._rebuild_walkable()

        self.num_groups = num_groups
        self.occupancy = np.zeros((self.nx, self.ny), dtype=float)
        self.visibility = np.zeros((self.nx, self.ny), dtype=float)
        self.visibility_o = np.zeros((self.nx, self.ny, num_groups), dtype=float)
        self.max_occupancy = 0.0
        self.max_visibility = 0.0
        self.max_boundary_visibility = 0.0
        self.max_boundary_visibility_o = 0.0
        self.occupancy_decay = 0.99
        self.decay = 0.99

        self._cost_fields: Dict[int, np.ndarray] = {}

    # ------------------------------------------------------------------ build
    def _rebuild_walkable(self) -> None:
        self.permablocked[:] = False
        self.openspace[:] = True
        if self.site_polygon is not None:
            inside = rasterize_polygons_mask([self.site_polygon], self.xs, self.ys)
            self.permablocked = ~inside
        blockers = [_poly_of(b) for b in (list(self.buildings) + list(self.obstacles))]
        if blockers:
            blocked = rasterize_polygons_mask(blockers, self.xs, self.ys)
            self.openspace = ~blocked
        self.walkable = self.openspace & (~self.permablocked)
        self._compute_boundary()

    def _compute_boundary(self) -> None:
        self.boundary[:] = False
        blocked = ~self.openspace
        # a blocked cell is a boundary cell if any 8-neighbour is open space
        open_ = self.openspace
        nb = np.zeros_like(open_)
        nb[1:, :] |= open_[:-1, :]
        nb[:-1, :] |= open_[1:, :]
        nb[:, 1:] |= open_[:, :-1]
        nb[:, :-1] |= open_[:, 1:]
        nb[1:, 1:] |= open_[:-1, :-1]
        nb[1:, :-1] |= open_[:-1, 1:]
        nb[:-1, 1:] |= open_[1:, :-1]
        nb[:-1, :-1] |= open_[1:, 1:]
        self.boundary = blocked & nb

    def set_geometry(self, buildings, obstacles, site_polygon=None) -> None:
        self.buildings = list(buildings)
        self.obstacles = list(obstacles)
        if site_polygon is not None:
            self.site_polygon = list(site_polygon)
        self._rebuild_walkable()

    def partial_update(self, rect: Tuple[float, float, float, float]) -> None:
        """Re-rasterise walkability in a world-space rectangle after a building or
        obstacle changes (port of ``Grid_Thread.partialGridStatus``)."""
        min_px = min(max(self.cell_x(rect[0]), 0), self.nx - 1)
        min_py = min(max(self.cell_y(rect[1]), 0), self.ny - 1)
        max_px = min(max(self.cell_x(rect[2]), 0), self.nx - 1)
        max_py = min(max(self.cell_y(rect[3]), 0), self.ny - 1)
        blockers = list(self.buildings) + list(self.obstacles)
        for i in range(min_px, max_px + 1):
            x = self.xs[i]
            for j in range(min_py, max_py + 1):
                y = self.ys[j]
                blocked = False
                for b in blockers:
                    f = b.footprint
                    if x < f.min_x or y < f.min_y or x > f.max_x or y > f.max_y:
                        continue
                    if b.footprint.floor_z > 1.5:
                        continue
                    if point_in_polygon(x, y, f.as_xy()):
                        blocked = True
                        break
                self.openspace[i, j] = not blocked
        self.walkable = self.openspace & (~self.permablocked)
        self._compute_boundary()

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

    def clear_cost_fields(self) -> None:
        self._cost_fields.clear()

    def compute_cost_field(self, key: int, ox: float, oy: float,
                           rng: Optional[np.random.Generator] = None) -> np.ndarray:
        """Compute the cost-to-destination field seeded at ``(ox, oy)``.

        Uses the slope-weighted Dijkstra when a topography is present, otherwise
        the faithful BFS flood fill (with the original random diagonal bias)."""
        if self.elevation is not None:
            return self._dijkstra(key, ox, oy)
        return self._bfs(key, ox, oy, rng)

    def _seed_cell(self, ox: float, oy: float) -> Tuple[int, int]:
        px = min(max(self.cell_x(ox), 0), self.nx - 1)
        py = min(max(self.cell_y(oy), 0), self.ny - 1)
        return px, py

    def _bfs(self, key: int, ox: float, oy: float,
             rng: Optional[np.random.Generator]) -> np.ndarray:
        """Uniform-cost BFS flood fill, matching the Java ``floodfill``: 70% of
        expansions use only orthogonal neighbours, 30% use all 8 (a cheap way to
        avoid a purely diagonal or purely orthogonal bias)."""
        if rng is None:
            rng = np.random.default_rng()
        nx, ny = self.nx, self.ny
        dist = np.zeros((nx, ny), dtype=np.int32)  # 0 = unvisited
        px, py = self._seed_cell(ox, oy)
        dist[px, py] = 1
        q: deque = deque()
        q.append((px, py, 1))
        while q:
            ax, ay, d = q.popleft()
            neighbors = _ORTHO if (rng.random() * 100 >= 30) else _NEIGHBORS
            for di, dj, _ in neighbors:
                x = ax + di
                y = ay + dj
                if x < 0 or x >= nx or y < 0 or y >= ny:
                    continue
                if not self.walkable[x, y]:
                    continue
                if dist[x, y] != 0:
                    continue
                dist[x, y] = d + 1
                q.append((x, y, d + 1))
        cost = np.where(dist > 0, dist.astype(float), np.inf)
        self._cost_fields[key] = cost
        return cost

    def _dijkstra(self, key: int, ox: float, oy: float) -> np.ndarray:
        nx, ny = self.nx, self.ny
        px, py = self._seed_cell(ox, oy)
        cost = np.full((nx, ny), np.inf, dtype=float)
        cost[px, py] = 0.0
        elev = self.elevation
        gsize = self.gridsize
        tc = self.terrain_cost
        heap: List[Tuple[float, int, int]] = [(0.0, px, py)]
        while heap:
            c, i, j = heapq.heappop(heap)
            if c > cost[i, j]:
                continue
            for di, dj, planar in _NEIGHBORS:
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny):
                    continue
                if not self.walkable[ni, nj]:
                    continue
                horiz = planar * gsize
                dz = elev[i, j] - elev[ni, nj]  # agent walks neighbour -> current
                step = tc.step_cost(dz, horiz)
                if not math.isfinite(step):
                    continue
                nc = c + step
                if nc < cost[ni, nj]:
                    cost[ni, nj] = nc
                    heapq.heappush(heap, (nc, ni, nj))
        self._cost_fields[key] = cost
        return cost

    # --------------------------------------------------------------- occupancy
    def add_occupancy(self, i: int, j: int, amount: float = 1.0) -> None:
        if self.in_bounds(i, j):
            self.occupancy[i, j] += amount

    def add_visibility(self, i: int, j: int, group: int = -1) -> None:
        if not self.in_bounds(i, j):
            return
        self.visibility[i, j] += 1.0
        if 0 <= group < self.num_groups:
            self.visibility_o[i, j, group] += 1.0

    def decay_fields(self) -> None:
        """Decay occupancy and visibility, tracking maxima (incl. on boundary
        cells, used to normalise the facade-visibility colours)."""
        self.occupancy *= self.occupancy_decay
        self.occupancy[self.occupancy < 1e-3] = 0.0
        self.visibility *= self.decay
        self.visibility[self.visibility < 1e-3] = 0.0
        self.visibility_o *= self.decay
        self.visibility_o[self.visibility_o < 1e-3] = 0.0

        self.max_occupancy = float(self.occupancy.max()) if self.occupancy.size else 0.0
        self.max_visibility = float(self.visibility.max()) if self.visibility.size else 0.0
        if self.boundary.any():
            self.max_boundary_visibility = float(self.visibility[self.boundary].max())
            self.max_boundary_visibility_o = float(self.visibility_o[self.boundary].max())
        else:
            self.max_boundary_visibility = 0.0
            self.max_boundary_visibility_o = 0.0

    # Backwards-compatible alias.
    def decay_occupancy(self) -> None:
        self.decay_fields()

    def reset_analysis(self) -> None:
        self.occupancy[:] = 0.0
        self.visibility[:] = 0.0
        self.visibility_o[:] = 0.0
        self.max_occupancy = 0.0
        self.max_visibility = 0.0
        self.max_boundary_visibility = 0.0
        self.max_boundary_visibility_o = 0.0

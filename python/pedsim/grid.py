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
from .layers import Layer, LayerStack
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
        friction: Optional[np.ndarray] = None,
        blocked_mask: Optional[np.ndarray] = None,
        layers: Optional["LayerStack"] = None,
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

        # Landscape influences. ``friction``/``blocked_mask`` are a fixed base;
        # ``layers`` is the named, re-weightable stack on top of it (rivers,
        # vegetation, walls...). The effective arrays are recombined on demand.
        self._base_friction = self._check_layer(friction, float, "friction")
        self._base_blocked = self._check_layer(blocked_mask, bool, "blocked_mask")
        self.layers = layers if layers is not None else LayerStack((self.nx, self.ny))
        self.friction: Optional[np.ndarray] = None
        self.extra_blocked: Optional[np.ndarray] = None
        self.step_penalty: Optional[np.ndarray] = None
        self._layers_version = -1
        self._combine_layers()

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
    def _check_layer(self, arr, dtype, name):
        if arr is None:
            return None
        a = np.asarray(arr, dtype=dtype)
        if a.shape != (self.nx, self.ny):
            raise ValueError(
                f"{name} must have shape {(self.nx, self.ny)}, got {a.shape}"
            )
        return a

    def set_friction(self, friction: Optional[np.ndarray]) -> None:
        """Replace the *base* friction and invalidate cached cost fields."""
        self._base_friction = self._check_layer(friction, float, "friction")
        self.refresh_layers(force=True)

    def set_blocked_mask(self, blocked_mask: Optional[np.ndarray]) -> None:
        """Replace the *base* blocked mask (rasterised walls / water)."""
        self._base_blocked = self._check_layer(blocked_mask, bool, "blocked_mask")
        self.refresh_layers(force=True)

    def add_layer(self, layer: "Layer") -> "Layer":
        """Add/replace a named landscape layer and refresh the derived arrays."""
        self.layers.add(layer)
        self.refresh_layers(force=True)
        return layer

    def _combine_layers(self) -> None:
        """Fold the base arrays and the weighted layer stack into the effective
        ``friction`` / ``extra_blocked`` arrays used by the solvers."""
        lf = self.layers.friction() if self.layers is not None else None
        lb = self.layers.blocked() if self.layers is not None else None
        if self._base_friction is None:
            self.friction = lf
        elif lf is None:
            self.friction = self._base_friction
        else:
            self.friction = self._base_friction * lf
        if self._base_blocked is None:
            self.extra_blocked = lb
        elif lb is None:
            self.extra_blocked = self._base_blocked
        else:
            self.extra_blocked = self._base_blocked | lb
        self._layers_version = self.layers.version if self.layers is not None else -1
        self._compute_step_penalty()

    def _compute_step_penalty(self) -> None:
        """Extra cost of entering a cell, over and above open flat going, in the
        same units as the cost field.

        The cost field on its own cannot deflect anybody: agents pick the
        *farthest visible* cell that improves their cost, so with a clear line
        of sight they wade straight across an expensive river instead of walking
        to the ford. Accumulating this penalty along the sight-line lets them
        compare "go straight through" against "the route the cost field knows",
        and only beeline when the straight line is actually worth it.

        The baseline is the *median* cell, not the theoretical best one, so only
        ground that is unusually hard for this landscape costs anything: a river
        or a scarp in otherwise open country, but not the ordinary slope of a
        uniformly hilly one. That keeps ordinary scenes steering as they always
        did and confines the effect to the obstacles it is meant to represent.

        For slope the estimate is isotropic (from the local gradient magnitude)
        -- good enough for choosing a waypoint; the routing itself stays
        directional.
        """
        gsize = self.gridsize
        if self.elevation is not None:
            dzdx, dzdy = np.gradient(self.elevation, gsize)
            slope = np.hypot(dzdx, dzdy)
            cell = gsize / np.maximum(self.terrain_cost.speed(slope), 1e-9)
            if self.friction is not None:
                cell = cell * self.friction
        elif self.friction is not None:
            cell = np.array(self.friction, dtype=float)
        else:
            self.step_penalty = None
            return
        finite = np.isfinite(cell)
        typical = float(np.median(cell[finite])) if finite.any() else 0.0
        pen = np.where(finite, cell - typical, 1e6)
        self.step_penalty = np.maximum(pen, 0.0)

    def layers_dirty(self) -> bool:
        return self.layers is not None and self.layers.version != self._layers_version

    def refresh_layers(self, force: bool = False) -> bool:
        """Recombine the layer stack if a weight changed. Returns True if the
        derived arrays (and hence the cost fields) were rebuilt."""
        if not force and not self.layers_dirty():
            return False
        self._combine_layers()
        self._rebuild_walkable()
        self.clear_cost_fields()
        return True

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
        if self.extra_blocked is not None:
            self.walkable &= ~self.extra_blocked
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
        if self.extra_blocked is not None:
            self.walkable &= ~self.extra_blocked
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

        Three solvers, in order of increasing information:

        * topography present -> slope-weighted Dijkstra (directional up/down cost)
        * friction only      -> friction-weighted flood fill (adds >1 per cell)
        * neither            -> the faithful uniform-cost BFS flood fill
        """
        if self.elevation is not None:
            return self._dijkstra(key, ox, oy)
        if self.friction is not None:
            return self._weighted_floodfill(key, ox, oy, rng)
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

    def _weighted_floodfill(self, key: int, ox: float, oy: float,
                            rng: Optional[np.random.Generator]) -> np.ndarray:
        """Friction-weighted flood fill.

        Keeps the character of the original uniform-cost fill -- including the
        70/30 orthogonal/all-neighbour random bias, and a flat increment that
        ignores diagonal length -- but instead of adding 1 per cell it adds the
        local ``friction``, so crossing a river or thick scrub costs several
        cells' worth of effort. Because the increments are uneven a plain FIFO
        queue would no longer settle cells in cost order, so the frontier is a
        priority queue and cells may be relaxed more than once.
        """
        if rng is None:
            rng = np.random.default_rng()
        nx, ny = self.nx, self.ny
        fric = self.friction
        cost = np.full((nx, ny), np.inf, dtype=float)
        px, py = self._seed_cell(ox, oy)
        cost[px, py] = 0.0
        heap: List[Tuple[float, int, int]] = [(0.0, px, py)]
        while heap:
            c, i, j = heapq.heappop(heap)
            if c > cost[i, j]:
                continue
            neighbors = _ORTHO if (rng.random() * 100 >= 30) else _NEIGHBORS
            for di, dj, _ in neighbors:
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny):
                    continue
                if not self.walkable[ni, nj]:
                    continue
                inc = 1.0 if fric is None else 0.5 * (fric[i, j] + fric[ni, nj])
                if not math.isfinite(inc):
                    continue
                nc = c + inc
                if nc < cost[ni, nj]:
                    cost[ni, nj] = nc
                    heapq.heappush(heap, (nc, ni, nj))
        self._cost_fields[key] = cost
        return cost

    # -- plain-list views ---------------------------------------------------
    # Reading one cell of a numpy array from Python costs far more than the
    # arithmetic around it. The solvers and the agents' sight-lines read cells
    # one at a time, so they work on nested lists made once per array. The
    # values are the same doubles; only the container changes.
    def walkable_rows(self) -> list:
        cached = getattr(self, "_walk_rows", None)
        if cached is None or cached[0] is not self.walkable:
            cached = (self.walkable, self.walkable.tolist())
            self._walk_rows = cached
        return cached[1]

    def cost_rows(self, key: int) -> Optional[list]:
        arr = self._cost_fields.get(key)
        if arr is None:
            return None
        store = self.__dict__.setdefault("_cost_rows", {})
        cached = store.get(key)
        if cached is None or cached[0] is not arr:
            cached = (arr, arr.tolist())
            store[key] = cached
        return cached[1]

    def penalty_rows(self) -> Optional[list]:
        if self.step_penalty is None:
            return None
        cached = getattr(self, "_penalty_rows", None)
        if cached is None or cached[0] is not self.step_penalty:
            cached = (self.step_penalty, self.step_penalty.tolist())
            self._penalty_rows = cached
        return cached[1]

    def _step_costs(self) -> list:
        """Cost of the step *into* each cell from each of its 8 neighbours'
        expansion, as ``[(di, dj, rows)]`` -- the terrain and friction part of
        Dijkstra, done once for all destinations instead of once per edge."""
        tc = self.terrain_cost
        tag = (self.elevation, self.friction, tc.base_speed, tc.slope_factor,
               tc.slope_offset, tc.impassable_slope, tc.max_ascent_slope,
               tc.max_descent_slope)
        cached = getattr(self, "_step_cache", None)
        if cached is not None and len(cached[0]) == len(tag) and all(
                (x is y) if isinstance(x, np.ndarray) or x is None else (x == y)
                for x, y in zip(cached[0], tag)):
            return cached[1]
        nx, ny = self.nx, self.ny
        elev = self.elevation
        fric = self.friction
        up = tc.impassable_slope if tc.max_ascent_slope is None else tc.max_ascent_slope
        down = tc.impassable_slope if tc.max_descent_slope is None else tc.max_descent_slope
        out = []
        for di, dj, planar in _NEIGHBORS:
            horiz = planar * self.gridsize
            # cells (i, j) whose neighbour (i + di, j + dj) is on the grid
            i0, i1 = max(0, -di), nx - max(0, di)
            j0, j1 = max(0, -dj), ny - max(0, dj)
            here = (slice(i0, i1), slice(j0, j1))
            there = (slice(i0 + di, i1 + di), slice(j0 + dj, j1 + dj))
            step = np.full((nx, ny), np.inf, dtype=float)
            if elev is not None:
                slope = (elev[here] - elev[there]) / horiz   # walking neighbour -> here
                with np.errstate(over="ignore", invalid="ignore"):
                    cost = horiz / (tc.base_speed * np.exp(
                        -tc.slope_factor * np.abs(slope + tc.slope_offset)))
                cost[(slope > up) | (-slope > down)] = np.inf
            else:
                cost = np.full((i1 - i0, j1 - j0), horiz, dtype=float)
            if fric is not None:
                # average the two cells so a crossing costs the same either way
                with np.errstate(invalid="ignore"):
                    cost = cost * (0.5 * (fric[here] + fric[there]))
            step[here] = cost
            out.append((di, dj, step.tolist()))
        self._step_cache = (tag, out)
        return out

    def _dijkstra(self, key: int, ox: float, oy: float) -> np.ndarray:
        nx, ny = self.nx, self.ny
        px, py = self._seed_cell(ox, oy)
        inf = math.inf
        cost = [[inf] * ny for _ in range(nx)]
        cost[px][py] = 0.0
        walk = self.walkable_rows()
        steps = self._step_costs()
        heap: List[Tuple[float, int, int]] = [(0.0, px, py)]
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            c, i, j = pop(heap)
            if c > cost[i][j]:
                continue
            for di, dj, rows in steps:
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny):
                    continue
                if not walk[ni][nj]:
                    continue
                step = rows[i][j]
                if not step < inf:        # impassable, or undefined (nan)
                    continue
                nc = c + step
                if nc < cost[ni][nj]:
                    cost[ni][nj] = nc
                    push(heap, (nc, ni, nj))
        field = np.array(cost, dtype=float)
        self._cost_fields[key] = field
        return field

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

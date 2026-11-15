"""Nested grids: a coarse landscape with fine patches where the detail is.

A settlement scene a few kilometres across is mostly empty ground. A single
grid fine enough for a doorway (1 m) would have millions of cells there, and
every route would be solved over all of them. A nested scene keeps the
scene's own grid coarse (5 m, say) and lays **patches** of fine cells over the
places that need them: around buildings and walls, around the places walkers
go to, along rivers, and wherever the user marks.

How the two levels fit together:

* **Patches are tiles.** The scene is divided into square tiles aligned with
  the coarse cells. Every tile that a feature (plus a margin) touches becomes
  fine, and touching tiles are merged into rectangles. Coarse cells under a
  patch are switched off: each piece of ground belongs to exactly one grid.
* **One route solve over both.** A cost field is one Dijkstra over the coarse
  cells *and* the fine cells, joined along every patch edge. So the field is
  consistent across the edge, and a route may enter a patch, cross it and
  leave again.
* **Walkers are on one grid at a time.** Each sees and steps on its own grid,
  exactly as in a single-grid scene. When the cell across a patch edge is
  cheaper than the one it stands on, it hops over. Sight-lines therefore end
  at a patch edge.
* **One clock.** A fine walker takes ``ratio`` small steps in a tick while a
  coarse walker takes one large one, so both cover the same ground per tick.

A scene without patches does not touch this module and behaves as before.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from .grid import NavGrid

Tile = Tuple[int, int]
Rect = Tuple[float, float, float, float]

#: Places that are just scene-edge entry points do not need fine ground.
COARSE_OD_KINDS = ("gate", "site")


@dataclass
class NestedConfig:
    """How a scene is refined. All lengths in metres.

    ``fine`` must divide the coarse cell size and ``tile`` must be a multiple
    of it. ``margin`` is how far around a feature the fine ground extends.
    ``max_fine_cells`` caps the total: features are refined in the order
    buildings and walls, places, marked rectangles, rivers, and whatever does
    not fit stays coarse and is reported in ``Simulation.nested_notes``.
    """

    fine: float = 1.0
    tile: float = 50.0
    margin: float = 15.0
    rivers: bool = True
    max_fine_cells: int = 800_000
    marked: List[Rect] = field(default_factory=list)


@dataclass
class Patch:
    bounds: Rect
    grid: NavGrid

    def contains(self, x: float, y: float) -> bool:
        b = self.bounds
        return b[0] <= x < b[2] and b[1] <= y < b[3]


# ------------------------------------------------------------------- tiles
def _tiles_for_rect(sim, rect: Rect, cfg: NestedConfig) -> Set[Tile]:
    g = sim.grid
    n_i = int(math.ceil((g.max_x - g.min_x) / cfg.tile))
    n_j = int(math.ceil((g.max_y - g.min_y) / cfg.tile))
    i0 = int(math.floor((rect[0] - cfg.margin - g.min_x) / cfg.tile))
    j0 = int(math.floor((rect[1] - cfg.margin - g.min_y) / cfg.tile))
    i1 = int(math.floor((rect[2] + cfg.margin - g.min_x) / cfg.tile))
    j1 = int(math.floor((rect[3] + cfg.margin - g.min_y) / cfg.tile))
    return {(i, j) for i in range(max(i0, 0), min(i1, n_i - 1) + 1)
            for j in range(max(j0, 0), min(j1, n_j - 1) + 1)}


def wanted_tiles(sim) -> Tuple[Set[Tile], List[str]]:
    """Tiles to refine, and notes on anything left coarse for want of room."""
    cfg: NestedConfig = sim.nested
    per_tile = int(round(cfg.tile / cfg.fine)) ** 2
    room = max(1, cfg.max_fine_cells // per_tile)
    tiles: Set[Tile] = set()
    notes: List[str] = []

    def take(name: str, rects: Sequence[Rect]) -> None:
        skipped = 0
        for rect in rects:
            new = _tiles_for_rect(sim, rect, cfg) - tiles
            if len(tiles) + len(new) > room:
                skipped += 1
                continue
            tiles.update(new)
        if skipped:
            notes.append(f"{skipped} {name} left on the coarse grid: the fine-cell "
                         f"limit of {cfg.max_fine_cells} is reached")

    buildings, obstacles = sim.geometry_for_grid()
    take("buildings or walls", [item.bbox() for item in list(buildings) + list(obstacles)])
    take("places", [(od.x, od.y, od.x, od.y) for od in sim.ods
                    if od is not None and (od.kind or "site") not in COARSE_OD_KINDS])
    take("marked areas", list(cfg.marked))
    if cfg.rivers:
        points = []
        for river in sim.rivers:
            path = list(river.path)
            for (x0, y0), (x1, y1) in zip(path, path[1:]):
                steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (cfg.tile / 2.0)))
                for k in range(steps + 1):
                    t = k / steps
                    x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                    half = float(getattr(river, "width", 0.0)) / 2.0
                    points.append((x - half, y - half, x + half, y + half))
        take("river stretches", points)
    return tiles, notes


def merge_tiles(tiles: Set[Tile]) -> List[Tuple[int, int, int, int]]:
    """Cover a tile set with rectangles ``(i0, j0, i1, j1)``, inclusive.

    Runs of tiles along a row are joined, then identical runs in consecutive
    rows are stacked. Not minimal, but few and deterministic.
    """
    runs: Dict[int, List[Tuple[int, int]]] = {}
    for j in sorted({t[1] for t in tiles}):
        row = sorted(t[0] for t in tiles if t[1] == j)
        start = prev = row[0]
        out = []
        for i in row[1:]:
            if i != prev + 1:
                out.append((start, prev))
                start = i
            prev = i
        out.append((start, prev))
        runs[j] = out
    rects: List[Tuple[int, int, int, int]] = []
    open_rects: Dict[Tuple[int, int], int] = {}      # run -> first row
    last_row: Optional[int] = None
    for j in sorted(runs):
        if last_row is not None and j != last_row + 1:
            for (i0, i1), j0 in open_rects.items():
                rects.append((i0, j0, i1, last_row))
            open_rects = {}
        current = set(runs[j])
        for run in list(open_rects):
            if run not in current:
                rects.append((run[0], open_rects.pop(run), run[1], j - 1))
        for run in runs[j]:
            open_rects.setdefault(run, j)
        last_row = j
    for (i0, i1), j0 in open_rects.items():
        rects.append((i0, j0, i1, last_row))
    return sorted(rects)


# ----------------------------------------------------------------- building
def _check(sim) -> int:
    cfg: NestedConfig = sim.nested
    coarse = sim.grid.gridsize
    ratio = coarse / cfg.fine
    if abs(ratio - round(ratio)) > 1e-9 or ratio < 2:
        raise ValueError(f"fine cell {cfg.fine} m must divide the coarse cell {coarse} m "
                         "at least twice")
    per = cfg.tile / coarse
    if abs(per - round(per)) > 1e-9:
        raise ValueError(f"tile {cfg.tile} m must be a whole number of {coarse} m cells")
    return int(round(ratio))


def rebuild(sim) -> None:
    """Bring the patches in line with the scene's features and geometry.

    Called whenever routes are re-solved, which is after every edit. Patches
    whose rectangle is unchanged keep their grid (and their heat map).
    """
    from .rivers import build_layers

    cfg: NestedConfig = sim.nested
    sim.nested_ratio = _check(sim)
    g = sim.grid
    tiles, notes = wanted_tiles(sim)
    sim.nested_notes = notes
    wanted: List[Rect] = []
    for i0, j0, i1, j1 in merge_tiles(tiles):
        wanted.append((
            g.min_x + i0 * cfg.tile, g.min_y + j0 * cfg.tile,
            min(g.min_x + (i1 + 1) * cfg.tile, g.min_x + g.nx * g.gridsize),
            min(g.min_y + (j1 + 1) * cfg.tile, g.min_y + g.ny * g.gridsize),
        ))
    old = {p.bounds: p for p in sim.patches}
    buildings, obstacles = sim.geometry_for_grid()
    patches: List[Patch] = []
    for rect in wanted:
        patch = old.get(rect)
        if patch is None:
            grid = NavGrid(
                bounds=rect, gridsize=cfg.fine, buildings=buildings, obstacles=obstacles,
                site_polygon=sim.site_polygon, topography=g.topography,
                terrain_cost=g.terrain_cost, num_groups=g.num_groups,
            )
            patch = Patch(rect, grid)
        else:
            patch.grid.terrain_cost = g.terrain_cost
            patch.grid.set_geometry(buildings, obstacles, sim.site_polygon)
        # rivers are rasterised per grid, at that grid's own resolution
        for name in ("rivers", "flood"):
            patch.grid.layers.remove(name)
        if sim.rivers:
            kept = [r.crossing_cost for r in sim.rivers]
            try:
                for r in sim.rivers:
                    r.crossing_cost = r.crossing_cost * sim.river_weight
                for layer in build_layers(patch.grid.xs, patch.grid.ys, sim.rivers, sim.season):
                    patch.grid.layers.add(layer)
            finally:
                for r, cost in zip(sim.rivers, kept):
                    r.crossing_cost = cost
        patch.grid.refresh_layers(force=True)
        for b in buildings:
            b.footprint.gridded_segments(patch.grid)
        patches.append(patch)

    changed = [p.bounds for p in patches] != [p.bounds for p in sim.patches]
    world = None
    if changed:
        # walkers keep their place on the ground while the grids under them change
        world = [(a.grid.world_x(a.px), a.grid.world_y(a.py)) if a.active else None
                 for a in sim.agents]
    sim.patches = patches

    hole = np.zeros((g.nx, g.ny), dtype=bool)
    for p in patches:
        i0 = int(round((p.bounds[0] - g.min_x) / g.gridsize))
        j0 = int(round((p.bounds[1] - g.min_y) / g.gridsize))
        i1 = int(round((p.bounds[2] - g.min_x) / g.gridsize))
        j1 = int(round((p.bounds[3] - g.min_y) / g.gridsize))
        hole[i0:i1, j0:j1] = True
    g.hole_mask = hole if patches else None
    g._rebuild_walkable()
    sim._nested_tiles = {}
    for level, p in enumerate(patches, start=1):
        ti0 = int(round((p.bounds[0] - g.min_x) / cfg.tile))
        tj0 = int(round((p.bounds[1] - g.min_y) / cfg.tile))
        ti1 = int(math.ceil((p.bounds[2] - g.min_x) / cfg.tile - 1e-9))
        tj1 = int(math.ceil((p.bounds[3] - g.min_y) / cfg.tile - 1e-9))
        for ti in range(ti0, ti1):
            for tj in range(tj0, tj1):
                sim._nested_tiles[(ti, tj)] = level
    sim._nested_links = _links(sim)
    if world is not None:
        for a, pos in zip(sim.agents, world):
            if pos is None:
                continue
            a.level = level_at(sim, pos[0], pos[1])
            grid = a.grid
            a.px = (pos[0] - grid.sx) / grid.gridsize
            a.py = (pos[1] - grid.sy) / grid.gridsize
            a.far_px = a.far_py = -1


def grids(sim) -> List[NavGrid]:
    return [sim.grid] + [p.grid for p in sim.patches]


def level_at(sim, x: float, y: float) -> int:
    """Which grid owns the ground at ``(x, y)``: 0 coarse, k the k-th patch."""
    tiles = getattr(sim, "_nested_tiles", None)
    if not tiles:
        return 0
    g = sim.grid
    tile = sim.nested.tile
    return tiles.get((int(math.floor((x - g.min_x) / tile)),
                      int(math.floor((y - g.min_y) / tile))), 0)


def _links(sim) -> List[Dict[Tuple[int, int], List[Tuple[int, int, int]]]]:
    """For every grid, the cells across a patch edge from each of its edge cells."""
    all_grids = grids(sim)
    links: List[Dict[Tuple[int, int], List[Tuple[int, int, int]]]] = [{} for _ in all_grids]

    def join(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> None:
        links[a[0]].setdefault((a[1], a[2]), [])
        if b not in links[a[0]][(a[1], a[2])]:
            links[a[0]][(a[1], a[2])].append(b)
        links[b[0]].setdefault((b[1], b[2]), [])
        if a not in links[b[0]][(b[1], b[2])]:
            links[b[0]][(b[1], b[2])].append(a)

    coarse = sim.grid
    for level, patch in enumerate(sim.patches, start=1):
        g = patch.grid
        edge = ([(i, 0, 0.0, -1.0) for i in range(g.nx)]
                + [(i, g.ny - 1, 0.0, 1.0) for i in range(g.nx)]
                + [(0, j, -1.0, 0.0) for j in range(g.ny)]
                + [(g.nx - 1, j, 1.0, 0.0) for j in range(g.ny)])
        for i, j, dx, dy in edge:
            x = g.xs[i] + dx * g.gridsize
            y = g.ys[j] + dy * g.gridsize
            if not (coarse.min_x <= x < coarse.min_x + coarse.nx * coarse.gridsize
                    and coarse.min_y <= y < coarse.min_y + coarse.ny * coarse.gridsize):
                continue
            other = level_at(sim, x, y)
            og = all_grids[other]
            oi, oj = og.cell_x(x), og.cell_y(y)
            if og.in_bounds(oi, oj):
                join((level, i, j), (other, oi, oj))
    return links


# ------------------------------------------------------------------ routing
def solve(sim, key: int, ox: float, oy: float) -> None:
    """One cost field over every grid of the scene, for the place at ``(ox, oy)``.

    The same directional Dijkstra as :meth:`NavGrid._dijkstra`, with one more
    kind of edge: across a patch boundary, between a fine cell and the cell of
    the neighbouring grid it touches.
    """
    all_grids = grids(sim)
    links = sim._nested_links
    inf = math.inf
    cost = [[[inf] * g.ny for _ in range(g.nx)] for g in all_grids]
    walk = [g.walkable_rows() for g in all_grids]
    steps = [g._step_costs() for g in all_grids]
    size = [(g.nx, g.ny) for g in all_grids]
    # list copies of elevation and friction, made once per set of grids rather
    # than once per place (they are only read at patch edges)
    tag = tuple((id(g.elevation), id(g.friction)) for g in all_grids)
    cached = getattr(sim, "_nested_lists", None)
    if cached is None or cached[0] != tag:
        cached = (tag,
                  [g.elevation.tolist() if g.elevation is not None else None for g in all_grids],
                  [g.friction.tolist() if g.friction is not None else None for g in all_grids])
        sim._nested_lists = cached
    elev, fric = cached[1], cached[2]
    tc = sim.grid.terrain_cost

    def link_cost(frm: Tuple[int, int, int], to: Tuple[int, int, int]) -> float:
        """Cost of the step a walker takes from ``frm`` to ``to``."""
        (l0, i0, j0), (l1, i1, j1) = frm, to
        g0, g1 = all_grids[l0], all_grids[l1]
        dist = math.hypot(g1.xs[i1] - g0.xs[i0], g1.ys[j1] - g0.ys[j0])
        dz = 0.0
        if elev[l0] is not None and elev[l1] is not None:
            dz = elev[l1][i1][j1] - elev[l0][i0][j0]
        step = float(tc.step_cost(dz, dist))
        f0 = fric[l0][i0][j0] if fric[l0] is not None else 1.0
        f1 = fric[l1][i1][j1] if fric[l1] is not None else 1.0
        return step * 0.5 * (f0 + f1)

    level = level_at(sim, ox, oy)
    pi, pj = all_grids[level]._seed_cell(ox, oy)
    cost[level][pi][pj] = 0.0
    heap: List[Tuple[float, int, int, int]] = [(0.0, level, pi, pj)]
    pop, push = heapq.heappop, heapq.heappush
    while heap:
        c, lv, i, j = pop(heap)
        own = cost[lv]
        if c > own[i][j]:
            continue
        nx, ny = size[lv]
        w = walk[lv]
        for di, dj, rows in steps[lv]:
            ni, nj = i + di, j + dj
            if not (0 <= ni < nx and 0 <= nj < ny):
                continue
            if not w[ni][nj]:
                continue
            step = rows[i][j]
            if not step < inf:
                continue
            nc = c + step
            if nc < own[ni][nj]:
                own[ni][nj] = nc
                push(heap, (nc, lv, ni, nj))
        across = links[lv].get((i, j))
        if across:
            for l2, i2, j2 in across:
                if not walk[l2][i2][j2]:
                    continue
                step = link_cost((l2, i2, j2), (lv, i, j))
                if not step < inf:
                    continue
                nc = c + step
                if nc < cost[l2][i2][j2]:
                    cost[l2][i2][j2] = nc
                    push(heap, (nc, l2, i2, j2))
    for g, rows in zip(all_grids, cost):
        g._cost_fields[key] = np.array(rows, dtype=float)


def solve_all(sim) -> None:
    for g in grids(sim):
        g.clear_cost_fields()
    for k, od in sim._active_ods():
        solve(sim, k, od.x, od.y)


# ------------------------------------------------------------------ walking
def hop(sim, a) -> bool:
    """Move a walker across a patch edge when the far side is nearer its target."""
    links = sim._nested_links[a.level]
    if not links:
        return False
    grid = a.grid
    i = min(max(int(a.px), 0), grid.nx - 1)
    j = min(max(int(a.py), 0), grid.ny - 1)
    across = links.get((i, j))
    if not across:
        return False
    rows = grid.cost_rows(a.target)
    if rows is None:
        return False
    here = rows[i][j]
    best = None
    all_grids = grids(sim)
    for l2, i2, j2 in across:
        other = all_grids[l2].cost_rows(a.target)
        if other is None:
            continue
        value = other[i2][j2]
        if value < here and (best is None or value < best[0]):
            best = (value, l2, i2, j2)
    if best is None:
        return False
    _, a.level, i2, j2 = best
    a.px, a.py = float(i2), float(j2)
    a.far_px = a.far_py = -1
    return True


def step(sim) -> None:
    """One tick of a nested scene."""
    from .vision import scan

    ratio = sim.nested_ratio
    all_grids = grids(sim)
    for sub in range(ratio):
        for a in sim.agents:
            if a.active and (a.level > 0 or sub == 0):
                hop(sim, a)
        for level, grid in enumerate(all_grids):
            if level == 0 and sub > 0:
                continue                   # the coarse grid takes one step a tick
            walkers = [a for a in sim.agents if a.active and a.level == level]
            if not walkers:
                continue
            if sim.batch_vision:
                scan(sim, grid, walkers)
            else:
                for a in walkers:
                    a.vision_scan()
            for a in walkers:
                a.set_dir_to_target()
                if not a.active:
                    continue
                a.move()
                a.mark_occupancy()
                a.target_check()
    sim.release_agents()
    if sim.category_occupancy:
        for arr in sim.category_occupancy.values():
            arr *= sim.grid.occupancy_decay
            arr[arr < 1e-3] = 0.0
    if sim.traces:
        for t in list(sim.traces):
            t.update(sim)
            if not t.active and t.age > t.max_age:
                sim.traces.remove(t)
    for grid in all_grids:
        grid.decay_fields()
    sim.ticks += 1


def summary(sim) -> str:
    fine = sum(p.grid.nx * p.grid.ny for p in sim.patches)
    g = sim.grid
    return (f"{g.nx}x{g.ny} cells of {g.gridsize:g} m, plus {len(sim.patches)} "
            f"patches of {sim.nested.fine:g} m cells ({fine} fine cells)")

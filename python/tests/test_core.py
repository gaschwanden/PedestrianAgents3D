"""Sanity tests for the pedsim port.

Runnable either with pytest (``pytest python/tests``) or directly
(``python python/tests/test_core.py``).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim import Simulation, TerrainCost, Topography, load_site, load_topography
from pedsim.geometry import point_in_polygon
from pedsim.grid import NavGrid
from pedsim.od import OD

EX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
DATA = os.path.join(EX, "data")


def _ensure_dataset():
    sys.path.insert(0, EX)
    import build_dataset

    if not os.path.exists(os.path.join(DATA, "gobekli_site.json")):
        build_dataset.main()


def test_point_in_polygon():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon(5, 5, square)
    assert not point_in_polygon(15, 5, square)


def test_walkability_and_flat_cost_is_distance():
    building = [(40, 40), (60, 40), (60, 60), (40, 60)]
    grid = NavGrid(bounds=(0, 0, 100, 100), gridsize=2.0, buildings=[building])
    bi, bj = grid.cell_x(50), grid.cell_y(50)
    assert not grid.walkable[bi, bj]
    assert grid.walkable[grid.cell_x(10), grid.cell_y(10)]

    grid.compute_cost_field(0, 90, 90)
    cost = grid.cost_field(0)
    # On flat ground the cost is the Euclidean-ish least distance: a point twice
    # as far away costs roughly twice as much.
    c_near = cost[grid.cell_x(80), grid.cell_y(80)]
    c_far = cost[grid.cell_x(70), grid.cell_y(70)]
    assert c_far > c_near > 0


def test_topography_makes_hills_expensive():
    # A gentle (traversable) ridge runs across the middle in x.
    def elev(x, y):
        return 10.0 * math.exp(-((y - 50) / 12.0) ** 2)

    topo = Topography.from_function(elev, (0, 0, 100, 100), 101, 101)
    grid = NavGrid(bounds=(0, 0, 100, 100), gridsize=2.0, topography=topo,
                   terrain_cost=TerrainCost(slope_factor=6.0, impassable_slope=3.0))
    grid.compute_cost_field(0, 50, 90)  # destination north of the ridge

    flat = NavGrid(bounds=(0, 0, 100, 100), gridsize=2.0)
    flat.compute_cost_field(0, 50, 90)

    # From a point south of the ridge, crossing costs more with terrain than on
    # flat ground because the climb takes effort.
    p = (50, 10)
    ct = grid.cost_field(0)[grid.cell_x(p[0]), grid.cell_y(p[1])]
    cf = flat.cost_field(0)[flat.cell_x(p[0]), flat.cell_y(p[1])]
    assert math.isfinite(ct) and math.isfinite(cf)
    assert ct > cf  # climbing the ridge is penalised


def test_topography_route_detours_around_ridge():
    # Ridge across x in the middle, but with a low "pass" near x=20.
    def elev(x, y):
        base = 40.0 * math.exp(-((y - 50) / 5.0) ** 2)
        pass_gap = 38.0 * math.exp(-(((x - 20) / 8.0) ** 2 + ((y - 50) / 5.0) ** 2))
        return max(0.0, base - pass_gap)

    topo = Topography.from_function(elev, (0, 0, 100, 100), 101, 101)
    grid = NavGrid(bounds=(0, 0, 100, 100), gridsize=2.0, topography=topo,
                   terrain_cost=TerrainCost(slope_factor=8.0, impassable_slope=3.0))
    grid.compute_cost_field(0, 50, 90)
    cost = grid.cost_field(0)

    # Steepest descent from below the ridge should route through the pass (x~20),
    # not straight up at x=50.
    i, j = grid.cell_x(50), grid.cell_y(10)
    neigh = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    xs_visited = []
    for _ in range(2000):
        xs_visited.append(grid.world_x(i))
        best, bi, bj = cost[i, j], i, j
        for di, dj in neigh:
            ni, nj = i + di, j + dj
            if 0 <= ni < grid.nx and 0 <= nj < grid.ny and cost[ni, nj] < best:
                best, bi, bj = cost[ni, nj], ni, nj
        if (bi, bj) == (i, j):
            break
        i, j = bi, bj
    assert min(xs_visited) < 35  # detoured towards the pass


def test_site_importer_roles():
    _ensure_dataset()
    site = load_site(os.path.join(DATA, "gobekli_site.json"))
    ods = site.build_ods()
    by_name = {od.name: od for od in ods}
    # A gate is a pure source, an enclosure is a sink.
    assert by_name["N gate"].origin_weight > 0 and by_name["N gate"].dest_weight == 0
    assert by_name["Enclosure C"].dest_weight > 0
    # Blocking structures do not become OD places.
    assert "Wall 1" not in by_name
    assert len(site.building_polygons()) >= 4


def test_topography_importer_orientation():
    _ensure_dataset()
    topo = load_topography(os.path.join(DATA, "gobekli_dem.asc"))
    # Summit near the centre is higher than the flat corners.
    assert topo.sample(0, 0) > topo.sample(140, 140)
    assert topo.sample(0, 0) > 10


def test_simulation_runs_and_moves_agents():
    _ensure_dataset()
    site = load_site(os.path.join(DATA, "gobekli_site.json"))
    topo = load_topography(os.path.join(DATA, "gobekli_dem.asc"))
    sim = Simulation.from_site(site, topography=topo, gridsize=4.0,
                               num_agents=60, release_rate=10, cone_vision=40, seed=1)
    assert sim.reachable_targets() >= 2
    for _ in range(60):
        sim.step()
    assert len(sim.active_agents) > 0
    assert sim.grid.occupancy.max() > 0  # agents laid down a heat map


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()

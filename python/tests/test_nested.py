"""Nested grids: a coarse scene with fine patches around its features."""
import numpy as np
import pytest

from pedsim import nested
from pedsim.agent import DIED_LOST, DIED_TARGET_REACHED, Agent
from pedsim.building import Building
from pedsim.od import OD
from pedsim.simulation import Simulation
from pedsim.topography import TerrainCost, Topography


def box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def scene(seed=3, agents=60):
    size, cell = 600.0, 5.0
    n = int(size / cell)
    xs = np.arange(n) * cell
    elev = 12 * np.sin(xs[:, None] / 120.0) + 6 * np.cos(xs[None, :] / 80.0)
    ods = [
        OD(40, 40, name="gate sw", kind="gate"), OD(560, 560, name="gate ne", kind="gate"),
        OD(40, 540, name="gate nw", kind="gate"), OD(330, 330, name="spring", kind="water"),
    ]
    return Simulation(
        bounds=(0, 0, size, size), ods=ods, gridsize=cell,
        buildings=[Building.from_polygon(box(280, 280, 300, 300), height=3, function="domestic")],
        topography=Topography(elev, cell / 2, cell / 2, cell),
        terrain_cost=TerrainCost(slope_factor=6.0),
        num_agents=agents, release_rate=10, speed=0.5, seed=seed,
    )


def nest(sim, **kw):
    sim.set_nested(nested.NestedConfig(**{"fine": 1.0, "tile": 50.0, "margin": 15.0, **kw}))
    return sim


def test_tiles_merge_into_rectangles_that_cover_them_exactly():
    tiles = {(0, 0), (1, 0), (0, 1), (1, 1), (3, 0), (5, 5), (5, 6), (6, 6)}
    rects = nested.merge_tiles(tiles)
    covered = [(i, j) for i0, j0, i1, j1 in rects
               for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
    assert sorted(covered) == sorted(tiles)          # every tile once, nothing extra
    assert (0, 0, 1, 1) in rects


def test_fine_ground_appears_around_features_and_nowhere_else():
    sim = nest(scene())
    assert sim.patches
    assert nested.level_at(sim, 290, 290) > 0        # the building
    assert nested.level_at(sim, 330, 330) > 0        # the spring, a marked place
    assert nested.level_at(sim, 40, 40) == 0         # a gate stays coarse
    assert nested.level_at(sim, 500, 100) == 0       # empty ground
    # each piece of ground belongs to one grid: coarse cells under a patch are off
    g = sim.grid
    assert not g.walkable[g.cell_x(290), g.cell_y(260)]
    fine = sum(p.grid.nx * p.grid.ny for p in sim.patches)
    assert fine < 0.1 * (600 * 600)                  # far less than a 1 m grid everywhere
    assert all(p.grid.gridsize == 1.0 for p in sim.patches)


def test_route_costs_match_a_single_grid():
    plain, both = scene(), nest(scene())
    i, j = plain.grid.cell_x(40), plain.grid.cell_y(40)
    for k in range(len(plain.ods)):
        a = plain.grid.cost_field(k)[i, j]
        b = both.grid.cost_field(k)[i, j]
        assert np.isfinite(b)
        assert abs(a - b) <= 0.02 * max(a, 1.0)       # same route cost, to within 2 %
    # and the field is continuous across a patch edge
    patch = both.patches[0]
    edge = patch.grid.cost_field(0)[0, patch.grid.ny // 2]
    x = patch.grid.xs[0] - 1.0
    outside = both.grid.cost_field(0)[both.grid.cell_x(x), both.grid.cell_y(patch.grid.ys[patch.grid.ny // 2])]
    assert abs(edge - outside) < 12.0                # about one coarse cell of walking


def test_walkers_cross_patch_edges_and_arrive():
    sim = nest(scene())
    seen = {"reached": 0, "lost": 0}
    real = Agent.die

    def die(self, reason):
        if reason == DIED_TARGET_REACHED:
            seen["reached"] += 1
        if reason == DIED_LOST:
            seen["lost"] += 1
        return real(self, reason)

    Agent.die = die
    levels = set()
    try:
        for _ in range(900):
            sim.step()
            levels.update(a.level for a in sim.agents if a.active)
    finally:
        Agent.die = real
    assert seen["reached"] > 50
    assert seen["lost"] == 0
    assert 0 in levels and max(levels) > 0            # walkers were on both kinds of grid
    assert max(p.grid.occupancy.max() for p in sim.patches) > 0
    assert sim.grid.occupancy.max() > 0


def test_a_one_metre_doorway_is_a_real_opening_in_a_patch():
    sim = scene(agents=20)
    sim.buildings.clear()
    sim.grid.set_geometry([], [], None)
    house = sim.add_building(box(300, 300, 312, 312), function="domestic",
                             wall_m=0.4, door=(306.0, 300.0), door_width_m=1.0)
    k = sim.add_od(306.0, 306.0, kind="house", name="hearth")
    nest(sim)
    level = nested.level_at(sim, 306, 306)
    g = sim.patches[level - 1].grid
    assert g.walkable[g.cell_x(306.0), g.cell_y(306.0)]           # the room
    assert not g.walkable[g.cell_x(300.0), g.cell_y(306.0)]       # the west wall
    assert g.walkable[g.cell_x(306.0), g.cell_y(300.0)]           # the doorway
    # wall cells are about a metre thick, not a coarse cell
    row = [not g.walkable[g.cell_x(x), g.cell_y(306.0)] for x in np.arange(296.5, 304.0, 1.0)]
    assert 1 <= sum(row) <= 3
    far = sim.grid.cost_field(k)[sim.grid.cell_x(40), sim.grid.cell_y(40)]
    assert np.isfinite(far)                                       # reachable from a gate
    house.door = None                                             # wall the door up
    sim._build_cost_fields()
    assert not np.isfinite(sim.grid.cost_field(k)[sim.grid.cell_x(40), sim.grid.cell_y(40)])


def test_adding_a_building_far_away_makes_a_new_patch():
    sim = nest(scene())
    before = len(sim.patches)
    assert nested.level_at(sim, 505, 105) == 0
    sim.add_building(box(500, 100, 510, 110), function="domestic")
    assert nested.level_at(sim, 505, 105) > 0
    assert len(sim.patches) == before + 1
    sim.run(20)                                       # still steps


def test_fine_cell_limit_leaves_the_rest_coarse_and_says_so():
    sim = nest(scene(), max_fine_cells=2500)          # room for one 50 m tile
    assert sum(p.grid.nx * p.grid.ny for p in sim.patches) <= 2500
    assert any("left on the coarse grid" in note for note in sim.nested_notes)


def test_bad_cell_sizes_are_refused():
    with pytest.raises(ValueError):
        nest(scene(), fine=2.0)                       # does not divide 5 m
    with pytest.raises(ValueError):
        nest(scene(), tile=52.0)                      # not a whole number of 5 m cells


def test_turning_nesting_off_restores_the_single_grid():
    plain = scene()
    plain.run(60)
    sim = nest(scene())
    sim.set_nested(None)
    assert sim.patches == [] and sim.grid.hole_mask is None
    assert np.array_equal(sim.grid.walkable, scene().grid.walkable)
    assert np.array_equal(sim.grid.cost_field(0), scene().grid.cost_field(0))


def test_nested_scene_packs_and_replays_identically():
    import json

    from pedsim import live

    def build():
        sim = nest(scene())
        sim.pack_seed = 3
        return sim

    src = build()
    g = src.grid
    frame = live.BilinearFrame.flat((g.min_x, g.min_y, g.max_x, g.max_y), 37.2, 38.9, 300, 300)
    meta, blob = live.pack_scene(src, "n", "nested", "village", frame)
    engine = live.LiveEngine()
    solved = []
    real = nested.solve
    nested.solve = lambda *a, **k: (solved.append(a[1]), real(*a, **k))[1]
    try:
        desc = engine.load(json.loads(json.dumps(meta)), blob)
    finally:
        nested.solve = real
    assert solved == []                               # every route came from the pack
    assert desc["nested"]["patches"] == len(src.patches) > 0
    direct = build()
    direct.run(150)
    engine.step(150)
    assert np.array_equal(direct.grid.occupancy, engine.sim.grid.occupancy)
    for a, b in zip(direct.patches, engine.sim.patches):
        assert np.array_equal(a.grid.occupancy, b.grid.occupancy)

    snap = engine.snapshot()
    assert len(snap["patches"]) == len(src.patches)
    first = snap["patches"][0]
    assert 0.0 <= first["x0"] < first["x1"] <= 1.0 and 0.0 <= first["y0"] < first["y1"] <= 1.0
    assert len(first["field"]) == first["nx"] * first["ny"] * 4
    # an edit on the device re-solves across both levels and adds fine ground
    c = desc["center"]
    engine.add_od(c[0] + 0.002, c[1] + 0.001, kind="destination")
    assert engine.describe()["nested"]["patches"] >= len(src.patches)
    engine.step(20)

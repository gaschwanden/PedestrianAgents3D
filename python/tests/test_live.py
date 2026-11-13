"""The live engine, the scene pack it loads, and the fast paths under it.

The engine must be the same model as the desktop one, so most of these tests
are equalities: a packed scene replays like the scene it was packed from, and
the batched vision scan gives the same arrays as the per-agent reference.
"""
import json

import numpy as np
import pytest

from pedsim import live
from pedsim.scenario import normalise, synthetic_scene
from pedsim.simulation import ANALYSIS_FACADE_VIS, Simulation

SCENARIO = {
    "scene": "synthetic", "seed": 4, "num_agents": 40, "steps": 10,
    "gridsize": 4, "extent_m": 400, "population": "", "tasks": "",
    "respect_chronology": False,
}


def make():
    sim = synthetic_scene(normalise(dict(SCENARIO)))
    sim.pack_seed = SCENARIO["seed"]
    return sim


def frame_for(sim):
    g = sim.grid
    return live.BilinearFrame.flat((g.min_x, g.min_y, g.max_x, g.max_y),
                                   37.2233, 38.9225, x0=200.0, y0=200.0)


def packed():
    sim = make()
    meta, blob = live.pack_scene(sim, "syn", "Synthetic", "village", frame_for(sim))
    return json.loads(json.dumps(meta)), blob


def test_batched_vision_matches_reference():
    fast, slow = make(), make()
    slow.batch_vision = False
    for sim in (fast, slow):
        sim.set_analysis_mode(ANALYSIS_FACADE_VIS)
        sim.run(120)
    assert np.array_equal(fast.grid.occupancy, slow.grid.occupancy)
    assert np.array_equal(fast.grid.visibility, slow.grid.visibility)
    assert np.array_equal(fast.grid.visibility_o, slow.grid.visibility_o)
    assert fast.grid.occupancy.max() > 0


def test_packed_scene_replays_identically():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    direct = make()
    # the synthetic scene has phased buildings; put both in the same state
    direct.research.phase_mode = engine.sim.research.phase_mode
    direct.apply_phase_filter()
    assert np.array_equal(direct.grid.walkable, engine.sim.grid.walkable)
    direct.run(80)
    engine.step(80)
    assert np.array_equal(direct.grid.occupancy, engine.sim.grid.occupancy)


def test_packed_cost_fields_are_used_then_dropped_on_edit():
    meta, blob = packed()
    calls = []
    real = Simulation._build_cost_fields

    engine = live.LiveEngine()
    engine.load(meta, blob)
    grid = engine.sim.grid
    solve = grid.compute_cost_field
    grid.compute_cost_field = lambda *a, **k: (calls.append(a[0]), solve(*a, **k))[1]
    engine.sim._build_cost_fields()
    assert calls == []                      # every field came from the pack
    centre = engine.describe()["center"]
    engine.add_building(
        [[centre[0] + dx, centre[1] + dy] for dx, dy in
         ((0.0, 0.0), (0.0002, 0.0), (0.0002, 0.0002), (0.0, 0.0002))])
    assert calls                            # a wall changed: routes re-solved
    assert real is Simulation._build_cost_fields


def test_georeference_round_trip():
    frame = live.BilinearFrame.flat((0, 0, 400, 400), 37.2233, 38.9225, x0=200, y0=200)
    lon, lat = frame.to_lonlat(200.0, 200.0)
    assert abs(float(lon) - 38.9225) < 1e-9 and abs(float(lat) - 37.2233) < 1e-9
    x, y = frame.to_local(*frame.to_lonlat(np.array([13.0, 390.0]), np.array([7.0, 250.0])))
    assert np.allclose(x, [13.0, 390.0], atol=1e-6) and np.allclose(y, [7.0, 250.0], atol=1e-6)
    again = live.BilinearFrame.from_dict(json.loads(json.dumps(frame.to_dict())))
    assert np.allclose(again.to_lonlat(50.0, 60.0), frame.to_lonlat(50.0, 60.0))


def test_snapshot_shapes_and_commands():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    snap = engine.command("step", {"n": 30})
    n = snap["n_agents"]
    assert n > 0
    assert len(snap["agents"]) == n * 16 and len(snap["ids"]) == n * 2
    assert len(snap["field"]) == snap["nx"] * snap["ny"] * 4 * snap["channels"]
    assert "describe" in snap                       # first snapshot describes the scene
    assert "describe" not in engine.command("step", {"n": 1})

    c = snap["describe"]["center"]
    before = len(snap["describe"]["ods"])
    snap = engine.command("addOd", {"lon": c[0] + 0.0003, "lat": c[1]})
    assert len(snap["describe"]["ods"]) == before + 1
    snap = engine.command("weightOd", {"lon": c[0] + 0.0003, "lat": c[1]})
    assert snap["describe"]["ods"][-1]["dest_weight"] == 0.25
    snap = engine.command("deleteOd", {"lon": c[0] + 0.0003, "lat": c[1]})
    assert len(snap["describe"]["ods"]) == before

    snap = engine.command("isovist", {"lon": c[0], "lat": c[1]})
    assert len(snap["isovist"]) > 8
    snap = engine.command("toggles", {"analysis": "facadeO"})
    assert snap["channels"] == 3
    with pytest.raises(ValueError):
        engine.command("nonsense")


def test_chronology_toggle_switches_phases():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    engine.set_toggles({"chronology": True, "startBc": 9500, "endBc": 9000})
    assert engine.describe()["active"] == ["GT-III"]
    engine.set_toggles({"startBc": 8500, "endBc": 8100})
    desc = engine.describe()
    assert desc["active"] == ["GT-II"]
    assert [b["active"] for b in desc["buildings"]] == [True, True, False]
    engine.set_toggles({"overrides": {"GT-III": True}})
    assert set(engine.describe()["active"]) == {"GT-III", "GT-II"}


def test_export_reloads_on_desktop_and_reset_restores():
    meta, blob = packed()
    engine = live.LiveEngine()
    first = engine.load(meta, blob)
    c = first["center"]
    engine.add_od(c[0] + 0.0004, c[1] + 0.0002, name="field note")
    saved = json.loads(json.dumps(engine.export_geometry()))

    desktop = make()
    desktop.load_geometry_dict(saved)
    assert any(od is not None and od.name == "field note" for od in desktop.ods)

    other = live.LiveEngine()
    other.load(meta, blob)
    assert len(other.apply_geometry(saved)["ods"]) == len(first["ods"]) + 1
    assert len(engine.reset()["ods"]) == len(first["ods"])


def test_set_agents():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    engine.set_toggles({"agents": 12})
    engine.step(40)
    assert engine.snapshot()["n_agents"] <= 12
    engine.set_toggles({"agents": 60})
    engine.step(40)
    assert engine.snapshot()["n_agents"] > 12


def test_dem_is_interpolated_below_source_resolution(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")
    from rasterio.transform import from_origin

    from pedsim import geo

    # A tilted plane on a 1-arc-second grid: bilinear sampling reproduces it,
    # nearest-neighbour sampling turns it into steps.
    step = 1.0 / 3600.0
    rows, cols = 60, 60
    west, north = 38.9, 37.24
    lon = west + (np.arange(cols) + 0.5) * step
    lat = north - (np.arange(rows) + 0.5) * step
    plane = (700.0 + 40000.0 * (lon[None, :] - west) + 30000.0 * (north - lat[:, None]))
    path = str(tmp_path / "dem.tif")
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=cols, count=1,
                       dtype="float32", crs="EPSG:4326",
                       transform=from_origin(west, north, step, step)) as dst:
        dst.write(plane.astype("float32"), 1)

    frame = geo.LocalFrame(north - 30 * step, west + 30 * step)
    bounds = (-150.0, -150.0, 150.0, 150.0)
    smooth = geo.load_dem([path], frame, bounds, cellsize=3.0).elevation
    stepped = geo.load_dem([path], frame, bounds, cellsize=3.0, interpolate=False).elevation
    assert (np.diff(stepped, axis=0) == 0).mean() > 0.8      # the staircase
    assert (np.diff(smooth, axis=0) == 0).mean() < 0.01      # a slope
    assert np.abs(np.diff(smooth, axis=0)).max() < np.abs(np.diff(stepped, axis=0)).max() / 3
    # coarse grids keep the old sampling, so cluster scenes do not change
    coarse = geo.load_dem([path], frame, bounds, cellsize=60.0)
    assert np.array_equal(coarse.elevation,
                          geo.load_dem([path], frame, bounds, cellsize=60.0,
                                       interpolate=False).elevation)


def test_respawn_at_origin_keeps_each_walker_home():
    sim = make()
    sim.respawn_at_origin = True
    homes = {}
    arrivals = 0
    for _ in range(600):
        sim.step()
        for k, a in enumerate(sim.agents):
            if not a.active:
                continue
            if k in homes and a.age <= 1:
                arrivals += 1
            assert homes.setdefault(k, a.home) == a.home == a.origin
    assert arrivals > 5           # walkers did finish trips and start again


def test_default_respawn_draws_a_fresh_origin():
    sim = make()
    assert sim.respawn_at_origin is False
    seen = {}
    for _ in range(600):
        sim.step()
        for k, a in enumerate(sim.agents):
            if a.active:
                seen.setdefault(k, set()).add(a.origin)
    assert any(len(v) > 1 for v in seen.values())


def test_terrain_and_river_weights_change_routes_and_return():
    from pedsim.rivers import River

    sim = make()
    # a new array, not an in-place edit: the solver caches per elevation array
    sim.grid.elevation = np.fromfunction(
        lambda i, j: 0.15 * np.abs(i - sim.grid.nx / 2) * sim.grid.gridsize,
        sim.grid.elevation.shape)
    sim.set_terrain_weight(1.0)
    base = sim.grid.cost_field(4).copy()
    sim.set_terrain_weight(2.0)
    assert np.nanmax(sim.grid.cost_field(4)[np.isfinite(base)]) > np.nanmax(base[np.isfinite(base)])
    sim.set_terrain_weight(1.0)
    assert np.array_equal(sim.grid.cost_field(4), base)

    sim.add_river([(200.0, 0.0), (200.0, 400.0)], name="test", width=12.0, crossing_cost=4.0)
    one = sim.grid.cost_field(4).copy()
    sim.set_river_weight(3.0)
    assert sim.rivers[0].crossing_cost == 4.0          # the river itself is untouched
    ok = np.isfinite(one)
    assert (sim.grid.cost_field(4)[ok] >= one[ok] - 1e-9).all()
    assert sim.grid.cost_field(4)[ok].max() > one[ok].max()
    sim.set_river_weight(1.0)
    assert np.array_equal(sim.grid.cost_field(4), one)
    assert isinstance(sim.rivers[0], River)


def test_packed_routes_are_not_used_at_other_weights():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    grid = engine.sim.grid
    calls = []
    solve = grid.compute_cost_field
    grid.compute_cost_field = lambda *a, **k: (calls.append(a[0]), solve(*a, **k))[1]
    engine.set_toggles({"terrainWeight": 2.0})
    assert calls
    assert engine.describe()["terrain_weight"] == 2.0


def test_toggles_do_not_reset_the_analysis():
    meta, blob = packed()
    engine = live.LiveEngine()
    engine.load(meta, blob)
    engine.step(60)
    peak = engine.sim.grid.occupancy.max()
    engine.set_toggles({"analysis": "path", "season": "normal"})
    assert engine.sim.grid.occupancy.max() == peak


def test_hollow_building_has_a_room_a_wall_and_a_door():
    meta, blob = packed()
    engine = live.LiveEngine()
    first = engine.load(meta, blob)
    sim = engine.sim
    g = sim.grid
    # a 40 m square room in open ground, door in the middle of its south wall
    x0, y0, x1, y1 = 260.0, 40.0, 300.0, 80.0
    ring = [engine._lonlat(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    door = engine._lonlat((280.0, y0))
    engine.add_building(ring, door=door)
    b = sim.buildings[-1]
    assert b.wall_m == 0.4 and b.door is not None

    cell = lambda x, y: (g.cell_x(x), g.cell_y(y))
    assert g.walkable[cell(280.0, 60.0)]            # the room is open
    assert not g.walkable[cell(x0, 60.0)]           # west wall
    assert not g.walkable[cell(x1, 60.0)]           # east wall
    assert not g.walkable[cell(280.0, y1)]          # north wall
    assert g.walkable[cell(280.0, y0)]              # the doorway
    # the household's place is inside, and the outside can reach it
    od = sim.ods[-1]
    assert od.kind == "house" and x0 < od.x < x1 and y0 < od.y < y1
    field = g.cell_x(od.x), g.cell_y(od.y)
    cost = g.cost_field(len(sim.ods) - 1)
    assert np.isfinite(cost[cell(20.0, 20.0)])
    # and only through the door: walling it up cuts the room off
    b.door = None
    g._rebuild_walkable()
    sim._build_cost_fields()
    assert not np.isfinite(g.cost_field(len(sim.ods) - 1)[cell(20.0, 20.0)])

    desc = engine.describe()
    drawn = desc["buildings"][-1]
    assert drawn["inner"] and len(drawn["inner"]) == len(drawn["ring"])
    saved = json.loads(json.dumps(engine.export_geometry()))
    assert saved["buildings"][-1]["wall_m"] == 0.4
    other = live.LiveEngine()
    other.load(meta, blob)
    other.apply_geometry(saved)
    assert other.sim.buildings[-1].wall_m == 0.4
    assert len(first["buildings"]) + 1 == len(desc["buildings"])

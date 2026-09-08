"""Tests for full-parity features: DXF import, buildings, editing, analysis
modes, isovist, traces, modules and IO.

Run with pytest or directly (``python python/tests/test_features.py``).
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim import (
    ANALYSIS_FACADE_VIS,
    ANALYSIS_NONE,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ModulePrototype,
    Simulation,
)
from pedsim.dxf import DXFHandler
from pedsim.geometry import (
    clockwise,
    line_poly_intersections,
    line_segment_intersection,
    split_polygon,
)

TEXT = "/workspace/text"
HAVE_DXF = os.path.exists(os.path.join(TEXT, "GSite.dxf"))


def _scene(mode=ANALYSIS_PATHOVERLAP, **kw):
    return Simulation.from_dxf(
        os.path.join(TEXT, "GSite.dxf"),
        os.path.join(TEXT, "GBuildings.dxf"),
        os.path.join(TEXT, "GObstacles.dxf"),
        os.path.join(TEXT, "GOD.txt"),
        gridsize=6.0, num_agents=60, release_rate=12, cone_vision=45,
        analysis_mode=mode, seed=1, **kw,
    )


def test_geometry_intersection_and_split():
    inter = line_segment_intersection(0, 0, 10, 0, 5, -5, 5, 5)
    assert inter is not None and abs(inter[0] - 5) < 1e-6
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    inters, edges = line_poly_intersections(square, -1, 5, 11, 5)
    assert len(inters) == 2
    a, b = split_polygon(square, inters, edges)
    assert len(a) >= 3 and len(b) >= 3
    assert clockwise([(0, 0), (10, 0), (10, 10), (0, 10)]) == 1  # CCW


def test_dxf_import_counts():
    if not HAVE_DXF:
        return
    site = DXFHandler().import_dxf(os.path.join(TEXT, "GSite.dxf"))
    assert len(site.lwpolys) + len(site.polys) >= 1
    obs = DXFHandler().import_dxf(os.path.join(TEXT, "GObstacles.dxf"))
    assert len(obs.polys) == 42
    layers = {p.layer for p in obs.polys}
    assert "OBSTACLES_LOW" in layers and "WATERBODY" in layers
    bld = DXFHandler().import_dxf(os.path.join(TEXT, "GBuildings.dxf"))
    assert len(bld.meshes) == 10
    assert all(len(m.footprint) >= 3 for m in bld.meshes)


def test_from_dxf_runs():
    if not HAVE_DXF:
        return
    sim = _scene()
    assert len(sim.buildings) == 10 and len(sim.obstacles) == 42
    assert sim.reachable_targets() >= 2
    # every OD seeds a walkable cell with a usable cost field
    for k, od in enumerate(sim.ods):
        if od is None:
            continue
        cf = sim.grid.cost_field(k)
        assert np.isfinite(cf).sum() > 10
    for _ in range(80):
        sim.step()
    assert len(sim.active_agents) > 0
    assert sim.grid.max_occupancy > 0


def test_editing_add_split_delete():
    if not HAVE_DXF:
        return
    sim = _scene()
    n0 = len(sim.buildings)
    b = sim.add_building([(300, -50), (340, -50), (340, -10), (300, -10)], height=12)
    assert len(sim.buildings) == n0 + 1
    res = sim.split_building(b, 290, -30, 350, -30)
    assert res is not None and len(sim.buildings) == n0 + 2
    sim.delete_building(res[0])
    sim.delete_building(res[1])
    assert len(sim.buildings) == n0


def test_edit_od_operations():
    if not HAVE_DXF:
        return
    sim = _scene()
    k = sim.add_od(120, 120, group=2)
    assert sim.ods[k] is not None
    sim.weight_od(k, origin_weight=0.5, dest_weight=0.0)
    assert sim.ods[k].origin_weight == 0.5 and not sim.ods[k].is_sink
    sim.move_od(k, 100, 100)
    assert np.isfinite(sim.grid.cost_field(k)).sum() > 10
    sim.delete_od(k)
    assert sim.ods[k] is None


def test_facade_visibility_accumulates():
    if not HAVE_DXF:
        return
    sim = _scene(ANALYSIS_FACADE_VIS)
    for _ in range(80):
        sim.step()
    assert sim.grid.max_visibility > 0
    assert sim.grid.max_boundary_visibility > 0


def test_traces_recorded():
    if not HAVE_DXF:
        return
    sim = _scene(ANALYSIS_TRACES)
    for _ in range(120):
        sim.step()
    assert len(sim.traces) > 0
    assert max(len(t.points) for t in sim.traces) > 5


def test_isovist_clips():
    if not HAVE_DXF:
        return
    sim = _scene(ANALYSIS_NONE)
    iso = sim.compute_isovist(0.0, 0.0, ray_length=2000.0)
    assert len(iso.polygon()) > 50
    # at least some rays are clipped shorter than the full length
    import math
    dists = [math.hypot(x - 0.0, y - 0.0) for x, y in iso.polygon()]
    assert min(dists) < 2000.0
    assert iso.area() > 0


def test_analysis_reset():
    if not HAVE_DXF:
        return
    sim = _scene(ANALYSIS_PATHOVERLAP)
    for _ in range(40):
        sim.step()
    assert sim.grid.max_occupancy > 0
    sim.reset_analysis()
    assert sim.grid.occupancy.max() == 0
    assert len(sim.active_agents) == 0


def test_save_load_ods_roundtrip():
    if not HAVE_DXF:
        return
    sim = _scene()
    n = sim.reachable_targets()
    tf = tempfile.mktemp(suffix=".txt")
    sim.save_ods(tf)
    sim2 = _scene()
    sim2.load_ods(tf)
    assert sim2.reachable_targets() == n


def test_module_rotate_snap():
    proto = ModulePrototype([[(0, 0), (10, 0), (10, 10), (0, 10)]],
                            [[(0, 0), (10, 0), (10, 10), (0, 10)]])
    sim = _scene() if HAVE_DXF else None
    from pedsim.modules import PlacedModule
    pm = PlacedModule(proto, 5, 5)
    pm.rotate_by(0.05)  # within snap tol of 0
    assert pm.rotation == 0.0
    assert pm.snap([(100, 100)], snap_dist=5000) is True
    assert (pm.x, pm.y) == (100, 100)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()

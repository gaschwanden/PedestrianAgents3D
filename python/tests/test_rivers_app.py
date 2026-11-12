"""Rivers, seasons, two-scale navigation and versioned saving."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from pedsim.app import Scale, Scene, TwoScaleApp, slug
from pedsim.od import OD
from pedsim.rivers import River, Season, build_layers, distance_field, summarise
from pedsim.simulation import Simulation


def make_sim(**kw):
    ods = [OD(30, 150, group=0, name="west"), OD(270, 150, group=0, name="east")]
    return Simulation(bounds=(0, 0, 300, 300), ods=ods, gridsize=4.0,
                      num_agents=40, seed=1, **kw)


# ------------------------------------------------------------------- rivers
def test_distance_field_is_zero_on_the_line():
    xs = np.arange(0.0, 100.0, 10.0)
    ys = np.arange(0.0, 100.0, 10.0)
    d = distance_field(xs, ys, [(0.0, 50.0), (100.0, 50.0)])
    assert d[:, 5].max() == pytest.approx(0.0)
    assert d[0, 0] == pytest.approx(50.0)


def test_channel_costs_and_banks_attract():
    xs = np.arange(0.0, 300.0, 5.0)
    ys = np.arange(0.0, 300.0, 5.0)
    r = River("test", [(150.0, 0.0), (150.0, 300.0)], width=20.0,
              crossing_cost=4.0, attraction=0.3, bank_width=40.0)
    (layer,) = build_layers(xs, ys, [r], Season.NORMAL)
    assert layer.name == "rivers"
    # positive in the channel, negative on the banks: a river both blocks and draws
    assert layer.data.max() > 0.0
    assert layer.data.min() < 0.0


def test_bank_attraction_cannot_make_walking_free():
    """A negative layer must never drive combined friction to zero -- the cost
    solvers need strictly positive edge weights."""
    sim = make_sim()
    sim.add_river([(150, 0), (150, 300)], attraction=0.9, crossing_cost=0.0)
    sim.set_layer_weight("rivers", 5.0)
    assert sim.grid.friction.min() > 0.0


def test_seasonal_river_vanishes_when_dry_and_blocks_in_flood():
    sim = make_sim()
    sim.add_river([(150, 0), (150, 300)], perennial=False)

    sim.set_season(Season.DRY)
    assert sim.grid.layers.get("rivers") is None, "a dry wadi is just ground"
    assert sim.grid.extra_blocked is None

    sim.set_season(Season.NORMAL)
    assert sim.grid.layers.get("rivers") is not None
    assert sim.grid.extra_blocked is None, "normal flow is costly, not impassable"

    sim.set_season(Season.SPRING_FLOOD)
    assert sim.grid.layers.get("flood") is not None
    assert sim.grid.extra_blocked.any()


def test_a_perennial_river_still_costs_in_the_dry_season():
    sim = make_sim()
    sim.add_river([(150, 0), (150, 300)], perennial=True)
    sim.set_season(Season.DRY)
    assert sim.grid.layers.get("rivers") is not None


def test_flooding_makes_the_far_bank_unreachable():
    sim = make_sim()
    sim.add_river([(150, 0), (150, 300)], width=24.0)
    sim.set_season(Season.NORMAL)
    reachable_normal = np.isfinite(sim.grid.cost_field(1)).sum()
    sim.set_season(Season.SPRING_FLOOD)
    reachable_flood = np.isfinite(sim.grid.cost_field(1)).sum()
    assert reachable_flood < reachable_normal / 1.5


def test_a_ford_is_the_cheap_way_across():
    sim = make_sim()
    r = sim.add_river([(150, 0), (150, 300)], width=24.0, crossing_cost=8.0,
                      attraction=0.0)
    sim.add_ford(r, 150, 40)
    cost = sim.grid.cost_field(1)          # field seeded at the east OD
    gx = sim.grid.cell_x(150.0)
    at_ford = cost[gx, sim.grid.cell_y(40.0)]
    away = cost[gx, sim.grid.cell_y(250.0)]
    assert at_ford < away


def test_season_cycles_through_all_three():
    sim = make_sim()
    seen = {sim.season}
    for _ in range(3):
        seen.add(sim.advance_season())
    assert seen == set(Season)


def test_summary_reports_what_the_season_is_doing():
    r = River("x", [(0.0, 0.0), (10.0, 0.0)])
    assert "dry" in summarise([r], Season.DRY)
    assert "impassable" in summarise([r], Season.SPRING_FLOOD)


def test_rivers_survive_a_save_load_round_trip(tmp_path):
    sim = make_sim()
    r = sim.add_river([(150, 0), (150, 300)], name="Culap", perennial=True,
                      crossing_cost=7.0)
    sim.add_ford(r, 150, 40)
    sim.set_season(Season.DRY)
    path = str(tmp_path / "geometry.json")
    sim.save_geometry_json(path)

    other = make_sim()
    other.load_geometry_json(path)
    assert [x.name for x in other.rivers] == ["Culap"]
    assert other.rivers[0].perennial and other.rivers[0].fords == [(150.0, 40.0)]
    assert other.season is Season.DRY


# ------------------------------------------------------------- versioned save
def test_saving_archives_the_previous_version(tmp_path):
    sim = make_sim()
    path = str(tmp_path / "geometry.json")

    assert sim.save_geometry_versioned(path) == "", "nothing to archive on first save"
    sim.add_river([(10, 10), (20, 20)], name="first")
    archived = sim.save_geometry_versioned(path)

    assert os.path.basename(archived) == "geometry.v001.json"
    with open(archived, encoding="utf-8") as fh:
        assert json.load(fh)["rivers"] == [], "the archive holds the *old* state"
    with open(path, encoding="utf-8") as fh:
        assert len(json.load(fh)["rivers"]) == 1


def test_old_versions_are_pruned_but_the_newest_are_kept(tmp_path):
    sim = make_sim()
    path = str(tmp_path / "geometry.json")
    for _ in range(6):
        sim.save_geometry_versioned(path, keep=3)
    names = [os.path.basename(v) for v in Simulation.list_versions(path)]
    assert names == ["geometry.v003.json", "geometry.v004.json", "geometry.v005.json"]


def test_version_numbers_do_not_collide_after_pruning(tmp_path):
    sim = make_sim()
    path = str(tmp_path / "geometry.json")
    for _ in range(4):
        sim.save_geometry_versioned(path, keep=1)
    assert Simulation.next_version_number(path) == 4


# ---------------------------------------------------------------- navigation
def test_slug_handles_turkish_names():
    assert slug("Göbeklitepe") == "gobeklitepe"
    assert slug("Nevalı Çori") == "nevali_cori"
    assert slug("Taş Tepeler cluster") == "tas_tepeler_cluster"


def build_app(tmp_path):
    cluster = Scene("cluster", Scale.CLUSTER, make_sim)
    detail = Scene("Karahantepe", Scale.SITE, make_sim, site_name="Karahantepe")
    return TwoScaleApp(cluster, {"Karahantepe": detail}, save_dir=str(tmp_path))


def test_navigation_starts_at_the_cluster_and_comes_back(tmp_path):
    app = build_app(tmp_path)
    assert app.at_cluster and app.scale is Scale.CLUSTER

    app.enter_detail("Karahantepe")
    assert not app.at_cluster
    assert app.breadcrumb() == "cluster  >  Karahantepe"

    app.back_to_cluster()
    assert app.at_cluster


def test_a_site_without_a_detailed_map_cannot_be_entered(tmp_path):
    app = build_app(tmp_path)
    assert not app.has_detail("Sefertepe")
    with pytest.raises(KeyError):
        app.enter_detail("Sefertepe")


def test_scenes_are_built_once_and_keep_their_edits(tmp_path):
    app = build_app(tmp_path)
    sim = app.enter_detail("Karahantepe")
    sim.add_river([(10, 10), (20, 20)], name="edit")
    app.back_to_cluster()
    assert app.enter_detail("Karahantepe") is sim
    assert [r.name for r in sim.rivers] == ["edit"]


def test_edits_are_tracked_per_scene(tmp_path):
    app = build_app(tmp_path)
    app.enter_detail("Karahantepe")
    app.mark_dirty()
    assert app.dirty
    app.back_to_cluster()
    assert not app.dirty, "the cluster has no unsaved edits of its own"
    assert [s.name for s in app.dirty_scenes()] == ["Karahantepe"]


def test_saving_clears_the_dirty_flag_and_writes_under_the_scene_name(tmp_path):
    app = build_app(tmp_path)
    app.enter_detail("Karahantepe")
    app.mark_dirty()
    msg = app.save_current()
    assert "karahantepe.geometry.json" in msg
    assert not app.dirty
    assert os.path.exists(tmp_path / "karahantepe.geometry.json")


def test_loading_a_scene_that_was_never_saved_says_so(tmp_path):
    app = build_app(tmp_path)
    assert "no saved geometry" in app.load_current()


def test_the_root_scene_must_be_the_cluster(tmp_path):
    with pytest.raises(ValueError):
        TwoScaleApp(Scene("x", Scale.SITE, make_sim), save_dir=str(tmp_path))

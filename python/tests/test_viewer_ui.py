"""Viewer behaviour: draw order, the terrain layer, the control pane, prompts.

Runs headless through SDL's dummy driver, so the rendered surface can be read
back pixel by pixel.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math

import numpy as np
import pytest

pygame = pytest.importorskip("pygame")

from pedsim.app import Scale, Scene, TwoScaleApp
from pedsim.od import OD
from pedsim.rivers import Season
from pedsim.simulation import Simulation
from pedsim.viewer import Viewer


def make_sim(buildings=None, **kw):
    ods = [OD(30, 150, group=0, name="west"), OD(270, 150, group=0, name="east")]
    return Simulation(bounds=(0, 0, 300, 300), ods=ods, gridsize=4.0,
                      buildings=buildings, num_agents=40, seed=1, **kw)


def make_viewer(sim=None, **kw):
    return Viewer(sim or make_sim(), width=900, height=700, **kw)


def pixels(view):
    """Screen as ``[x, y, 3]`` uint8."""
    return pygame.surfarray.array3d(view.screen)


# ------------------------------------------------------------- draw order
def test_buildings_hide_the_pedestrians_behind_them():
    """A tall building is opaque: an agent standing behind it must not show
    through the extrusion."""
    wall = [(100.0, 140.0), (200.0, 140.0), (200.0, 170.0), (100.0, 170.0)]
    sim = make_sim(buildings=[wall])
    sim.buildings[0].height = 60.0
    view = make_viewer(sim)
    view.pitch = math.radians(55)       # tilt so the facade covers ground behind
    view.fit_view()
    view.pitch = math.radians(55)

    # put an agent on the ground just behind the wall and render it
    agent = sim.agents[0]
    agent.alive = True
    agent.px = sim.grid.cell_x(150.0)
    agent.py = sim.grid.cell_y(178.0)
    sx, sy = view.to_screen(150.0, 178.0)
    view.render()

    px = pixels(view)[sx, sy]
    # the agent colour is a saturated group colour; the wall is a grey shade
    assert abs(int(px[0]) - int(px[2])) < 40, f"agent bled through the wall: {px}"


def test_the_control_pane_never_draws_over_the_map_origin():
    """The viewport excludes the top bar and the pane, so a fitted scene is
    centred in what is actually visible."""
    view = make_viewer()
    assert view.view_h == view.H - view.panel_h - view.TOP_H
    _, sy = view.to_screen(view.cx, view.cy)
    assert view.TOP_H < sy < view.H - view.panel_h


# ----------------------------------------------------------- terrain layer
def _elevated_sim():
    from pedsim.topography import Topography

    z = np.tile(np.linspace(0.0, 60.0, 75)[:, None], (1, 75))
    return make_sim(topography=Topography(z, 0.0, 0.0, 4.0))


def _painted_fraction(view):
    """Share of the viewport that is not the bare background colour."""
    view.render()
    band = pixels(view)[:, view.TOP_H + 5:view.H - view.panel_h - 5]
    bg = np.array(view.screen.get_at((view.W - 2, view.TOP_H + 2))[:3])
    return float((np.abs(band.astype(int) - bg).sum(axis=2) > 12).mean())


def test_the_relief_map_is_off_until_its_layer_is_selected():
    view = make_viewer(_elevated_sim())
    view.set_analysis_mode(0)
    assert [v["name"] for v in view.layer_views][0] == "terrain map"

    view.select_layer(-1)
    off = _painted_fraction(view)
    assert off < 0.05, "something is still painting a background"

    view.select_layer(0)
    assert _painted_fraction(view) > 0.5


def test_a_scene_without_elevation_offers_no_terrain_layer():
    view = make_viewer()
    assert "terrain map" not in [v["name"] for v in view.layer_views]


# -------------------------------------------------------------- the pane
def test_every_button_is_the_same_width_on_every_tab():
    view = make_viewer()
    widths = set()
    for tab in view.TABS:
        view.select_tab(tab)
        assert view.buttons, f"tab {tab} has no buttons"
        widths |= {b["rect"].width for b in view.buttons}
    assert widths == {view.BTN_W}


def test_a_long_layer_name_is_ellipsised_rather_than_spilling_out():
    """Layer names come from the data, so they can be any length."""
    view = make_viewer()
    short = view._fit_label("cost", view.BTN_W - 12)
    long = view._fit_label("Karahantepe structure AB walls", view.BTN_W - 12)
    assert short == "cost"
    assert long.endswith("\u2026")
    assert view.font.size(long)[0] <= view.BTN_W - 12


def test_the_pane_height_does_not_jump_between_tabs():
    view = make_viewer()
    heights = set()
    for tab in view.TABS:
        view.select_tab(tab)
        heights.add(view.panel_h)
    assert len(heights) == 1


def test_tabs_cycle_and_clicking_one_selects_it():
    view = make_viewer()
    view.select_tab("Water")
    assert view.active_tab == "Water"
    view.cycle_tab(1)
    assert view.active_tab == "Layers"
    view.cycle_tab(-1)
    assert view.active_tab == "Water"

    _, rect = view.tab_rects[0]
    view._panel_click(rect.center)
    assert view.active_tab == view.TABS[0]


def test_a_new_layer_reflows_the_pane_without_being_asked():
    view = make_viewer()
    before = len(view.layer_views)
    view.sim.add_river([(150, 0), (150, 300)])
    view.render()
    assert len(view.layer_views) > before
    assert "rivers" in [v["name"] for v in view.layer_views]


# ------------------------------------------------------------ river tools
def test_the_add_river_tool_draws_a_polyline_not_a_ring():
    view = make_viewer()
    view.tool = "rv_add"
    view.draft_poly = [(10.0, 10.0), (150.0, 150.0)]
    view.finish_draft()
    assert len(view.sim.rivers) == 1
    assert view.sim.rivers[0].path == [(10.0, 10.0), (150.0, 150.0)]
    assert view.has_unsaved


def test_a_ford_lands_on_the_river_you_clicked():
    view = make_viewer()
    r = view.sim.add_river([(150, 0), (150, 300)], width=30.0)
    view.tool = "rv_ford"
    view._handle_click(view.to_screen(152.0, 100.0))
    assert len(r.fords) == 1

    view._handle_click(view.to_screen(20.0, 20.0))
    assert len(r.fords) == 1, "a click nowhere near the channel is not a ford"


def test_the_season_button_cycles_and_reroutes():
    view = make_viewer()
    view.sim.add_river([(150, 0), (150, 300)], width=24.0)
    view._do_action("season_flood")
    assert view.sim.season is Season.SPRING_FLOOD
    assert view.sim.grid.extra_blocked.any()
    view._do_action("season_next")
    assert view.sim.season is Season.DRY


# --------------------------------------------------- navigation & prompting
def build_app(tmp_path):
    cluster = Scene("cluster", Scale.CLUSTER, make_sim)
    return TwoScaleApp(cluster, {"Karahantepe": Scene("Karahantepe", Scale.SITE, make_sim)},
                       save_dir=str(tmp_path))


def test_leaving_a_clean_scene_does_not_ask(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view._enter_site("Karahantepe")
    view._do_action("back_to_cluster")
    assert view.prompt is None and app.at_cluster


def test_leaving_a_dirty_scene_asks_first(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view._enter_site("Karahantepe")
    view.mark_dirty()

    view._do_action("back_to_cluster")
    assert view.prompt is not None
    assert not app.at_cluster, "nothing moves until the question is answered"

    view._answer(True)
    assert app.at_cluster
    assert not app.details["Karahantepe"].dirty
    assert (tmp_path / "karahantepe.geometry.json").exists()


def test_discarding_leaves_without_writing_anything(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view._enter_site("Karahantepe")
    view.mark_dirty()
    view._do_action("back_to_cluster")
    view._answer(False)
    assert app.at_cluster
    assert not (tmp_path / "karahantepe.geometry.json").exists()


def test_cancelling_stays_put(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view._enter_site("Karahantepe")
    view.mark_dirty()
    view._do_action("back_to_cluster")
    view._answer(None)
    assert not app.at_cluster and app.dirty


def test_quitting_with_unsaved_edits_asks_rather_than_discarding(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view.mark_dirty()
    view._request_quit()
    assert view.running and view.prompt is not None
    view._answer(False)
    assert not view.running


def test_swapping_scenes_resets_what_belonged_to_the_old_one(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view.draft_poly = [(1.0, 1.0)]
    view.selected_site = "Karahantepe"
    view.set_simulation(app.enter_detail("Karahantepe"))
    assert view.draft_poly == [] and view.selected_site == ""
    assert view.sim is app.current.sim()


def test_a_site_with_no_detailed_map_says_so_instead_of_opening(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view.selected_site = "Sefertepe"
    view._open_selected_site()
    assert app.at_cluster
    assert "no detailed map" in view.status_msg


def test_site_markers_are_only_drawn_at_cluster_scale(tmp_path):
    app = build_app(tmp_path)
    view = make_viewer(app.cluster.sim(), app=app)
    view.render()
    assert {n for n, _, _ in view._site_markers} == {"west", "east"}

    view.set_simulation(app.enter_detail("Karahantepe"))
    view.render()
    assert view._site_markers == []

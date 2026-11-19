"""Importing published site plans: georeferencing and sampling."""
from __future__ import annotations

import math

import numpy as np
import pytest

from pedsim.layers import BLOCK, FRICTION
from pedsim.od import OD
from pedsim.plans import ControlPoint, Georeference, SitePlan, add_plan_to
from pedsim.simulation import Simulation


def plain_plan(**kw):
    """A 100x200 white image with a black vertical bar down the middle."""
    img = np.ones((200, 100), dtype=float)
    img[:, 45:55] = 0.0
    return SitePlan(img, kw.pop("geo", Georeference(1.0, 0.0, 0.0, 0.0)), **kw)


# ------------------------------------------------------------ georeferencing
def test_two_control_points_land_exactly_where_told():
    a = ControlPoint((10.0, 10.0), (0.0, 0.0), "datum")
    b = ControlPoint((110.0, 10.0), (50.0, 0.0), "grid E50")
    geo = Georeference.from_control_points(a, b)

    assert geo.metres_per_pixel == pytest.approx(0.5)
    assert geo.rotation == pytest.approx(0.0)
    for cp in (a, b):
        wx, wy = geo.to_world(*cp.pixel)
        assert (float(wx), float(wy)) == pytest.approx(cp.world, abs=1e-9)


def test_the_image_y_axis_is_flipped_to_world_north():
    """Row numbers grow downwards in an image and northing grows upwards; a
    plan imported without the flip is mirrored, which is easy to miss."""
    geo = Georeference(1.0, 0.0, 0.0, 0.0)
    _, y_top = geo.to_world(0.0, 0.0)
    _, y_bottom = geo.to_world(0.0, 100.0)
    assert float(y_top) > float(y_bottom)


def test_a_rotated_plan_is_rotated_back():
    """A plan drawn with north 30 deg off the page edge."""
    a = ControlPoint((0.0, 0.0), (0.0, 0.0))
    # 100 px along the image x-axis lands 100 m away at 30 deg above east
    b = ControlPoint((100.0, 0.0), (100 * math.cos(math.radians(30)),
                                    100 * math.sin(math.radians(30))))
    geo = Georeference.from_control_points(a, b)
    assert math.degrees(geo.rotation) == pytest.approx(30.0)
    assert geo.metres_per_pixel == pytest.approx(1.0)


def test_round_trip_pixel_to_world_and_back():
    geo = Georeference.from_control_points(
        ControlPoint((17.0, 93.0), (412.0, -88.0)),
        ControlPoint((640.0, 240.0), (700.0, 150.0)))
    px, py = 321.0, 177.0
    wx, wy = geo.to_world(px, py)
    bx, by = geo.to_pixel(wx, wy)
    assert float(bx) == pytest.approx(px, abs=1e-6)
    assert float(by) == pytest.approx(py, abs=1e-6)


def test_scale_bar_and_north_arrow_are_enough():
    anchor = ControlPoint((50.0, 50.0), (0.0, 0.0), "centre of the trench")
    geo = Georeference.from_scale_bar(anchor, bar_pixels=200.0, bar_metres=10.0)
    assert geo.metres_per_pixel == pytest.approx(0.05)
    wx, wy = geo.to_world(*anchor.pixel)
    assert (float(wx), float(wy)) == pytest.approx((0.0, 0.0))


def test_north_arrow_bearing_is_the_image_up_direction():
    anchor = ControlPoint((0.0, 0.0), (0.0, 0.0))
    geo = Georeference.from_scale_bar(anchor, 100.0, 100.0, north_deg=90.0)
    # image up now points east, so a pixel one row *above* the anchor is east
    wx, wy = geo.to_world(0.0, -1.0)
    assert float(wx) == pytest.approx(1.0)
    assert float(wy) == pytest.approx(0.0, abs=1e-9)
    assert geo.north_deg == pytest.approx(90.0)


def test_degenerate_control_points_are_refused():
    same_pixel = ControlPoint((5.0, 5.0), (0.0, 0.0))
    with pytest.raises(ValueError):
        Georeference.from_control_points(same_pixel, ControlPoint((5.0, 5.0), (9.0, 9.0)))
    with pytest.raises(ValueError):
        Georeference.from_control_points(same_pixel, ControlPoint((90.0, 5.0), (0.0, 0.0)))


def test_a_bad_scale_bar_is_refused():
    anchor = ControlPoint((0.0, 0.0), (0.0, 0.0))
    with pytest.raises(ValueError):
        Georeference.from_scale_bar(anchor, 0.0, 10.0)
    with pytest.raises(ValueError):
        Georeference.from_scale_bar(anchor, 100.0, -1.0)


def test_check_measures_error_against_a_point_the_fit_never_saw():
    geo = Georeference.from_control_points(
        ControlPoint((0.0, 0.0), (0.0, 0.0)),
        ControlPoint((100.0, 0.0), (100.0, 0.0)))
    assert geo.check([ControlPoint((50.0, 0.0), (50.0, 0.0))]) == pytest.approx(0.0)
    # a third point 3 m off the fitted line is reported as 3 m of error
    assert geo.check([ControlPoint((50.0, 0.0), (53.0, 0.0))]) == pytest.approx(3.0)


# -------------------------------------------------------------------- plans
def test_colour_and_byte_images_are_normalised_on_load():
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[..., :] = 255
    plan = SitePlan(rgb, Georeference(1.0, 0.0, 0.0, 0.0))
    assert plan.image.shape == (4, 4)
    assert plan.image.max() <= 1.0 and plan.image.min() >= 0.0
    assert plan.coverage() == 0.0, "a blank white sheet has no ink"


def test_ink_is_the_dark_part():
    plan = plain_plan()
    assert plan.ink().sum() == 200 * 10
    assert plan.coverage() == pytest.approx(0.1)   # 10 of 100 columns


def test_ground_size_follows_the_scale():
    plan = plain_plan(geo=Georeference(0.25, 0.0, 0.0, 0.0))
    w, h = plan.ground_size()
    assert (w, h) == pytest.approx((25.0, 50.0))


def test_world_bounds_grow_when_the_plan_is_rotated():
    upright = plain_plan().world_bounds()
    turned = plain_plan(geo=Georeference(1.0, math.radians(45), 0.0, 0.0)).world_bounds()
    assert (turned[2] - turned[0]) > (upright[2] - upright[0])


def test_sampling_puts_the_ink_where_the_georeference_says():
    """The bar runs down image columns 45-54; at 1 m/px anchored at the origin
    it should land in a 10 m wide strip on the ground."""
    plan = plain_plan()
    xs = np.arange(0.0, 100.0, 1.0)
    ys = np.arange(-199.0, 1.0, 1.0)
    mask = plan.sample(xs, ys)
    hit_cols = np.where(mask.any(axis=1))[0]
    assert xs[hit_cols].min() == pytest.approx(45.0)
    assert xs[hit_cols].max() == pytest.approx(54.0)


def test_cells_outside_the_plan_are_not_walls():
    """A plan describes only the ground it covers; beyond its edge the answer is
    'unknown', which must not be imported as 'open'."""
    plan = plain_plan()
    xs = np.arange(500.0, 600.0, 1.0)      # far away from the image
    ys = np.arange(500.0, 600.0, 1.0)
    assert not plan.sample(xs, ys).any()
    assert not plan.covered(xs, ys).any()


def test_coverage_distinguishes_empty_from_unmapped():
    plan = plain_plan()
    xs = np.arange(0.0, 200.0, 1.0)         # runs off the right edge at x=100
    ys = np.arange(-100.0, 0.0, 1.0)
    covered = plan.covered(xs, ys)
    assert covered[:100].all()
    assert not covered[100:].any()


# ------------------------------------------------------------------- layers
def make_sim():
    # ODs north and south of the wall, so crossing it is the whole journey
    ods = [OD(150, 20, group=0), OD(150, 280, group=0)]
    return Simulation(bounds=(0, 0, 300, 300), ods=ods, gridsize=4.0,
                      num_agents=30, seed=1)


def wall_plan():
    """A wall across a 300x300 m scene, with a gateway at its east end."""
    img = np.ones((300, 300), dtype=float)
    img[140:160, 0:240] = 0.0          # rows 140-160 -> y 140-160; x 0-240
    return SitePlan(img, Georeference(1.0, 0.0, 0.0, 300.0), name="trench",
                    source="Test et al. 2026 fig. 1")


def test_an_imported_plan_blocks_movement():
    sim = make_sim()
    layer = add_plan_to(sim, wall_plan())
    assert layer.kind == BLOCK
    assert sim.grid.extra_blocked.any()
    assert not sim.grid.walkable[sim.grid.cell_x(100.0), sim.grid.cell_y(150.0)]


def test_the_gateway_is_still_walkable_and_carries_the_route():
    sim = make_sim()
    add_plan_to(sim, wall_plan())
    assert sim.grid.walkable[sim.grid.cell_x(270.0), sim.grid.cell_y(150.0)]

    cost = sim.grid.cost_field(1)
    assert np.isfinite(cost[sim.grid.cell_x(150.0), sim.grid.cell_y(20.0)]), \
        "the far OD must still be reachable, the long way round"
    # and the cheap way across is through the gateway, not through the wall
    through_gate = cost[sim.grid.cell_x(270.0), sim.grid.cell_y(150.0)]
    assert np.isfinite(through_gate)


def test_importing_as_rough_going_costs_without_blocking():
    sim = make_sim()
    layer = add_plan_to(sim, wall_plan(), blocking=False, cost=4.0)
    assert layer.kind == FRICTION
    assert sim.grid.extra_blocked is None
    assert sim.grid.friction.max() == pytest.approx(5.0)


def test_an_imported_layer_can_be_switched_off_again():
    """An imported plan is an interpretation, so it must stay removable."""
    sim = make_sim()
    add_plan_to(sim, wall_plan())
    blocked = sim.grid.walkable.sum()
    sim.grid.layers.remove("trench walls")
    sim.refresh_layers(force=True)
    assert sim.grid.walkable.sum() > blocked


def test_the_layer_remembers_where_it_came_from():
    sim = make_sim()
    layer = add_plan_to(sim, wall_plan())
    assert "Test et al. 2026" in layer.description

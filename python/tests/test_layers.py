"""Tests for the weighted landscape layers, the friction-weighted flood fill and
the directional (up/down) slope cost.

Run with pytest or directly (``python python/tests/test_layers.py``).
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim.grid import NavGrid
from pedsim.layers import BLOCK, INFO, Layer, LayerStack
from pedsim.od import OD
from pedsim.simulation import Simulation
from pedsim.topography import TerrainCost, Topography


def _band(shape, j0, j1, value=1.0):
    a = np.zeros(shape)
    a[:, j0:j1] = value
    return a


# --------------------------------------------------------------- layer stack
def test_stack_combines_weights_additively():
    stack = LayerStack((10, 10))
    stack.add(Layer("a", np.full((10, 10), 0.5), weight=2.0))
    stack.add(Layer("b", np.full((10, 10), 1.0), weight=0.5))
    # 1 + 2*0.5 + 0.5*1.0
    assert np.allclose(stack.friction(), 2.5)


def test_zero_weight_disables_layer():
    stack = LayerStack((10, 10))
    stack.add(Layer("a", np.ones((10, 10)), weight=0.0))
    assert stack.friction() is None      # nothing active -> plain BFS
    stack.set_weight("a", 1.0)
    assert np.allclose(stack.friction(), 2.0)


def test_info_layer_never_routes():
    stack = LayerStack((10, 10))
    stack.add(Layer("elev", np.ones((10, 10)), kind=INFO, weight=5.0))
    assert stack.friction() is None
    assert stack.blocked() is None


def test_infinite_friction_and_block_layers_are_impassable():
    stack = LayerStack((10, 10))
    d = np.zeros((10, 10))
    d[3, 3] = np.inf
    stack.add(Layer("gorge", d))
    stack.add(Layer("wall", _band((10, 10), 7, 8), kind=BLOCK))
    blocked = stack.blocked()
    assert blocked[3, 3] and blocked[0, 7] and not blocked[0, 0]


def test_version_bumps_on_change():
    stack = LayerStack((4, 4))
    v0 = stack.version
    stack.add(Layer("a", np.zeros((4, 4))))
    assert stack.version > v0
    v1 = stack.version
    stack.set_weight("a", 3.0)
    assert stack.version > v1


def test_wrong_shape_rejected():
    stack = LayerStack((10, 10))
    try:
        stack.add(Layer("bad", np.zeros((5, 5))))
    except ValueError:
        return
    raise AssertionError("expected ValueError for mismatched layer shape")


def test_normalise_preserves_inf():
    lyr = Layer("x", np.array([[0.0, 5.0], [10.0, np.inf]])).normalise()
    assert lyr.data[0, 0] == 0.0 and lyr.data[1, 0] == 1.0
    assert np.isinf(lyr.data[1, 1])


def test_adjust_weight_clamps():
    lyr = Layer("x", np.zeros((2, 2)), weight=1.0, weight_step=0.5, max_weight=2.0)
    assert lyr.adjust_weight(1) == 1.5
    assert lyr.adjust_weight(10) == 2.0
    assert lyr.adjust_weight(-100) == 0.0


# ---------------------------------------------------------------- navigation
def test_grid_layer_changes_walkability():
    g = NavGrid((0, 0, 200, 200), 4.0)
    assert g.walkable[:, 30].all()
    g.add_layer(Layer("wall", _band((g.nx, g.ny), 30, 31), kind=BLOCK))
    assert not g.walkable[:, 30].any()
    g.layers.set_weight("wall", 0.0)
    g.refresh_layers()
    assert g.walkable[:, 30].all()


def test_friction_increments_cost_by_more_than_one():
    """The weighted flood fill must charge friction, not 1, per cell."""
    g = NavGrid((0, 0, 200, 200), 4.0)
    rng = np.random.default_rng(0)
    plain = g.compute_cost_field(0, 100.0, 4.0, rng)

    g.add_layer(Layer("mire", np.full((g.nx, g.ny), 1.0), weight=2.0))
    g.clear_cost_fields()
    thick = g.compute_cost_field(0, 100.0, 4.0, np.random.default_rng(0))

    far = (25, 45)
    assert np.isfinite(plain[far]) and np.isfinite(thick[far])
    # friction 3.0 everywhere -> roughly 3x the cost of open going
    assert thick[far] > 2.5 * plain[far]


def test_agents_funnel_through_a_ford():
    """A cheap gap in an expensive river should pull traffic off the straight
    line and concentrate the crossings there."""
    ods = [OD(150, 20, group=0), OD(150, 280, group=0)]   # straight line at x=150
    sim = Simulation(bounds=(0, 0, 300, 300), ods=ods, gridsize=4.0,
                     num_agents=150, seed=3)
    g = sim.grid
    river = _band((g.nx, g.ny), 34, 40, 1.0)
    river[20:26, 34:40] = 0.05                            # ford away at x~90
    sim.add_layer(Layer("river", river, weight=40.0, max_weight=60.0))
    for _ in range(500):
        sim.step()

    crossings = g.occupancy[:, 36]        # mid-channel column
    ford = crossings[20:26].mean()
    elsewhere = np.delete(crossings, np.s_[20:26]).mean()
    assert ford > 0, "nobody crossed the river at all"
    assert ford > 5 * elsewhere, f"ford {ford:.2f} vs elsewhere {elsewhere:.2f}"


def test_layer_weight_change_invalidates_cost_fields():
    ods = [OD(20, 20, group=0), OD(280, 280, group=0)]
    sim = Simulation(bounds=(0, 0, 300, 300), ods=ods, gridsize=4.0, seed=1)
    g = sim.grid
    sim.add_layer(Layer("mire", np.ones((g.nx, g.ny)), weight=1.0))
    before = float(g.cost_field(1)[5, 5])
    sim.set_layer_weight("mire", 4.0)
    after = float(g.cost_field(1)[5, 5])
    assert after > before


# --------------------------------------------------------------- directional
def test_step_cost_is_asymmetric_up_vs_down():
    tc = TerrainCost()
    up = tc.step_cost(+5.0, 10.0)
    down = tc.step_cost(-5.0, 10.0)
    flat = tc.step_cost(0.0, 10.0)
    assert up > flat > 0
    assert down != up, "walking up and down must not cost the same"
    # Tobler's optimum is a gentle descent, so a slight downhill beats flat
    assert tc.step_cost(-0.5, 10.0) < flat


def test_directional_impassability_limits():
    tc = TerrainCost(max_ascent_slope=0.3, max_descent_slope=0.9)
    assert not np.isfinite(tc.step_cost(+4.0, 10.0))   # 0.4 up  -> blocked
    assert np.isfinite(tc.step_cost(-4.0, 10.0))       # 0.4 down -> fine
    assert not np.isfinite(tc.step_cost(-10.0, 10.0))  # 1.0 down -> blocked


def test_dijkstra_uses_walking_direction():
    """A cost field seeded downhill must be cheaper to reach than one seeded
    uphill, because the agent walks toward the seed."""
    zz = np.tile(np.linspace(0.0, 60.0, 51)[:, None], (1, 51))  # ramp along x
    topo = Topography(zz, 0.0, 0.0, 4.0)
    g = NavGrid((0, 0, 200, 200), 4.0, topography=topo,
                terrain_cost=TerrainCost())
    downhill = g.compute_cost_field(0, 4.0, 100.0)     # seed at the low end
    g.clear_cost_fields()
    uphill = g.compute_cost_field(1, 196.0, 100.0)     # seed at the high end
    probe = (25, 25)
    assert np.isfinite(downhill[probe]) and np.isfinite(uphill[probe])
    assert downhill[probe] < uphill[probe]


def test_friction_scales_slope_cost_too():
    zz = np.tile(np.linspace(0.0, 20.0, 51)[:, None], (1, 51))
    topo = Topography(zz, 0.0, 0.0, 4.0)
    g = NavGrid((0, 0, 200, 200), 4.0, topography=topo, terrain_cost=TerrainCost())
    base = g.compute_cost_field(0, 4.0, 100.0)[40, 25]
    g.add_layer(Layer("scrub", np.ones((g.nx, g.ny)), weight=1.0))
    rough = g.compute_cost_field(0, 4.0, 100.0)[40, 25]
    assert rough > 1.8 * base


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()

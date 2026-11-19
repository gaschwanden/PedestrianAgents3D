"""Circle / rectangle buildings with a door OD."""
from __future__ import annotations

import math

from pedsim.od import OD
from pedsim.simulation import Simulation
from pedsim.templates import (
    circle_polygon, entrance_from_door, place_templated_building, rect_polygon,
)


def _sim():
    return Simulation(
        bounds=(0, 0, 200, 200),
        ods=[OD(20, 20, name="a"), OD(180, 180, name="b")],
        gridsize=10, num_agents=0, seed=1,
    )


def test_circle_and_rect_polygons():
    ring = circle_polygon(50, 50, 10, n=16)
    assert len(ring) == 16
    assert abs(math.hypot(ring[0][0] - 50, ring[0][1] - 50) - 10) < 1e-9
    box = rect_polygon(10, 20, 40, 60)
    assert box == [(10, 20), (40, 20), (40, 60), (10, 60)]


def test_place_circle_creates_building_and_entrance_od():
    sim = _sim()
    before = len([o for o in sim.ods if o is not None])
    building, od = place_templated_building(
        sim, "circle", (80, 80), (90, 80), (95, 80),
        function="domestic",
    )
    assert building.function == "domestic"
    assert len(building.footprint.as_xy()) >= 8
    assert building.contains(80, 80)
    assert not building.contains(od.x, od.y)
    assert od.kind == "house"
    assert "entrance" in od.tags and "door" in od.tags
    assert len([o for o in sim.ods if o is not None]) == before + 1


def test_place_rect_door_is_outside():
    sim = _sim()
    building, od = place_templated_building(
        sim, "rect", (40, 40), (70, 60), (55, 35),
    )
    assert building.contains(55, 50)
    assert not building.contains(od.x, od.y)
    # door was on the south side → entrance should be south of the building
    assert od.y < 40


def test_entrance_from_door_prefers_nearest_facade():
    sim = _sim()
    building, _ = place_templated_building(
        sim, "rect", (0, 0), (20, 10), (10, -1),
    )
    east = entrance_from_door(building, 25, 5, offset_m=2)
    assert east[0] > 20

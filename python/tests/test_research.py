"""Chronology, scenarios, phases, population, calendar and the trip rule."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from pedsim.building import Building
from pedsim.chronology import (
    Interval, active, co_occupied, overlap_years, pair_matrix,
)
from pedsim.od import OD
from pedsim.phases import Phase, inhabitants
from pedsim.population import load_factor, load_population
from pedsim.scenario import load_scenario, run_scenario
from pedsim.simulation import Simulation


class _Site:
    def __init__(self, name, start, end, sd_s=None, sd_e=None):
        self.name = name
        self.start_bc = start
        self.end_bc = end
        self.start_bc_sd = sd_s
        self.end_bc_sd = sd_e
        self.pin = None


def test_co_occupation_closes_a_500_year_gap_at_tau_250():
    a = _Site("A", 9500, 9000)
    b = _Site("B", 8500, 8000)
    window = Interval(7000, 10000)
    for tau in (0, 100, 249):
        assert co_occupied(a, b, window, tau) is False
    assert co_occupied(a, b, window, 250) is True
    # nested, partial, disjoint
    wide = Interval(7000, 10000)
    assert overlap_years(_Site("n1", 9500, 8000), _Site("n2", 9000, 8500), wide) == 501
    assert overlap_years(_Site("p1", 9500, 8000), _Site("p2", 10000, 9000), wide) == 501
    assert overlap_years(a, b, wide, tau=0) == 0


def test_pair_matrix_shape_and_diagonal():
    sites = [_Site("A", 9500, 9000), _Site("B", 8500, 8000)]
    mask, weights = pair_matrix(sites, Interval(7000, 10000), tau=0)
    assert mask.shape == (2, 2)
    assert mask[0, 0] and mask[1, 1]
    assert not mask[0, 1]
    assert weights[0, 0] > 0


def test_undated_sites_stay_out_until_the_policy_says_otherwise():
    undated = _Site("Yoğunburç", None, None)
    window = Interval(8000, 9000)
    assert active(undated, window, undated_policy="exclude") is False
    assert active(undated, window, undated_policy="include") is True
    assert active(undated, window, undated_policy="include_flagged") is True


def test_pin_keeps_a_site_active_outside_its_dates():
    site = _Site("Göbeklitepe", 9500, 8000)
    window = Interval(7000, 7400)
    assert active(site, window) is False
    assert active(site, window, pins={"Göbeklitepe": "always_on"}) is True


def _three_sites():
    ods = [
        OD(10, 10, name="Göbeklitepe", site="Göbeklitepe"),
        OD(80, 10, name="Karahantepe", site="Karahantepe"),
        OD(40, 80, name="Gürcütepe", site="Gürcütepe"),
    ]
    return Simulation(bounds=(0, 0, 100, 100), ods=ods, gridsize=10,
                      num_agents=0, seed=1)


def _count(sim, n=2000):
    counts = {(i, j): 0 for i in range(3) for j in range(3)}
    for _ in range(n):
        trip = sim.draw_trip()
        assert trip is not None
        counts[trip] += 1
    return counts


def test_chronology_blocks_gurcutepe_in_a_ppna_window():
    sim = _three_sites()
    sim.research.respect_chronology = True
    sim.research.window = Interval(9400, 9600)
    counts = _count(sim)
    for (i, j), n in counts.items():
        if i == 2 or j == 2:
            assert n == 0
    assert sum(counts.values()) == 2000

    sim.research.respect_chronology = False
    counts_off = _count(sim, n=800)
    assert sum(n for (i, j), n in counts_off.items() if i == 2 or j == 2) > 0


def test_same_scenario_and_seed_are_bit_identical(tmp_path):
    path = os.path.join(os.path.dirname(__file__), "..", "data", "config",
                        "scenario_synthetic.yaml")
    a = run_scenario(path, out_dir=str(tmp_path / "a"))
    b = run_scenario(path, out_dir=str(tmp_path / "b"))
    assert a.record["scenario_hash"] == b.record["scenario_hash"]
    assert np.array_equal(a.occupancy, b.occupancy)
    assert os.path.exists(os.path.join(a.directory, "run.json"))


def test_an_unknown_scenario_key_is_named():
    from pedsim.scenario import normalise
    with pytest.raises(ValueError, match="not_a_key"):
        normalise({"not_a_key": 1})


def test_old_geometry_loads_and_round_trips_phases(tmp_path):
    sim = Simulation(
        bounds=(0, 0, 80, 80), gridsize=4, num_agents=0, seed=1,
        ods=[OD(10, 10, name="a"), OD(60, 10, name="b")],
        buildings=[Building.from_polygon(
            [(10, 10), (30, 10), (30, 30), (10, 30)],
            phase_ids=["GT-II"], function="domestic",
        )],
    )
    sim.research.phases = [
        Phase("GT-III", "Layer III", 9500, 8800, source="VERIFY", confidence="inferred"),
        Phase("GT-II", "Layer II", 8800, 8000, source="", confidence="assumption"),
    ]
    path = tmp_path / "scene.geometry.json"
    sim.save_geometry_json(str(path))
    raw = json.loads(path.read_text())
    assert raw["format"] == 3
    assert raw["phases"][0]["id"] == "GT-III"
    assert raw["buildings"][0]["phase_ids"] == ["GT-II"]
    # a format-2 file has no phase fields
    old = {
        "format": 2,
        "buildings": [{"polygon": [[10, 10], [30, 10], [30, 30], [10, 30]], "height": 4, "layer": ""}],
        "obstacles": [],
        "ods": ["OD,10,10,0,1,1,0"],
    }
    old_path = tmp_path / "old.json"
    old_path.write_text(json.dumps(old))
    sim.load_geometry_json(str(old_path))
    assert sim.buildings[0].phase_ids == []
    assert sim.buildings[0].function == "unknown"


def test_phase_toggle_restores_the_walkable_hash():
    wall = Building.from_polygon(
        [(8, 8), (28, 8), (28, 28), (8, 28)], phase_ids=["GT-II"], function="domestic",
    )
    sim = Simulation(
        bounds=(0, 0, 60, 60), gridsize=2, num_agents=0, seed=1,
        ods=[OD(4, 40, name="a"), OD(50, 40, name="b")],
        buildings=[wall],
    )
    sim.research.phases = [
        Phase("GT-II", "Layer II", 8800, 8000),
        Phase("GT-III", "Layer III", 9500, 8800),
    ]
    sim.apply_phase_filter()
    both = sim.grid.walkable.tobytes()
    sim.research.set_manual_phases(["GT-III"])
    sim.apply_phase_filter()
    assert sim.grid.walkable.tobytes() != both
    sim.research.set_manual_phases(["GT-II", "GT-III"])
    sim.apply_phase_filter()
    assert sim.grid.walkable.tobytes() == both


def test_by_time_activates_the_phase_the_window_meets():
    sim = Simulation(
        bounds=(0, 0, 40, 40), gridsize=4, num_agents=0, seed=1,
        ods=[OD(4, 4), OD(30, 30)],
    )
    sim.research.phases = [
        Phase("GT-III", "III", 9500, 8800),
        Phase("GT-II", "II", 8800, 8000),
    ]
    sim.research.phase_mode = "by_time"
    sim.research.window = Interval(8300, 8500)
    assert sim.research.current_phase_ids() == ["GT-II"]


def test_twenty_houses_make_one_hundred_people():
    houses = [
        Building.from_polygon(
            [(i * 12, 0), (i * 12 + 8, 0), (i * 12 + 8, 8), (i * 12, 8)],
            function="domestic", phase_ids=["GT-II"],
        )
        for i in range(20)
    ]
    assert inhabitants(houses, ["GT-II"], rule="per_house", persons_per_house=5) == 100
    assert inhabitants(houses, ["GT-III"], rule="per_house", persons_per_house=5) == 0


def test_class_shares_and_a_loaded_child_is_slower():
    pop = load_population()
    agents = [type("A", (), {"pclass": "", "speed_factor": 1.0})() for _ in range(10000)]
    counts = pop.assign(agents, np.random.default_rng(0))
    for spec in pop.classes:
        assert abs(counts[spec.id] / 10000 - spec.share) <= 0.01
    assert load_factor(8, 8, k=0.2) < load_factor(0, 8, k=0.2)
    assert "assumption" in " ".join(pop.badges()).lower() or pop.badges()


def test_child_water_stays_inside_two_kilometres():
    from pedsim.tasks import Task, TaskModel

    near = OD(100, 700, name="cistern", kind="water", tags=["cistern"], dest_weight=1, origin_weight=0)
    far = OD(100, 4000, name="stream", kind="water", tags=["stream"], dest_weight=1, origin_weight=0)
    home = OD(100, 100, name="house", kind="house", origin_weight=1, dest_weight=0)
    sim = Simulation(bounds=(0, 0, 5000, 5000), ods=[home, near, far], gridsize=50,
                     num_agents=1, seed=2)
    sim.population = load_population()
    sim.population.assign(sim.agents, sim.rng)
    # force the single agent to be a child
    sim.agents[0].pclass = "child"
    model = TaskModel([Task("water", "fetch", "water", ["child"], load_kg=8)])
    found = model._candidates(sim, 0, model.tasks[0], max_range_m=2000)
    assert found
    assert all(idx == 1 for _m, idx in found)
    model2 = TaskModel([Task("water", "fetch", "water", ["child"])])
    none = model2._candidates(sim, 0, model2.tasks[0], max_range_m=10)
    assert none == []


def test_august_is_dry_and_daylight_matches_the_solstices():
    from pedsim.calendar import load_calendar, solstice_minutes
    from pedsim.rivers import Season

    cal = load_calendar()
    assert cal.month(8).river_season is Season.DRY
    assert cal.month(3).river_season is Season.SPRING_FLOOD
    ends = solstice_minutes()
    assert abs(ends["winter"] - 580) <= 10
    assert abs(ends["summer"] - 880) <= 10
    assert cal.event_factor(8, "Göbeklitepe") == pytest.approx(1.4)
    assert cal.event_factor(1, "Göbeklitepe") == pytest.approx(1.0)

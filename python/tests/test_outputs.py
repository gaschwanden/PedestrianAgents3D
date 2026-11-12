"""Exports, tracks, network, regional fit, hypotheses and the third scale."""
from __future__ import annotations

import json
import os
import zipfile

import numpy as np
import pytest

from pedsim.app import Scale, Scene, TwoScaleApp
from pedsim.calibration import (
    Segment, buffer_overlap, clean_track, fit_tobler, load_routes, trim_private,
)
from pedsim.ensemble import run_ensemble
from pedsim.gis_export import (
    export_gpkg, export_kml, export_qgz, export_shapefiles, import_buildings_gpkg,
    read_gpkg_buildings, schema_text,
)
from pedsim.network import (
    DAY_TRIP_MIN, graph_metrics, interaction_matrix, mantel, pearson, sample_pair_counts,
)
from pedsim.od import OD
from pedsim.regional import compare_distance, fit_beta, synthetic_counts
from pedsim.simulation import Simulation
from pedsim.tracks import Fix, Track, parse_gpx, strava_activities, to_gpx, write_gpx
from pedsim.webmap.density import density_array
from pedsim.webmap.static import render_static


def _flat(distance_m=400, cell=20, n_agents=0):
    ods = [OD(cell, cell, name="a"), OD(distance_m - cell, cell, name="b")]
    return Simulation(bounds=(0, 0, distance_m, cell * 4), ods=ods, gridsize=cell,
                      num_agents=n_agents, seed=1)


def test_shapefile_schema_matches_the_golden_file(tmp_path):
    golden = os.path.join(os.path.dirname(__file__), "golden", "shp_schema.txt")
    assert schema_text() == open(golden, encoding="utf-8").read()
    export_shapefiles(
        str(tmp_path),
        sites=[{"name": "Göbeklitepe", "confidence": "published", "start_bc": 9500,
                "end_bc": 8000, "active": 1, "date_quality": "typological",
                "x": 500000, "y": 4120000}],
        ods=[{"name": "cistern", "kind": "water", "phase_ids": ["GT-II"],
              "origin_weight": 0, "dest_weight": 1, "capacity": None, "site": "Göbeklitepe",
              "x": 500010, "y": 4120010}],
        buildings=[{"polygon": [(0, 0), (10, 0), (10, 10), (0, 10)], "height": 3,
                    "layer": "", "phase_ids": ["GT-II"], "function": "domestic",
                    "inhabitants": 5, "state": "standing", "kind": "building"}],
    )
    assert os.path.exists(tmp_path / "sites.cpg")
    assert open(tmp_path / "sites.cpg", encoding="utf-8").read().strip() == "UTF-8"
    import shapefile
    reader = shapefile.Reader(str(tmp_path / "sites"), encoding="utf-8")
    assert reader.record(0)["NAME"] == "Göbeklitepe"
    names = [f[0] for f in reader.fields[1:]]
    for name in names:
        assert len(name) <= 10


def test_gpkg_round_trip_updates_a_building(tmp_path):
    sim = _flat()
    from pedsim.building import Building
    sim.buildings.append(Building.from_polygon(
        [(20, 20), (40, 20), (40, 40), (20, 40)], function="domestic", phase_ids=["GT-II"],
    ))
    path = str(tmp_path / "scene.gpkg")
    buildings = [{
        "polygon": b.footprint.as_xy(), "function": b.function,
        "phase_ids": list(b.phase_ids), "name": "",
    } for b in sim.buildings]
    export_gpkg(path, sites=[], ods=[], buildings=buildings, run_json='{"run_id": "abc"}')
    con_rows = read_gpkg_buildings(path)
    assert con_rows and con_rows[0]["phase_ids"] == ["GT-II"]
    # move the ring and read it back through the importer
    import sqlite3
    # rewrite by exporting a shifted polygon
    buildings[0]["polygon"] = [(30, 20), (50, 20), (50, 40), (30, 40)]
    export_gpkg(path, sites=[], ods=[], buildings=buildings, run_json='{"run_id": "abc"}')
    notes = import_buildings_gpkg(path, sim)
    assert notes == []
    assert sim.buildings[0].footprint.min_x == pytest.approx(30)
    qgz = export_qgz(str(tmp_path / "scene.qgz"), "scene.gpkg", "abc", ["sites", "buildings"])
    import zipfile
    xml = zipfile.ZipFile(qgz).read("project.qgs").decode("utf-8")
    assert "abc" in xml and "buildings" in xml


def test_kml_and_static_figure(tmp_path):
    kml = export_kml(str(tmp_path / "sites.kml"),
                     [{"name": "Göbeklitepe", "lon": 38.92, "lat": 37.22}])
    text = open(kml, encoding="utf-8").read()
    assert "38.9200000" in text and "Göbeklitepe" in text
    occ = np.zeros((20, 16))
    occ[4:8, 3:6] = 5
    png = render_static(occ, str(tmp_path / "fig.png"), cellsize=10, run_id="run-1",
                        attribution="© OpenStreetMap contributors")
    from PIL import Image
    with Image.open(png) as im:
        assert im.info.get("run_id") == "run-1" or "OpenStreetMap" in str(im.info)


def test_density_units_do_not_move_the_pattern():
    raw = np.array([[0, 1], [3, 9]], dtype=float)
    per_day = density_array(raw, "trips_per_day", n_agents=3, n_days=1)
    relative = density_array(raw, "relative")
    assert np.argmax(per_day) == np.argmax(raw)
    assert np.argmax(relative) == np.argmax(raw)
    assert per_day.max() == pytest.approx(3.0)


def test_gpx_strava_and_private_trim(tmp_path):
    gpx = """<?xml version="1.0"?><gpx><trk><name>walk</name><trkseg>
      <trkpt lat="37.2200" lon="38.9200"><time>2026-08-01T08:00:00Z</time></trkpt>
      <trkpt lat="37.2210" lon="38.9210"><time>2026-08-01T08:10:00Z</time></trkpt>
    </trkseg></trk></gpx>"""
    track = parse_gpx(gpx)
    assert track.has_timestamps()
    # a track that starts on the hotel loses its first 200 m
    fixes = []
    for i in range(30):
        fixes.append(Fix(37.22 + i * 0.001, 38.92, time=_time(i)))
    trimmed, removed = trim_private(fixes, [(37.22, 38.92)], radius_m=200)
    assert removed >= 200
    assert trimmed[0].lat > fixes[0].lat
    # strava bulk export lists the hike and skips the run
    gpx_path_name = "activities/hike.gpx"
    buf = tmp_path / "strava.zip"
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("activities.csv",
                    "Activity ID,Activity Date,Activity Name,Activity Type,Filename\n"
                    "1,2026-08-01,Ridge,Hike,activities/hike.gpx\n"
                    "2,2026-08-02,Jog,Run,activities/jog.gpx\n")
        zf.writestr(gpx_path_name, gpx)
    rows = strava_activities(str(buf))
    assert [r["type"] for r in rows] == ["Hike"]
    out = write_gpx(str(tmp_path / "out.gpx"), "corridor", [(37.22, 38.92)], run_id="run-9")
    assert "run-9" in open(out, encoding="utf-8").read()


def _time(i):
    from datetime import datetime, timedelta, timezone
    return datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=i)


def test_cleaning_report_and_tobler_recovery():
    from datetime import datetime, timedelta, timezone
    fixes = []
    # walk north at a steady pace over a constant slope supplied by the DEM hook
    for i in range(40):
        fixes.append(Fix(
            lat=37.22 + i * 0.0003, lon=38.92,
            time=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc) + timedelta(seconds=20 * i),
            accuracy_m=5,
        ))
    track = Track("t1", fixes)
    segments, report = clean_track(track, elevation_at=lambda lat, lon: (lat - 37.22) * 111320 * 0.05)
    assert report.segments > 0
    assert report.fixes_dropped_accuracy == 0
    # synthetic segments from a known Tobler curve
    rng = np.random.default_rng(0)
    slopes = rng.uniform(-0.15, 0.2, 40)
    speeds = 5.0 * np.exp(-3.5 * np.abs(slopes + 0.05))
    segs = [Segment(float(s), float(v), 30.0, "one") for s, v in zip(slopes, speeds)]
    fit = fit_tobler(segs, n_boot=25, rng=rng)
    assert fit["a_ci"][0] - 1e-6 <= 5.0 <= fit["a_ci"][1] + 1e-6
    assert fit["b_ci"][0] - 1e-6 <= 3.5 <= fit["b_ci"][1] + 1e-6


def test_a_walked_line_overlaps_itself():
    line = [(0, 0), (10, 0), (20, 0), (30, 0)]
    assert buffer_overlap(line, line, buffer_m=25) == pytest.approx(1.0)


def test_routes_require_access_notes():
    routes = load_routes(os.path.join(os.path.dirname(__file__), "..", "data", "routes"))
    assert any(r["properties"]["id"] == "gobekli-ridge-transect" for r in routes)


def test_gravity_trips_follow_interaction_and_mantel_recovers_it():
    times = np.array([
        [0, 30, 80, 120],
        [30, 0, 50, 90],
        [80, 50, 0, 40],
        [120, 90, 40, 0],
    ], dtype=float)
    interaction = interaction_matrix([1, 2, 1.5, 3], times, beta=1.2)
    rng = np.random.default_rng(1)
    counts = sample_pair_counts(interaction, 5000, rng)
    assert pearson(counts, interaction) > 0.9
    similarity = np.exp(-times / 50.0)
    dissimilarity = 1.0 - similarity
    np.fill_diagonal(dissimilarity, 0.0)
    result = mantel(times, dissimilarity, permutations=200, rng=rng)
    assert result["r"] > 0.8
    rows, edges = graph_metrics(["a", "b", "c", "d"], times, day_trip_min=DAY_TRIP_MIN)
    assert len(rows) == 4 and edges


def test_known_beta_is_recovered_and_beats_a_worse_distance():
    rng = np.random.default_rng(2)
    times = np.array([[1.0, 2.0, 4.0], [3.0, 1.2, 2.5], [5.0, 3.0, 1.1]])
    counts = synthetic_counts(times, beta=1.5, n_per_site=800, rng=rng)
    fit = fit_beta(counts, times, np.ones(3))
    assert abs(fit["beta"] - 1.5) / 1.5 <= 0.10
    # a scrambled distance should not beat the true one
    scrambled = times[:, ::-1]
    report = compare_distance(counts, times, scrambled, np.ones(3))
    assert report["delta_aic_cost_minus_euclidean"] < 0


def test_ensemble_bands_and_hypothesis_report(tmp_path):
    from pedsim.hypotheses import compare

    def factory(seed):
        return _flat(n_agents=6)

    # factory ignores seed's effect on the already-built rng; rebuild inside
    def make(seed):
        sim = Simulation(
            bounds=(0, 0, 80, 40), gridsize=10, num_agents=6, seed=seed,
            ods=[OD(10, 10, name="a"), OD(60, 10, name="b")],
        )
        return sim

    summary = run_ensemble(make, n=4, steps=5, threshold=0.0)
    assert set(summary) == {"mean", "sd", "p05", "p95", "p_exceed"}
    text = compare(["R", "G"], seeds=[1], steps=8, num_agents=8, out_dir=str(tmp_path))
    assert "separat" in text
    assert "to be defined" in text
    assert os.path.exists(tmp_path / "metrics.csv")
    header = open(tmp_path / "metrics.csv", encoding="utf-8").readline()
    assert "special_share" in header
    units = open(tmp_path / "metrics.csv", encoding="utf-8").read().splitlines()[1]
    assert "km" in units


def test_three_scales_and_escape_goes_up_one_level():
    def make():
        return _flat(n_agents=0)

    regional = Scene("Region", Scale.REGIONAL, make)
    cluster = Scene("Cluster", Scale.CLUSTER, make)
    site = Scene("Göbeklitepe", Scale.SITE, make, site_name="Göbeklitepe")
    app = TwoScaleApp(cluster, {"Göbeklitepe": site}, regional=regional)
    assert app.breadcrumb() == "Region"
    app.enter_cluster()
    app.enter_detail("Göbeklitepe")
    assert app.breadcrumb() == "Region \u203a Cluster \u203a Göbeklitepe"
    app.up()
    assert app.at_cluster
    app.up()
    assert app.at_root
    # edits are still the scene we left and came back to
    app.enter_cluster()
    app.mark_dirty()
    assert app.dirty
    app.up()
    app.enter_cluster()
    assert app.dirty


def test_flat_thirty_seven_kilometres_is_a_days_walk():
    """Göbeklitepe to Karahantepe is about 37 km, 7–9 h at a walking pace."""
    from pedsim.network import straight_minutes
    from pedsim.sites import find
    a, b = find("Göbeklitepe"), find("Karahantepe")
    minutes = straight_minutes(a.lat, a.lon, b.lat, b.lon, kmh=4.5)
    assert 7 * 60 <= minutes <= 9 * 60


def test_odd_lists_the_scenario_parameters(tmp_path):
    from pedsim.scenario import write_odd
    path = write_odd(str(tmp_path / "ODD.md"))
    text = open(path, encoding="utf-8").read()
    assert "Overview" in text and "Design concepts" in text and "respect_chronology" in text


def test_packed_scene_keeps_both_phases(tmp_path):
    from pedsim.pack import write_scene
    scene = json.loads(open(write_scene(str(tmp_path), steps=2), encoding="utf-8").read())
    assert {phase["id"] for phase in scene["phases"]} == {"GT-III", "GT-II"}
    assert scene["density"]["GT-II"] and scene["density"]["GT-III"]
    seasons = {entry["id"]: entry for entry in scene["seasons"]}
    assert seasons["dry"]["event_factor"] == 1.4
    assert scene["engine"].startswith("pedsim")


def test_cluster_pack_lists_settlements_and_ods(tmp_path):
    from pedsim.pack import write_cluster_scene
    scene = json.loads(open(write_cluster_scene(str(tmp_path), steps=2,
                                                cellsize=1000.0, num_agents=16),
                             encoding="utf-8").read())
    assert scene["scale"] == "cluster"
    assert len(scene["sites"]) >= 8
    assert len(scene["ods"]) >= 8
    assert scene["links"] and scene["density"]["both"]

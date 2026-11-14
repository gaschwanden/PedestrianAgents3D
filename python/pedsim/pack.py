"""Offline data packs for the field client.

``build_pack`` writes live scenes: for the cluster and for each usable site,
the inputs of a :class:`~pedsim.simulation.Simulation` (terrain on the grid,
geometry, rivers, georeference, solved cost fields). The field client rebuilds
that simulation with :mod:`pedsim.live` and runs it on the device, so there is
still one agent model. It also writes a hillshade basemap from the DEM, the
route library and the calendar / population tables.

``write_scene`` and ``write_cluster_scene`` are the older playback packs
(recorded frames). They are kept for the tests and as a reference.
"""
from __future__ import annotations

import json
import math
import os
import shutil
from typing import Dict, List

from .scenario import config_dir, package_root


def _ring(building, to_lonlat) -> list:
    ring = [to_lonlat(x, y) for x, y in building.footprint.as_xy()]
    if ring and ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return ring


def _village_lonlat(x: float, y: float) -> list:
    """Local metres to WGS84, with (200, 200) on the Göbeklitepe marker."""
    lat = 37.2233 + (y - 200.0) / 111320.0
    lon = 38.9225 + (x - 200.0) / (111320.0 * math.cos(math.radians(37.2233)))
    return [round(lon, 6), round(lat, 6)]


def _seasons_from_calendar() -> List[dict]:
    from .calendar import load_calendar

    cal = load_calendar()
    by_season: Dict[str, dict] = {}
    for number, month in sorted(cal.months.items()):
        season = getattr(month.river_season, "value", str(month.river_season))
        entry = by_season.setdefault(season, {
            "id": season,
            "name": season,
            "months": [],
            "daylight_minutes": month.daylight_minutes,
            "event_factor": 1.0,
        })
        entry["months"].append(number)
        entry["event_factor"] = max(
            entry["event_factor"],
            float(cal.event_factor(number, "Göbeklitepe")),
        )
        # Prefer August daylight for dry, March for floods, May for normal.
        prefer = {"dry": 8, "spring floods": 3, "normal": 5}.get(season)
        if prefer == number:
            entry["daylight_minutes"] = round(month.daylight_minutes, 1)
    order = ["dry", "normal", "spring floods"]
    return [by_season[key] for key in order if key in by_season]


def _shared_meta() -> dict:
    from .scenario import config_path, load_yaml

    population = load_yaml(config_path("population.yaml"))
    tasks = load_yaml(config_path("tasks.yaml"))
    routes = []
    route_dir = os.path.join(package_root(), "data", "routes")
    if os.path.isdir(route_dir):
        for name in sorted(os.listdir(route_dir)):
            if name.endswith(".geojson"):
                with open(os.path.join(route_dir, name), encoding="utf-8") as fh:
                    routes.append(json.load(fh))
    return {
        "seasons": _seasons_from_calendar(),
        "classes": [c["id"] for c in population.get("classes", [])],
        "tasks": [t["id"] for t in tasks.get("tasks", [])],
        "routes": routes,
    }


def _min_steps_for_ods(sim, margin: float = 1.6) -> int:
    """Lower bound so a straight walk can cover the longest OD pair."""
    import math

    ods = [o for o in sim.ods if o is not None]
    if len(ods) < 2:
        return 1
    worst = 0.0
    cell = max(sim.grid.gridsize, 1e-6)
    speed = max(float(sim.speed), 1e-6)
    for i, a in enumerate(ods):
        for b in ods[i + 1:]:
            cells = math.hypot((a.x - b.x) / cell, (a.y - b.y) / cell)
            worst = max(worst, cells / speed)
    return max(1, int(math.ceil(worst * margin)))


def write_scene(directory: str, steps: int | None = None) -> str:
    """Pack a real pedsim run of the synthetic village for the field client.

    When ``steps`` is omitted, the scenario length is used and extended if needed
    so agents can finish the longest origin→destination span. Explicit ``steps``
    (tests) runs exactly that many ticks and skips the arrival check.
    """
    from .scenario import config_path, load_scenario, synthetic_scene

    scenario = load_scenario(config_path("scenario_synthetic.yaml"))
    ensure_trips = steps is None
    requested = int(scenario.get("steps") or 900) if ensure_trips else int(steps)
    os.makedirs(directory, exist_ok=True)

    def band(phase_ids: list) -> dict:
        from .agent import DIED_TARGET_REACHED, Agent

        sim = synthetic_scene(scenario)
        sim.research.set_manual_phases(phase_ids)
        sim.apply_phase_filter()
        need = _min_steps_for_ods(sim)
        run_steps = max(requested, need) if ensure_trips else requested
        reached = {"n": 0}
        real_die = Agent.die

        def counting_die(self, reason):
            if reason == DIED_TARGET_REACHED:
                reached["n"] += 1
            return real_die(self, reason)

        Agent.die = counting_die
        try:
            frames = []
            for _ in range(run_steps):
                sim.step()
                frames.append([
                    _village_lonlat(sim.grid.world_x(a.px), sim.grid.world_y(a.py))
                    for a in sim.active_agents
                ])
        finally:
            Agent.die = real_die
        if ensure_trips and reached["n"] < 1:
            raise RuntimeError(
                f"village pack band {phase_ids}: no OD arrivals in {run_steps} steps "
                f"(need ≥{need} for straight OD spans)"
            )
        grid = sim.grid
        # Downsample occupancy for the pack so a 2 m grid stays downloadable;
        # agent frames keep the full-resolution positions.
        stride = max(1, int(round(4.0 / max(grid.gridsize, 1e-6))))
        rows = []
        for j in range(grid.ny - 1, -1, -stride):
            row = []
            for i in range(0, grid.nx, stride):
                block = grid.occupancy[i:i + stride, max(0, j - stride + 1):j + 1]
                row.append(round(float(block.max()) if block.size else 0.0, 4))
            rows.append(row)
        return {
            "rows": rows, "frames": frames, "sim": sim,
            "gridsize": grid.gridsize, "steps": run_steps,
            "need": need, "arrivals": reached["n"],
        }

    both = band(["GT-III", "GT-II"])
    sim = both.pop("sim")
    third = band(["GT-III"])
    second = band(["GT-II"])
    grid = sim.grid
    west, south = _village_lonlat(grid.sx, grid.sy)
    east, north = _village_lonlat(
        grid.sx + grid.nx * grid.gridsize, grid.sy + grid.ny * grid.gridsize,
    )
    meta = _shared_meta()
    run_steps = max(both["steps"], third["steps"], second["steps"])
    scene = {
        "id": "village",
        "name": "Göbeklitepe synthetic village",
        "scale": "village",
        "engine": "pedsim packed playback",
        "note": (
            "Density and agent positions come from pedsim. The field client "
            "selects and reweights these packed bands. It does not run a second model. "
            f"Packed {run_steps} steps so agents can finish origin→destination trips."
        ),
        "seed": int(scenario["seed"]),
        "steps": run_steps,
        "arrivals": {
            "both": both["arrivals"], "GT-III": third["arrivals"], "GT-II": second["arrivals"],
        },
        "gridsize_m": float(sim.grid.gridsize),
        "bounds": {"west": west, "south": south, "east": east, "north": north},
        "center": [38.9225, 37.2233],
        "zoom": 16,
        "phases": [
            {
                "id": phase.id, "name": phase.name,
                "start_bc": phase.start_bc, "end_bc": phase.end_bc,
                "colour": phase.colour, "confidence": phase.confidence,
            }
            for phase in sim.research.phases
        ],
        "buildings": [
            {
                "name": b.function,
                "function": b.function,
                "phase_ids": list(b.phase_ids),
                "ring": _ring(b, _village_lonlat),
            }
            for b in sim.buildings
        ],
        "sites": [],
        "ods": [
            {
                "name": o.name, "kind": o.kind, "phase_ids": list(o.phase_ids),
                "coordinates": _village_lonlat(o.x, o.y),
                "origin_weight": o.origin_weight, "dest_weight": o.dest_weight,
            }
            for o in sim.ods
        ],
        "links": [],
        "density": {
            "GT-III": third["rows"],
            "GT-II": second["rows"],
            "both": both["rows"],
        },
        "frames": {
            "GT-III": third["frames"],
            "GT-II": second["frames"],
            "both": both["frames"],
        },
        **meta,
    }
    path = os.path.join(directory, "scene.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(scene, fh, ensure_ascii=False)
    return path


def write_cluster_scene(
    directory: str,
    steps: int = 8,
    cellsize: float = 1000.0,
    num_agents: int = 32,
) -> str:
    """Pack the settlement-cluster run: sites, inter-site ODs and density."""
    from .scenes import cluster_scene
    from .sites import located

    os.makedirs(directory, exist_ok=True)
    sim = cluster_scene(
        cellsize=cellsize, num_agents=num_agents, seed=7, max_rivers=8,
    )
    frame = sim.frame

    def to_lonlat(x: float, y: float) -> list:
        lat, lon = frame.to_latlon(x, y)
        return [round(float(lon), 6), round(float(lat), 6)]

    frames = []
    for _ in range(steps):
        sim.step()
        frames.append([
            to_lonlat(sim.grid.world_x(a.px), sim.grid.world_y(a.py))
            for a in sim.active_agents
        ])
    grid = sim.grid
    rows = []
    for j in range(grid.ny - 1, -1, -1):
        rows.append([round(float(grid.occupancy[i, j]), 4) for i in range(grid.nx)])
    sw = to_lonlat(grid.sx, grid.sy)
    ne = to_lonlat(grid.sx + grid.nx * grid.gridsize, grid.sy + grid.ny * grid.gridsize)
    catalogue = located(usable_only=True)
    sites_out = []
    for site in catalogue:
        sites_out.append({
            "name": site.name,
            "coordinates": [round(site.lon, 6), round(site.lat, 6)],
            "start_bc": site.start_bc,
            "end_bc": site.end_bc,
            "confidence": site.confidence.value if hasattr(site.confidence, "value") else str(site.confidence),
            "official": bool(site.official),
            "period": site.period,
        })
    ods = [
        {
            "name": o.name, "kind": o.kind or "site",
            "phase_ids": list(getattr(o, "phase_ids", []) or []),
            "coordinates": to_lonlat(o.x, o.y),
            "origin_weight": o.origin_weight, "dest_weight": o.dest_weight,
            "site": getattr(o, "site", o.name),
        }
        for o in sim.ods
    ]
    # Straight-line OD network so the map shows inter-settlement links even
    # before corridors thicken in the occupancy field.
    links = []
    for i, a in enumerate(ods):
        for b in ods[i + 1:]:
            links.append({
                "from": a["name"], "to": b["name"],
                "coordinates": [a["coordinates"], b["coordinates"]],
            })
    meta = _shared_meta()
    scene = {
        "id": "cluster",
        "name": "Taş Tepeler cluster",
        "scale": "cluster",
        "engine": "pedsim packed playback",
        "note": (
            "Cluster density, sites and OD points come from pedsim. "
            "The field client plays this pack back."
        ),
        "seed": 7,
        "steps": steps,
        "bounds": {
            "west": min(sw[0], ne[0]),
            "south": min(sw[1], ne[1]),
            "east": max(sw[0], ne[0]),
            "north": max(sw[1], ne[1]),
        },
        "center": [38.85, 37.15],
        "zoom": 9.5,
        "phases": [
            {
                "id": "cluster", "name": "cluster window",
                "start_bc": 10000, "end_bc": 7000,
                "colour": "#c0504d", "confidence": "assumption",
            }
        ],
        "buildings": [],
        "sites": sites_out,
        "ods": ods,
        "links": links,
        "density": {"both": rows, "cluster": rows},
        "frames": {"both": frames, "cluster": frames},
        **meta,
    }
    path = os.path.join(directory, "cluster.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(scene, fh, ensure_ascii=False)
    return path


# ------------------------------------------------------------------ live pack
#: Sites left out of the village scenes, with the reason shown in the index.
VILLAGE_SKIP: Dict[str, str] = {}

#: Said in a village scene's note, because the terrain there is not the site's.
VILLAGE_CAVEAT = {
    "Nevalı Çori": "Submerged under the Atatürk reservoir: the terrain here is "
                   "the modern lake surface, not the valley the site stood in.",
}


def _slug(name: str) -> str:
    from .app import slug
    return slug(name)


def _site_rows() -> List[dict]:
    from . import maps
    from .sites import located

    from .sites import placed

    rows = []
    for site, lat, lon, quality in placed():
        rows.append({
            "name": site.name,
            "coordinates": [round(lon, 6), round(lat, 6)],
            "start_bc": site.start_bc, "end_bc": site.end_bc,
            "confidence": quality,
            # a working position, not a location: conflicting or search area
            "uncertain": quality in ("conflicting", "search area"),
            "usable": True,
            "official": bool(site.official),
            "period": site.period,
            "has_plan": bool(maps.has_village_plan(site.name)),
        })
    return rows


def _write_live(root: str, sim, scene_id: str, name: str, scale: str, frame,
                **kw) -> dict:
    """Write ``<id>.json`` + ``<id>.bin`` and return the index row."""
    from . import live

    meta, blob = live.pack_scene(sim, scene_id, name, scale, frame, **kw)
    meta.update(_shared_meta())
    # Loading it back proves the pack is complete, and gives the client a
    # ready description to draw before (or without) the engine.
    engine = live.LiveEngine()
    meta["display"] = engine.load(meta, blob)
    with open(os.path.join(root, f"{scene_id}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    with open(os.path.join(root, f"{scene_id}.bin"), "wb") as fh:
        fh.write(blob)
    return {
        "id": scene_id, "label": name, "scale": scale, "site": kw.get("site", ""),
        "file": f"{scene_id}.json", "blob": f"{scene_id}.bin",
        "bytes": len(blob), "note": kw.get("note", ""),
        "center": meta["display"]["center"],
        "bounds": meta["display"]["bounds"],
    }


def _saved_geometry(save_dir: str, name: str) -> str:
    path = os.path.join(save_dir, f"{_slug(name)}.geometry.json")
    return path if save_dir and os.path.exists(path) else ""


def write_live_pack(root: str, sites_filter=None, save_dir: str = "",
                    village_extent: float = 600.0, village_cell: float = 2.0,
                    cluster_cell: float = 250.0, progress=None) -> dict:
    """Pack the cluster and one village per usable site for the live engine.

    A ``<slug>.geometry.json`` saved by the desktop viewer in ``save_dir`` is
    applied to its scene first, so walls and ODs drawn on the laptop travel.
    """
    from . import live, scenes
    from .rivers import Season
    from .sites import placed

    say = progress or (lambda _m: None)
    os.makedirs(root, exist_ok=True)
    rows = _site_rows()
    import datetime as _dt

    index = {
        "default": "cluster",
        "build": _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S"),
        "scenes": [], "skipped": [],
    }
    real = scenes.data_available()

    say("cluster")
    sim = scenes.cluster_scene(cellsize=cluster_cell, seed=7)
    sim.pack_seed = 7
    saved = _saved_geometry(save_dir, "Taş Tepeler cluster")
    if saved:
        sim.load_geometry_json(saved)
    sim.research.respect_chronology = True
    grid = sim.grid
    bounds = (grid.min_x, grid.min_y, grid.max_x, grid.max_y)
    frame = live.BilinearFrame.from_frame(sim.frame, bounds, nodes=17)
    index["scenes"].append(_write_live(
        root, sim, "cluster", "Taş Tepeler cluster", "cluster", frame,
        zoom=9.5, sites=rows, cost_seasons=list(Season),
        note=("Copernicus GLO-30 terrain, HydroRIVERS watercourses" if real
              else "synthetic relief: no DEM was downloaded when this pack was built"),
    ))

    for site, _lat, _lon, quality in placed():
        if sites_filter and site.name not in sites_filter:
            continue
        if site.name in VILLAGE_SKIP:
            index["skipped"].append({"site": site.name, "reason": VILLAGE_SKIP[site.name]})
            continue
        say(site.name)
        sim = scenes.village_scene(site.name, extent_m=village_extent,
                                   cellsize=village_cell, seed=3)
        sim.pack_seed = 3
        saved = _saved_geometry(save_dir, site.name)
        if saved:
            sim.load_geometry_json(saved)
        grid = sim.grid
        bounds = (grid.min_x, grid.min_y, grid.max_x, grid.max_y)
        frame = live.BilinearFrame.from_frame(sim.frame, bounds, nodes=3)
        conf = quality
        walls = len(sim.buildings) + len(sim.obstacles)
        note = f"coordinate: {conf}. "
        if conf == "search area":
            note = ("Position unknown: this scene sits on a placeholder inside the "
                    "published search area. ")
        elif conf == "conflicting":
            note = "Two published positions disagree; this is the first of them. "
        if site.name in VILLAGE_CAVEAT:
            note += VILLAGE_CAVEAT[site.name] + " "
        note += (f"{walls} wall or building outlines from the saved desktop scene."
                 if walls else "Terrain and perimeter gates only: no wall plan imported yet.")
        row = _write_live(
            root, sim, "village-" + _slug(site.name), site.name, "village", frame,
            site=site.name, zoom=16.0, sites=[r for r in rows if r["name"] == site.name],
            note=note,
        )
        row["confidence"] = conf
        index["scenes"].append(row)

    from . import gobekli_plan

    if gobekli_plan.available() and (not sites_filter or "Göbeklitepe" in sites_filter):
        say("Göbeklitepe phase plan")
        sim = gobekli_plan.plan_scene(progress=progress)
        sim.pack_seed = 5
        grid = sim.grid
        bounds = (grid.min_x, grid.min_y, grid.max_x, grid.max_y)
        frame = live.BilinearFrame.from_frame(sim.frame, bounds, nodes=2)
        note = ("Walls and pillars read from the 2024 building-phase plan (" + gobekli_plan.CITATION
                + ") Position: " + sim.position_quality + ". Phase dates are assumptions; "
                "a wall is taken to stand from its building phase onward; unphased "
                "stonework is not included. " + " ".join(sim.entrance_notes))
        row = _write_live(
            root, sim, "plan-gobeklitepe", "Göbeklitepe · main excavation (plan)", "village",
            frame, site="Göbeklitepe", zoom=19.0,
            sites=[r for r in rows if r["name"] == "Göbeklitepe"], note=note,
        )
        row["confidence"] = "published"
        row["plan"] = True
        index["scenes"].append(row)
    else:
        index["skipped"].append({
            "site": "Göbeklitepe plan",
            "reason": "plan image not found at data/raw/" + gobekli_plan.PLAN_FILE,
        })

    with open(os.path.join(root, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1, ensure_ascii=False)
    return index


def write_engine_zip(path: str) -> str:
    """Zip the pure-Python package and its config for the in-browser engine."""
    import zipfile

    base = package_root()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ("pedsim", os.path.join("data", "config"),
                       os.path.join("data", "routes"), os.path.join("data", "schema")):
            top = os.path.join(base, folder)
            for dirpath, dirnames, filenames in os.walk(top):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for name in sorted(filenames):
                    if name.endswith((".pyc", ".DS_Store")):
                        continue
                    full = os.path.join(dirpath, name)
                    zf.write(full, os.path.relpath(full, base))
    return path


def build_pack(area: str = "goebekli", out_dir: str = "", publish_web: bool = False,
               save_dir: str = "", sites_filter=None, progress=None,
               maps: bool = True) -> str:
    root = out_dir or os.path.join(package_root(), "data", "packs", area)
    os.makedirs(root, exist_ok=True)
    config = config_dir()
    for name in ("population.yaml", "tasks.yaml", "calendar.yaml", "obsidian_sources.yaml"):
        src = os.path.join(config, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(root, name))
    routes = os.path.join(package_root(), "data", "routes")
    if os.path.isdir(routes):
        dest = os.path.join(root, "routes")
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(routes):
            if name.endswith(".geojson"):
                shutil.copy(os.path.join(routes, name), os.path.join(dest, name))
    index = {}
    if area == "goebekli":
        # The folder is build output: drop scenes from an earlier build so the
        # index and the files on disk cannot disagree.
        for name in os.listdir(root):
            if name.endswith((".bin", ".jpg", ".geojson")) or (
                    name.endswith(".json") and name != "manifest.json"):
                os.remove(os.path.join(root, name))
        index = write_live_pack(root, sites_filter=sites_filter, save_dir=save_dir,
                                progress=progress)
        from .basemap import write_basemap, write_scene_maps
        index["basemap"] = write_basemap(root, progress=progress)
        if maps:
            index["maps"] = write_scene_maps(root, index["scenes"], progress=progress)
        with open(os.path.join(root, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=1, ensure_ascii=False)
    manifest = {
        "area": area,
        "version": 3,
        "contents": sorted(os.listdir(root)),
        "basemap": (
            "basemap.jpg is a hillshade rendered from the Copernicus DEM and is "
            "packed for offline use. Satellite and street tiles are online only."
        ),
        "simulation": (
            "Each scene is <id>.json + <id>.bin: the inputs of a pedsim Simulation. "
            "The field client rebuilds and runs it with pedsim itself."
        ),
        "offline": True,
    }
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    if publish_web:
        web_root = os.path.abspath(os.path.join(package_root(), "..", "web"))
        web = os.path.join(web_root, "packs", area)
        os.makedirs(web, exist_ok=True)
        for name in os.listdir(web):
            if name.endswith((".json", ".bin", ".jpg", ".geojson")):
                os.remove(os.path.join(web, name))
        for name in sorted(os.listdir(root)):
            if name.endswith((".json", ".bin", ".jpg", ".geojson")):
                shutil.copy(os.path.join(root, name), os.path.join(web, name))
        os.makedirs(os.path.join(web_root, "vendor"), exist_ok=True)
        write_engine_zip(os.path.join(web_root, "vendor", "pedsim.zip"))
    return root

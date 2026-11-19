"""Scenario files: the one description a run is allowed to depend on.

A scenario is YAML. Loading it fills defaults, checks it against the schema,
and hashes the normalised JSON so two files that mean the same thing share a
hash. The run record stores that hash plus every default that was actually
used, which is what makes an ``ASSUMPTION`` visible after the fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


def package_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def config_dir() -> str:
    env = os.environ.get("PEDSIM_CONFIG")
    if env:
        return os.path.abspath(env)
    return os.path.join(package_root(), "data", "config")


def config_path(name: str) -> str:
    return os.path.join(config_dir(), name)


def schema_path() -> str:
    return os.path.join(package_root(), "data", "schema", "scenario.schema.json")


def load_yaml(path: str) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError("reading a scenario needs pyyaml (`pip install pyyaml`)") from exc
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the file must be a mapping, not {type(data).__name__}")
    return data


DEFAULTS: Dict[str, Any] = {
    "scene": "synthetic",
    "site": "",
    "time_window": {"start_bc": 10000, "end_bc": 7000},
    "respect_chronology": True,
    "tau_years": 0,
    "undated_policy": "exclude",
    "overlap_weighting": False,
    "pins": {},
    "phase_mode": "manual",
    "active_phases": [],
    "phase_overrides": {},
    "population": "population.yaml",
    "tasks": "tasks.yaml",
    "task_allocation": "by_class",
    "calendar_month": None,
    "terrain_profile": "default",
    "terrain": {
        "base_speed": 1.0,
        "slope_factor": 3.5,
        "slope_offset": 0.05,
        "impassable_slope": 1.2,
    },
    "num_agents": 40,
    "steps": 30,
    "seed": 1,
    "seeds": [],
    "gridsize": 2.0,
    "extent_m": 400.0,
    "od_mode": "uniform",
    "agents_per_person": None,
    "population_rule": "per_house",
    "persons_per_house": 5,
    "persons_per_m2": 0.1,
    "active_share": 0.6,
    "family": "",
    "notes": "",
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def normalise(data: dict) -> dict:
    """Defaults filled in, keys sorted later by the hasher. Unknown keys fail."""
    unknown = [k for k in data.keys() if k not in DEFAULTS and k != "name"]
    if unknown:
        raise ValueError(f"unknown scenario key: {unknown[0]}")
    merged = _merge(DEFAULTS, data)
    window = merged.get("time_window") or {}
    if not isinstance(window, dict) or "start_bc" not in window or "end_bc" not in window:
        raise ValueError("bad scenario key: time_window")
    try:
        start = int(window["start_bc"])
        end = int(window["end_bc"])
    except (TypeError, ValueError) as exc:
        raise ValueError("bad scenario key: time_window") from exc
    if start < end:
        raise ValueError("bad scenario key: time_window (start_bc must be ≥ end_bc)")
    merged["time_window"] = {"start_bc": start, "end_bc": end}
    policy = merged["undated_policy"]
    if policy not in ("exclude", "include", "include_flagged"):
        raise ValueError("bad scenario key: undated_policy")
    if merged["phase_mode"] not in ("manual", "by_time"):
        raise ValueError("bad scenario key: phase_mode")
    if merged["task_allocation"] not in ("by_class", "uniform"):
        raise ValueError("bad scenario key: task_allocation")
    if merged["od_mode"] not in ("uniform", "gravity"):
        raise ValueError("bad scenario key: od_mode")
    scene = str(merged["scene"])
    if scene not in ("synthetic", "cluster", "regional") and not scene.startswith("village"):
        raise ValueError("bad scenario key: scene")
    _validate_schema(merged)
    return merged


def _validate_schema(merged: dict) -> None:
    """Use jsonschema when it is installed. The hand checks above still run."""
    path = schema_path()
    if not os.path.exists(path):
        return
    try:
        import jsonschema
    except ImportError:
        return
    with open(path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    try:
        jsonschema.validate(merged, schema)
    except jsonschema.ValidationError as exc:
        key = ".".join(str(p) for p in exc.absolute_path) or exc.validator
        raise ValueError(f"bad scenario key: {key} ({exc.message})") from exc


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scenario_hash(data: dict) -> str:
    """SHA-256 of the normalised scenario. The name is not part of the hash."""
    body = dict(data)
    body.pop("name", None)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def load_scenario(path: str) -> dict:
    raw = load_yaml(path)
    merged = normalise(raw)
    merged["name"] = raw.get("name", os.path.splitext(os.path.basename(path))[0])
    merged["_hash"] = scenario_hash(merged)
    merged["_path"] = os.path.abspath(path)
    return merged


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=package_root(), capture_output=True, text=True, timeout=5, check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def package_versions() -> Dict[str, str]:
    import importlib.metadata as md

    from . import __version__

    found = {"pedsim": __version__}
    for name in ("numpy", "pyyaml", "jsonschema", "scipy", "networkx", "rasterio",
                 "pyproj", "shapely", "gpxpy"):
        try:
            found[name] = md.version(name if name != "pyyaml" else "PyYAML")
        except md.PackageNotFoundError:
            continue
    return found


def make_run_id(scenario: dict, seed: int) -> str:
    digest = scenario.get("_hash") or scenario_hash(scenario)
    return f"{digest[:12]}-{int(seed)}"


def build_run_record(scenario: dict, seeds: List[int], wall_clock_s: float,
                     input_files: Optional[Dict[str, str]] = None,
                     extra: Optional[dict] = None) -> dict:
    """The document that must be enough, on its own, to repeat the run."""
    resolved = {k: v for k, v in scenario.items() if not k.startswith("_")}
    record = {
        "run_id": make_run_id(scenario, seeds[0] if seeds else 0),
        "scenario_hash": scenario.get("_hash") or scenario_hash(scenario),
        "scenario": resolved,
        "seeds": list(seeds),
        "wall_clock_s": round(float(wall_clock_s), 4),
        "git_commit": git_commit(),
        "packages": package_versions(),
        "inputs": {},
        "assumptions": _assumption_keys(resolved),
    }
    for label, path in (input_files or {}).items():
        if path and os.path.exists(path):
            record["inputs"][label] = {"path": path, "sha256": file_sha256(path)}
    if extra:
        record.update(extra)
    return record


def _assumption_keys(resolved: dict) -> List[str]:
    """Parameters whose defaults are modelling choices, named for the record."""
    keys = [
        "tau_years", "persons_per_house", "persons_per_m2", "active_share",
        "population_rule", "task_allocation",
    ]
    return [k for k in keys if k in resolved]


def write_run_record(directory: str, record: dict) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "run.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return path


def load_run_record(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "scenario" not in data:
        raise ValueError(f"{path} has no scenario; it cannot reproduce a run")
    return data


@dataclass
class RunResult:
    scenario: dict
    record: dict
    occupancy: Any = None
    directory: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)


def apply_scenario(sim, scenario: dict) -> None:
    """Push chronology, phases, terrain profile and population onto a simulation."""
    from .chronology import Interval
    from .phases import Phase

    r = sim.research
    window = scenario["time_window"]
    r.window = Interval(int(window["end_bc"]), int(window["start_bc"]))
    r.respect_chronology = bool(scenario["respect_chronology"])
    r.tau = int(scenario["tau_years"])
    r.undated_policy = scenario["undated_policy"]
    r.overlap_weighting = bool(scenario["overlap_weighting"])
    r.pins = {str(k): str(v) for k, v in (scenario.get("pins") or {}).items()}
    r.phase_mode = scenario["phase_mode"]
    r.phase_overrides = {str(k): str(v) for k, v in (scenario.get("phase_overrides") or {}).items()}
    r.scenario_ref = scenario.get("name", "")
    r.scenario_hash = scenario.get("_hash", "")
    r.population_rule = scenario["population_rule"]
    r.persons_per_house = float(scenario["persons_per_house"])
    r.persons_per_m2 = float(scenario["persons_per_m2"])
    r.agents_per_person = scenario.get("agents_per_person")
    r.active_share = float(scenario["active_share"])
    r.od_mode = scenario["od_mode"]
    r.terrain_profile = scenario["terrain_profile"]
    if scenario["phase_mode"] == "manual":
        r.manual_phase_ids = list(scenario.get("active_phases") or [p.id for p in r.phases])
    terrain = scenario.get("terrain") or {}
    cost = sim.grid.terrain_cost
    if cost is not None and terrain:
        cost.base_speed = float(terrain.get("base_speed", cost.base_speed))
        cost.slope_factor = float(terrain.get("slope_factor", cost.slope_factor))
        cost.slope_offset = float(terrain.get("slope_offset", cost.slope_offset))
        cost.impassable_slope = float(terrain.get("impassable_slope", cost.impassable_slope))
    month = scenario.get("calendar_month")
    if month:
        from .calendar import apply_month
        apply_month(sim, int(month))
    if scenario.get("population"):
        from .population import load_population
        pop_path = scenario["population"]
        if not os.path.isabs(pop_path):
            pop_path = config_path(pop_path) if not os.path.exists(pop_path) else pop_path
        if os.path.exists(pop_path):
            sim.population = load_population(pop_path)
            sim.load_k = sim.population.load_k
            sim.population.assign(sim.agents, sim.rng)
            r.badges = sim.population.badges()
    if scenario.get("tasks"):
        from .tasks import TaskModel, load_tasks
        task_path = scenario["tasks"]
        if not os.path.isabs(task_path):
            candidate = config_path(task_path)
            task_path = candidate if os.path.exists(candidate) else task_path
        if os.path.exists(task_path):
            sim.task_model = TaskModel(load_tasks(task_path),
                                       allocation=scenario["task_allocation"])
            sim.tasks_enabled = True
    # phases embedded in the scenario under a non-schema key are ignored;
    # geometry phases already on the sim are filtered by active_phases.
    if scenario.get("active_phases") and r.phases:
        known = {p.id for p in r.phases}
        missing = [i for i in scenario["active_phases"] if i not in known]
        if missing:
            raise ValueError(f"bad scenario key: active_phases ({missing[0]})")
    if r.phases:
        sim.apply_phase_filter()


def synthetic_scene(scenario: dict):
    """A small flat scene so a scenario can run with no downloaded DEM."""
    from .building import Building
    from .od import OD
    from .simulation import Simulation
    from .topography import TerrainCost, Topography

    extent = float(scenario["extent_m"])
    gridsize = float(scenario["gridsize"])
    n = max(8, int(extent / gridsize))
    elev = np.zeros((n, n), dtype=float)
    topo = Topography(elev, 0.0, 0.0, gridsize)
    # two houses, one special building, water, two gates
    def box(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    houses = [
        Building.from_polygon(box(40, 40, 70, 70), height=3, function="domestic",
                              phase_ids=["GT-II"]),
        Building.from_polygon(box(80, 40, 110, 70), height=3, function="domestic",
                              phase_ids=["GT-II"]),
    ]
    special = Building.from_polygon(box(180, 160, 240, 230), height=4, function="special",
                                    phase_ids=["GT-III"])
    ods = [
        OD(55, 80, name="house-a", kind="house", origin_weight=1, dest_weight=0.2,
           phase_ids=["GT-II"]),
        OD(95, 80, name="house-b", kind="house", origin_weight=1, dest_weight=0.2,
           phase_ids=["GT-II"]),
        OD(210, 150, name="special", kind="special", origin_weight=0.1, dest_weight=1,
           phase_ids=["GT-III"]),
        OD(20, 200, name="cistern", kind="water", origin_weight=0, dest_weight=1,
           tags=["cistern"]),
        OD(360, 200, name="gate-east", kind="gate", origin_weight=0.2, dest_weight=0.5),
        OD(200, 20, name="gate-south", kind="gate", origin_weight=0.2, dest_weight=0.5),
    ]
    sim = Simulation(
        bounds=(0, 0, extent, extent), ods=ods, gridsize=gridsize,
        buildings=houses + [special], topography=topo,
        terrain_cost=TerrainCost(),
        num_agents=int(scenario["num_agents"]),
        release_rate=max(1, int(scenario["num_agents"]) // 5),
        # Cells/step; at 2 m cells ≈ 0.7 m/tick — pack long enough to finish ODs.
        speed=0.35, seed=int(scenario["seed"]),
    )
    from .phases import Phase
    sim.research.phases = [
        Phase("GT-III", "Layer III", 9500, 8800, source="", confidence="inferred",
              colour="#c0504d"),
        Phase("GT-II", "Layer II", 8800, 8000, source="", confidence="inferred",
              colour="#4f81bd"),
    ]
    sim.frame = None
    return sim


def run_scenario(path_or_dict, out_dir: Optional[str] = None, steps: Optional[int] = None,
                 seed: Optional[int] = None) -> RunResult:
    """Run one scenario. ``path_or_dict`` is a YAML path or an already normalised dict.

    The same file and the same seed produce the same occupancy array.
    """
    import time

    from .simulation import Simulation

    if isinstance(path_or_dict, str):
        scenario = load_scenario(path_or_dict)
    else:
        scenario = dict(path_or_dict)
        scenario.setdefault("_hash", scenario_hash(scenario))
    if seed is not None:
        scenario["seed"] = int(seed)
    scene = scenario["scene"]
    t0 = time.perf_counter()
    if scene == "synthetic" or scene.startswith("village:synthetic"):
        sim = synthetic_scene(scenario)
    elif scene == "cluster":
        from . import scenes
        sim = scenes.cluster_scene(cellsize=float(scenario["gridsize"]),
                                   num_agents=int(scenario["num_agents"]),
                                   seed=int(scenario["seed"]))
    elif scene.startswith("village"):
        site = scenario.get("site") or scene.split(":", 1)[-1]
        from . import scenes
        sim = scenes.village_scene(site, cellsize=float(scenario["gridsize"]),
                                   num_agents=int(scenario["num_agents"]),
                                   seed=int(scenario["seed"]))
    else:
        from .regional import regional_scene
        sim = regional_scene(scenario)
    apply_scenario(sim, scenario)
    n_steps = int(steps if steps is not None else scenario["steps"])
    sim.run(n_steps)
    elapsed = time.perf_counter() - t0
    record = build_run_record(scenario, [int(scenario["seed"])], elapsed)
    directory = ""
    if out_dir:
        run_dir = os.path.join(out_dir, record["run_id"])
        write_run_record(run_dir, record)
        np.save(os.path.join(run_dir, "occupancy.npy"), sim.grid.occupancy)
        directory = run_dir
    return RunResult(scenario=scenario, record=record, occupancy=sim.grid.occupancy.copy(),
                     directory=directory)


def rerun_from_record(path: str, out_dir: Optional[str] = None) -> RunResult:
    """Repeat a run from ``run.json`` alone."""
    record = load_run_record(path)
    scenario = normalise(record["scenario"])
    scenario["name"] = record["scenario"].get("name", "rerun")
    scenario["_hash"] = record.get("scenario_hash", scenario_hash(scenario))
    seed = (record.get("seeds") or [scenario["seed"]])[0]
    return run_scenario(scenario, out_dir=out_dir, seed=seed)


def odd_parameter_rows() -> List[Dict[str, str]]:
    """One row per scenario parameter, for the ODD protocol tables."""
    rows = []
    descriptions = {
        "scene": "Which world to build: synthetic, cluster, village:<site>, regional.",
        "time_window": "Study window [end_bc, start_bc], calibrated BC, larger = earlier.",
        "respect_chronology": "If true, trips only run between sites co-occupied in the window.",
        "tau_years": "Years added to both ends of every occupation interval (ASSUMPTION default 0).",
        "undated_policy": "exclude / include / include_flagged for sites with no dates.",
        "overlap_weighting": "Weight a pair by the fraction of the window they share.",
        "pins": "Per-site always_on / always_off overrides.",
        "phase_mode": "manual toggles, or by_time from the window.",
        "active_phases": "Phase ids on when phase_mode is manual.",
        "population": "Path of the population-class table.",
        "tasks": "Path of the task catalogue.",
        "task_allocation": "by_class, or uniform (the null model).",
        "calendar_month": "Month 1–12, or empty for no calendar.",
        "terrain": "Tobler base_speed multiplier, slope_factor, slope_offset, impassable_slope.",
        "num_agents": "Agent pool size.",
        "steps": "Simulation ticks.",
        "seed": "RNG seed. Ensembles use seeds.",
        "gridsize": "Cell size in metres.",
        "od_mode": "uniform trip weights, or gravity (A6).",
        "persons_per_house": "ASSUMPTION. Domestic inhabitants when a building has no override.",
        "persons_per_m2": "ASSUMPTION. Used when population_rule is per_m2.",
        "active_share": "ASSUMPTION. Fraction of daylight spent moving.",
        "family": "Hypothesis family R, G or M, when this scenario came from one.",
    }
    for key, default in DEFAULTS.items():
        rows.append({
            "parameter": key,
            "default": json.dumps(default, ensure_ascii=False),
            "description": descriptions.get(key, ""),
        })
    return rows


def render_odd() -> str:
    """ODD protocol text. The parameter table is generated from the schema defaults."""
    lines = [
        "# ODD protocol for pedsim",
        "",
        "Overview, Design concepts, Details, following Grimm et al. 2020",
        "(*Journal of Artificial Societies and Social Simulation*). `VERIFY` the",
        "citation before it goes into a paper. Parameter tables below are",
        "generated from the scenario defaults (`python -m pedsim.scenario --odd`)",
        "so they stay aligned with the code.",
        "",
        "## 1. Purpose and patterns",
        "",
        "pedsim asks how people moved between and inside the Taş Tepeler sites",
        "under explicit, switchable assumptions about who was there, when, and",
        "what they were walking to do. The patterns it is built to produce are",
        "path density, travel times between sites, and the diagnostic metrics",
        "that separate a residential reading from a gathering-place reading.",
        "",
        "## 2. Entities, state variables and scales",
        "",
        "Entities are agents, origin/destination places, buildings, phases,",
        "population classes, tasks, rivers and sites. Time in the simulation is",
        "a tick; reported times are minutes of walking from Tobler's function.",
        "Archaeological time is calibrated BC. Space is metres in a local frame",
        "on UTM zone 37N (EPSG:32637).",
        "",
        "## 3. Process overview and scheduling",
        "",
        "Each tick, every active agent scans a vision cone over the cost field,",
        "steps, and deposits occupancy. A finished agent draws a new trip,",
        "filtered by chronology, phase and (when enabled) the task catalogue.",
        "Cost fields are rebuilt when geometry, season or terrain parameters change,",
        "and reused when only the time window changes.",
        "",
        "## 4. Design concepts",
        "",
        "Agents do not follow the least-cost path. They walk toward the longest",
        "visible cheaper cell, so the empirical travel time can exceed the",
        "least-cost time. Interaction is indirect, through occupancy and shared",
        "destinations. Stochasticity is the RNG named by the scenario seed.",
        "Observation is the occupancy array, the trip log and the run record.",
        "",
        "## 5. Initialisation",
        "",
        "The scenario file names the scene, the seed, the agent count and every",
        "toggle. Defaults live in `pedsim.scenario.DEFAULTS` and are copied into",
        "`run.json`.",
        "",
        "## 6. Input data",
        "",
        "Copernicus DEM, HydroRIVERS, the site catalogue, plan geometry, and the",
        "YAML tables for population, tasks, calendar and phases. Missing dates",
        "and coordinates are not filled in.",
        "",
        "## 7. Submodels",
        "",
        "Tobler's hiking function; seasonal river friction; co-occupation;",
        "task chains; optional gravity weights. Each `ASSUMPTION` is a parameter.",
        "",
        "## Parameter table (generated)",
        "",
        "| Parameter | Default | Meaning |",
        "|---|---|---|",
    ]
    for row in odd_parameter_rows():
        default = row["default"].replace("|", "\\|")
        lines.append(f"| `{row['parameter']}` | `{default}` | {row['description']} |")
    lines.append("")
    return "\n".join(lines)


def write_odd(path: str) -> str:
    text = render_odd()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def main(argv=None) -> int:
    """``python -m pedsim.scenario --odd`` rewrites ``docs/ODD.md``."""
    import argparse

    parser = argparse.ArgumentParser(prog="pedsim.scenario")
    parser.add_argument("--odd", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.odd:
        path = args.out or os.path.abspath(os.path.join(package_root(), "..", "docs", "ODD.md"))
        write_odd(path)
        print(path)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

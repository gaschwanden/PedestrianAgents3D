"""Residential, gathering and mixed scenario families, and the metrics that
tell them apart.

The families are parameter files, not conclusions. R and G differ in who
starts a trip and where it ends. The report says whether a metric's ensemble
spread overlaps, and it refuses to call a difference "clear" when it does not.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .scenario import apply_scenario, normalise, synthetic_scene
from .tables import write_table

FAMILIES = {
    "R": (
        "Residential. Agents live in the domestic buildings and spend the day "
        "on water, resources and the occasional visit to a special building."
    ),
    "G": (
        "Gathering. A small resident core plus visitors who arrive at the "
        "perimeter gates and walk to the special buildings. Movement peaks "
        "when the calendar says there is an event."
    ),
    "M": (
        "Mixed. A share α of trips are visitors (G) and the rest are residents (R). "
        "α is the scenario key visitor_share."
    ),
}


def list_families() -> List[Tuple[str, str]]:
    return [(key, text) for key, text in FAMILIES.items()]


def family_scenario(family: str, site: str = "Göbeklitepe", seed: int = 1,
                    alpha: float = 0.5, steps: int = 40, num_agents: int = 30) -> dict:
    """A normalised scenario for one family. The scene is the synthetic village
    unless the caller swaps ``scene`` for a geodata-backed one."""
    family = family.upper()
    if family not in FAMILIES and not family.startswith("M"):
        raise KeyError(f"unknown family {family!r}")
    raw = {
        "name": f"{family}-{site}",
        "scene": "synthetic",
        "site": site,
        "family": "M" if family.startswith("M") else family,
        "seed": seed,
        "steps": steps,
        "num_agents": num_agents,
        "respect_chronology": True,
        "population": "",
        "tasks": "",
        "notes": FAMILIES["M" if family.startswith("M") else family],
    }
    scenario = normalise(raw)
    scenario["name"] = raw["name"]
    scenario["_visitor_share"] = float(alpha)
    return scenario


def _apply_family_weights(sim, family: str, alpha: float) -> None:
    """Retarget the synthetic village's OD weights. Does not touch geometry."""
    family = "M" if family.upper().startswith("M") else family.upper()
    for od in sim.ods:
        if od is None:
            continue
        if family == "R":
            if od.kind == "house":
                od.origin_weight, od.dest_weight = 1.0, 0.3
            elif od.kind == "water":
                od.origin_weight, od.dest_weight = 0.0, 1.0
            elif od.kind == "special":
                od.origin_weight, od.dest_weight = 0.05, 0.3
            elif od.kind == "gate":
                od.origin_weight, od.dest_weight = 0.0, 0.05
        elif family == "G":
            if od.kind == "house":
                od.origin_weight, od.dest_weight = 0.05, 0.05
            elif od.kind == "gate":
                od.origin_weight, od.dest_weight = 1.0, 0.2
            elif od.kind == "special":
                od.origin_weight, od.dest_weight = 0.0, 1.0
            elif od.kind == "water":
                od.origin_weight, od.dest_weight = 0.0, 0.2
        else:
            # Mix: interpolate the two weight pairs.
            pass
    if family == "M":
        # Build by blending a copy of the R and G assignments.
        for od in sim.ods:
            if od is None:
                continue
            if od.kind == "house":
                r, g = (1.0, 0.3), (0.05, 0.05)
            elif od.kind == "gate":
                r, g = (0.0, 0.05), (1.0, 0.2)
            elif od.kind == "special":
                r, g = (0.05, 0.3), (0.0, 1.0)
            elif od.kind == "water":
                r, g = (0.0, 1.0), (0.0, 0.2)
            else:
                continue
            od.origin_weight = (1 - alpha) * r[0] + alpha * g[0]
            od.dest_weight = (1 - alpha) * r[1] + alpha * g[1]


def gini(values) -> float:
    """Gini coefficient of a non-negative array. 0 is even, 1 is concentrated."""
    v = np.sort(np.asarray(values, dtype=float).ravel())
    v = v[np.isfinite(v)]
    v = v[v >= 0]
    if v.size == 0 or float(v.sum()) <= 0:
        return 0.0
    n = v.size
    index = np.arange(1, n + 1)
    return float((2.0 * np.sum(index * v) / (n * np.sum(v))) - (n + 1) / n)


def _cells_of(sim, kind: str) -> np.ndarray:
    """Boolean mask of cells inside buildings of a function (or OD kind)."""
    mask = np.zeros(sim.grid.occupancy.shape, dtype=bool)
    for b in sim.buildings:
        if getattr(b, "function", "") != kind:
            continue
        poly = b.footprint.as_xy()
        if len(poly) < 3:
            continue
        minx, miny, maxx, maxy = b.bbox()
        for i, x in enumerate(sim.grid.xs):
            if x < minx or x > maxx:
                continue
            for j, y in enumerate(sim.grid.ys):
                if miny <= y <= maxy and b.contains(float(x), float(y)):
                    mask[i, j] = True
    return mask


def diagnostics(sim, arrivals_by_step: Optional[Sequence[float]] = None) -> Dict[str, float]:
    """The six A1 metrics. Units are in :data:`METRIC_UNITS`."""
    occ = np.asarray(sim.grid.occupancy, dtype=float)
    total = float(occ.sum()) or 1.0
    special = _cells_of(sim, "special")
    domestic = _cells_of(sim, "domestic")
    special_share = float(occ[special].sum() / total) if special.any() else 0.0
    # (1) special vs domestic: share of movement on special cells
    domestic_share = float(occ[domestic].sum() / total) if domestic.any() else 0.0
    # (3) peak-to-mean of arrivals. A flat run is 1.
    if arrivals_by_step:
        arr = np.asarray(arrivals_by_step, dtype=float)
        peak = float(arr.max() / arr.mean()) if arr.mean() > 0 else 1.0
    else:
        peak = 1.0
    # (4) origin mix: share of logged trips that started at a gate
    log = getattr(sim, "trip_log", [])
    if log:
        outside = sum(1 for rec in log if rec.get("origin_kind") in ("gate", "site"))
        origin_mix = outside / len(log)
    else:
        gate_w = sum(od.origin_weight for od in sim.ods if od is not None and od.kind == "gate")
        all_w = sum(od.origin_weight for od in sim.ods if od is not None)
        origin_mix = gate_w / all_w if all_w else 0.0
    # (5) corridor cells: occupancy above the 90th percentile of the positive cells
    positive = occ[occ > 0]
    if positive.size:
        cut = float(np.percentile(positive, 90))
        corridor_cells = int((occ >= cut).sum())
    else:
        corridor_cells = 0
    corridor_km = corridor_cells * sim.grid.gridsize / 1000.0
    # (6) density at water, per resident
    water = [od for od in sim.ods if od is not None and od.kind == "water"]
    water_sum = 0.0
    for od in water:
        i = min(max(sim.grid.cell_x(od.x), 0), sim.grid.nx - 1)
        j = min(max(sim.grid.cell_y(od.y), 0), sim.grid.ny - 1)
        water_sum += float(occ[i, j])
    residents = sim.population_count() or float(sim.num_agents)
    return {
        "special_share": special_share,
        "domestic_share": domestic_share,
        "gini": gini(occ),
        "peak_to_mean": peak,
        "origin_mix": float(origin_mix),
        "corridor_km": float(corridor_km),
        "water_per_resident": water_sum / residents,
    }


METRIC_UNITS = {
    "family": "",
    "seed": "",
    "special_share": "1",
    "domestic_share": "1",
    "gini": "1",
    "peak_to_mean": "1",
    "origin_mix": "1",
    "corridor_km": "km",
    "water_per_resident": "visits/person",
}

METRIC_COLUMNS = list(METRIC_UNITS)


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta of ``a`` against ``b``. Positive means ``a`` tends to be larger."""
    aa = list(a)
    bb = list(b)
    if not aa or not bb:
        return 0.0
    gt = lt = 0
    for x in aa:
        for y in bb:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    return (gt - lt) / (len(aa) * len(bb))


def intervals_overlap(a: Sequence[float], b: Sequence[float], low: float = 5, high: float = 95) -> bool:
    if len(a) == 0 or len(b) == 0:
        return True
    a_lo, a_hi = np.percentile(a, [low, high])
    b_lo, b_hi = np.percentile(b, [low, high])
    return not (a_hi < b_lo or b_hi < a_lo)


def run_family(family: str, site: str = "Göbeklitepe", seed: int = 1,
               steps: int = 25, num_agents: int = 20, alpha: float = 0.5):
    """Run one family on the synthetic village. Returns ``(sim, metrics)``."""
    scenario = family_scenario(family, site=site, seed=seed, alpha=alpha,
                               steps=steps, num_agents=num_agents)
    sim = synthetic_scene(scenario)
    apply_scenario(sim, scenario)
    _apply_family_weights(sim, family, alpha)
    sim.run(steps)
    return sim, diagnostics(sim)


def compare(families: Sequence[str], site: str = "Göbeklitepe", seeds: Sequence[int] = (1,),
            steps: int = 20, num_agents: int = 16, out_dir: Optional[str] = None,
            evidence: Optional[Dict[str, str]] = None) -> str:
    """Run each family on the same seeds and write ``metrics.csv`` and ``report.md``."""
    evidence = evidence or {}
    rows = []
    by_family: Dict[str, List[dict]] = {f: [] for f in families}
    for family in families:
        for seed in seeds:
            _sim, metrics = run_family(family, site=site, seed=int(seed),
                                       steps=steps, num_agents=num_agents)
            metrics = dict(metrics)
            metrics["family"] = family
            metrics["seed"] = int(seed)
            by_family[family].append(metrics)
            rows.append(metrics)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        write_table(
            os.path.join(out_dir, "metrics.csv"),
            METRIC_COLUMNS,
            [[r.get(c, "") for c in METRIC_COLUMNS] for r in rows],
            METRIC_UNITS,
        )
    lines = [
        f"# Comparison: {', '.join(families)}",
        "",
        f"Site label: {site}. Seeds: {list(seeds)}.",
        "",
        "## What each family is",
        "",
    ]
    for family in families:
        key = "M" if str(family).upper().startswith("M") else str(family).upper()
        lines.append(f"- **{family}.** {FAMILIES.get(key, '')}")
    lines += ["", "## Separations", "",
              "| Metric | Cliff's delta | 90% intervals overlap | Reading | Evidence |",
              "|---|---|---|---|---|"]
    metric_keys = [k for k in METRIC_UNITS if k not in ("family", "seed")]
    if len(families) >= 2:
        left, right = families[0], families[1]
        for key in metric_keys:
            a = [m[key] for m in by_family[left]]
            b = [m[key] for m in by_family[right]]
            delta = cliffs_delta(a, b)
            overlap = intervals_overlap(a, b)
            if overlap:
                reading = f"{key} does not separate {left} and {right}"
            else:
                reading = f"{key} separates {left} and {right} clearly"
            ev = evidence.get(key, "") or "to be defined"
            lines.append(f"| {key} | {delta:.2f} | {'yes' if overlap else 'no'} | {reading} | {ev} |")
    lines += [
        "",
        "The null model (`task_allocation: uniform`) is the baseline a report",
        "should be read against: every class does every task at the same speed.",
        "",
    ]
    text = "\n".join(lines)
    if out_dir:
        with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def distribute_arrivals(bearings_deg: Sequence[float],
                        gates: Sequence[Tuple[str, float]]) -> Dict[str, int]:
    """Send each arrival to the gate whose bearing is closest.

    ``gates`` is ``(name, bearing_degrees)``. Used to check that village gate
    counts follow the cluster arrivals in each sector (A1-02).
    """
    counts = {name: 0 for name, _ in gates}
    if not gates:
        return counts
    for bearing in bearings_deg:
        best = None
        best_d = 1e9
        for name, gate_bearing in gates:
            d = abs((bearing - gate_bearing + 180) % 360 - 180)
            if d < best_d:
                best_d = d
                best = name
        counts[best] += 1
    return counts


def rank_scenarios(observed: np.ndarray, candidates: Dict[str, np.ndarray]) -> List[Tuple[str, float]]:
    """Spearman correlation of each candidate density with an observed raster.

    Highest correlation first. Used by the inverse check (A1-06).
    """
    def rankdata(a):
        order = np.argsort(a)
        ranks = np.empty(len(a), dtype=float)
        ranks[order] = np.arange(1, len(a) + 1)
        return ranks

    obs = rankdata(np.asarray(observed, dtype=float).ravel())
    scored = []
    for name, field in candidates.items():
        r = rankdata(np.asarray(field, dtype=float).ravel())
        if obs.std() == 0 or r.std() == 0:
            corr = 0.0
        else:
            corr = float(np.corrcoef(obs, r)[0, 1])
        scored.append((name, corr))
    scored.sort(key=lambda item: -item[1])
    return scored

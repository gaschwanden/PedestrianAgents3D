"""A third scale: obsidian sources to the Taş Tepeler sites.

The scene can be built from a Copernicus GLO-90 raster when one is on disk.
Without it, :func:`regional_scene` builds a coarse synthetic surface so the
cost table, the distance-decay fit and the tests still run. Source coordinates
in the YAML are ``VERIFY`` until the researcher replaces them.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def config_sources(path: Optional[str] = None) -> List[dict]:
    from .scenario import config_path, load_yaml

    path = path or config_path("obsidian_sources.yaml")
    data = load_yaml(path)
    sources = []
    for entry in data.get("sources", []):
        if entry.get("lat") is None or entry.get("lon") is None:
            continue
        sources.append({
            "id": str(entry["id"]),
            "name": str(entry.get("name", entry["id"])),
            "lat": float(entry["lat"]),
            "lon": float(entry["lon"]),
            "attractiveness": float(entry.get("attractiveness", 1.0)),
            "source": str(entry.get("source", "")),
            "confidence": str(entry.get("confidence", "assumption")),
        })
    return sources


def load_observations(path: str, source_ids: Sequence[str], site_names: Sequence[str]) -> dict:
    """CSV ``site, source_group, n_pieces, reference``. Unknown names are listed."""
    import csv

    known_s = {s.casefold(): s for s in source_ids}
    known_t = {s.casefold(): s for s in site_names}
    counts = {(s, t): 0.0 for s in source_ids for t in site_names}
    unmatched = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            site = (row.get("site") or "").strip()
            group = (row.get("source_group") or "").strip()
            try:
                n = float(row.get("n_pieces") or 0)
            except ValueError:
                unmatched.append(row)
                continue
            sk = known_s.get(group.casefold())
            tk = known_t.get(site.casefold())
            if sk is None or tk is None:
                unmatched.append({"site": site, "source_group": group, "n_pieces": n})
                continue
            counts[(sk, tk)] += n
    matrix = np.array([[counts[(s, t)] for t in site_names] for s in source_ids], dtype=float)
    return {"counts": matrix, "sources": list(source_ids), "sites": list(site_names),
            "unmatched": unmatched}


def predicted_shares(times_h: np.ndarray, attractiveness: Sequence[float],
                     beta: float, kind: str = "power") -> np.ndarray:
    """``p_sj ∝ A_s * f(t_sj)``, columns sum to 1. ``times_h`` is hours."""
    t = np.maximum(np.asarray(times_h, dtype=float), 1e-3)
    A = np.asarray(attractiveness, dtype=float)
    if kind == "exponential":
        f = np.exp(-beta * t)
    else:
        f = np.power(t, -beta)
    raw = A[:, None] * f
    total = raw.sum(axis=0, keepdims=True)
    total[total <= 0] = 1.0
    return raw / total


def multinomial_nll(counts: np.ndarray, probs: np.ndarray) -> float:
    p = np.clip(probs, 1e-12, 1.0)
    return float(-np.sum(counts * np.log(p)))


def fit_beta(counts: np.ndarray, times_h: np.ndarray, attractiveness: Sequence[float],
             kind: str = "power", betas: Optional[Sequence[float]] = None) -> dict:
    """Grid search for β. Returns the best β, the probabilities and the NLL."""
    if betas is None:
        betas = np.linspace(0.2, 4.0, 39)
    best = None
    for beta in betas:
        probs = predicted_shares(times_h, attractiveness, float(beta), kind)
        loss = multinomial_nll(counts, probs)
        if best is None or loss < best["nll"]:
            best = {"beta": float(beta), "nll": loss, "probs": probs, "kind": kind}
    return best


def aic(nll: float, k: int) -> float:
    return 2.0 * k + 2.0 * nll


def compare_distance(counts: np.ndarray, cost_hours: np.ndarray, euclidean_hours: np.ndarray,
                     attractiveness: Sequence[float]) -> dict:
    """Fit β on cost distance and on straight-line time. Report ΔAIC.

    Negative ``delta_aic_cost_minus_euclidean`` means the cost model fits better.
    """
    cost = fit_beta(counts, cost_hours, attractiveness)
    straight = fit_beta(counts, euclidean_hours, attractiveness)
    return {
        "cost": cost,
        "euclidean": straight,
        "aic_cost": aic(cost["nll"], 1),
        "aic_euclidean": aic(straight["nll"], 1),
        "delta_aic_cost_minus_euclidean": aic(cost["nll"], 1) - aic(straight["nll"], 1),
    }


def down_the_line(times_h: np.ndarray, loss: float = 0.3) -> np.ndarray:
    """Share of a source's material that survives a chain of handovers.

    ``times_h[s, j]`` is not used for the path; the chain is the order of
    sites by increasing time from that source, and each handover keeps
    ``1 - loss``. Column ``j`` is renormalised across sources. This is the
    alternative to direct access, not a claim about how obsidian moved.
    """
    n_sources, n_sites = times_h.shape
    raw = np.zeros_like(times_h, dtype=float)
    keep = 1.0 - float(loss)
    for s in range(n_sources):
        order = np.argsort(times_h[s])
        for hop, j in enumerate(order):
            raw[s, j] = keep ** hop
    total = raw.sum(axis=0, keepdims=True)
    total[total <= 0] = 1.0
    return raw / total


def regional_scene(scenario: Optional[dict] = None):
    """A coarse scene covering a few hundred kilometres, synthetic unless a DEM is named.

    The scenario's ``gridsize`` is the cell size in metres. The default extent
    is large and the default cell is 5 km, so the grid stays small.
    """
    from .od import OD
    from .simulation import Simulation
    from .topography import TerrainCost, Topography

    scenario = scenario or {}
    cell = float(scenario.get("gridsize") or 5000.0)
    extent = float(scenario.get("extent_m") or 400_000.0)
    n = max(8, int(extent / cell))
    # a gentle ridge so the two directions of travel are not identical
    xs = np.linspace(0, 1, n)[:, None]
    ys = np.linspace(0, 1, n)[None, :]
    elev = 800.0 + 400.0 * xs + 80.0 * np.sin(6 * ys)
    topo = Topography(elev, 0.0, 0.0, cell)
    sources = [
        OD(cell, cell, name="bingol", kind="quarry", site="Bingöl", origin_weight=1, dest_weight=0),
        OD(extent - 2 * cell, cell, name="gollu", kind="quarry", site="Göllü Dağ",
           origin_weight=1, dest_weight=0),
    ]
    sites = [
        OD(extent * 0.45, extent * 0.55, name="Göbeklitepe", kind="site", site="Göbeklitepe",
           origin_weight=0, dest_weight=1),
        OD(extent * 0.6, extent * 0.4, name="Karahantepe", kind="site", site="Karahantepe",
           origin_weight=0, dest_weight=1),
    ]
    sim = Simulation(
        bounds=(0, 0, extent, extent), ods=sources + sites, gridsize=cell,
        topography=topo, terrain_cost=TerrainCost(),
        num_agents=int(scenario.get("num_agents") or 10),
        seed=int(scenario.get("seed") or 1),
    )
    sim.scene_scale = "regional"
    return sim


def source_site_table(sim, walking_day_h: float = 8.0, season: str = "") -> List[dict]:
    """Least-cost hours and days from each quarry OD to each site OD."""
    from .tasks import trip_minutes

    sources = [(i, od) for i, od in enumerate(sim.ods) if od is not None and od.kind == "quarry"]
    sites = [(i, od) for i, od in enumerate(sim.ods) if od is not None and od.kind == "site"]
    rows = []
    for si, source in sources:
        for ti, site in sites:
            minutes = trip_minutes(sim, si, ti, 1.0)
            hours = minutes / 60.0 if math.isfinite(minutes) else math.inf
            rows.append({
                "source": source.site or source.name,
                "site": site.site or site.name,
                "t_hours": None if not math.isfinite(hours) else round(hours, 2),
                "t_days": None if not math.isfinite(hours) else round(hours / walking_day_h, 2),
                "season": season,
            })
    return rows


def synthetic_counts(times_h: np.ndarray, beta: float, n_per_site: int,
                     rng: np.random.Generator, kind: str = "power") -> np.ndarray:
    """Counts drawn from a known β, for the recovery test."""
    A = np.ones(times_h.shape[0])
    probs = predicted_shares(times_h, A, beta, kind)
    counts = np.zeros_like(probs)
    for j in range(probs.shape[1]):
        counts[:, j] = rng.multinomial(n_per_site, probs[:, j])
    return counts


def glo90_script() -> str:
    """Instructions for fetching GLO-90. The file is large and is not downloaded here."""
    return (
        "Copernicus GLO-90 is available from the Copernicus Data Space as the "
        "COP-DEM_GLO-90 collection. Download the tiles that cover 36–42° N, "
        "35–42° E (the sources and the cluster) into data/raw/ and point "
        "PEDSIM_DATA at that directory. Reservoir masks for Atatürk and Keban "
        "are an ASSUMPTION until a sourced polygon is added under "
        "python/data/config/reservoirs.geojson."
    )

"""One-at-a-time effects and a small Morris screening.

The model is any function ``evaluate(params) -> metrics dict``. The cluster
scene is one such function; the tests use a cheap stand-in so the ranking
can be checked without an 80 km Dijkstra.
"""
from __future__ import annotations

import csv
import os
from typing import Callable, Dict, List, Sequence

import numpy as np


def one_at_a_time(evaluate: Callable, baseline: Dict[str, float],
                  ranges: Dict[str, float]) -> List[dict]:
    """Move each parameter by ± its range, holding the others at baseline.

    The reported effect is the mean absolute change in each metric.
    """
    base_metrics = evaluate(dict(baseline))
    rows = []
    for name, delta in ranges.items():
        effects = {}
        for sign in (-1.0, 1.0):
            trial = dict(baseline)
            trial[name] = baseline[name] + sign * delta
            metrics = evaluate(trial)
            for key, value in metrics.items():
                effects.setdefault(key, []).append(abs(float(value) - float(base_metrics[key])))
        for key, diffs in effects.items():
            rows.append({
                "parameter": name,
                "metric": key,
                "effect": float(np.mean(diffs)),
            })
    rows.sort(key=lambda r: -r["effect"])
    return rows


def morris(evaluate: Callable, baseline: Dict[str, float], ranges: Dict[str, float],
           r: int = 4, rng: np.random.Generator = None) -> List[dict]:
    """Morris elementary effects. ``r`` trajectories, one step per parameter."""
    rng = rng or np.random.default_rng(0)
    names = list(ranges)
    effects = {name: [] for name in names}
    for _ in range(r):
        point = {}
        for name in names:
            low = baseline[name] - ranges[name]
            high = baseline[name] + ranges[name]
            point[name] = float(rng.uniform(low, high))
        current = evaluate(point)
        order = list(names)
        rng.shuffle(order)
        for name in order:
            step = ranges[name] if rng.random() < 0.5 else -ranges[name]
            nxt = dict(point)
            nxt[name] = point[name] + step
            metrics = evaluate(nxt)
            # elementary effect on the first metric, scaled by the step
            key = next(iter(metrics))
            ee = (float(metrics[key]) - float(current[key])) / step if step else 0.0
            effects[name].append(ee)
            point, current = nxt, metrics
    rows = []
    for name, values in effects.items():
        arr = np.asarray(values, dtype=float)
        rows.append({
            "parameter": name,
            "mu_star": float(np.mean(np.abs(arr))) if arr.size else 0.0,
            "sigma": float(arr.std()) if arr.size else 0.0,
        })
    rows.sort(key=lambda r: -r["mu_star"])
    return rows


def write_ranking(path: str, rows: Sequence[dict]) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if not rows:
        raise ValueError("no sensitivity rows")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path

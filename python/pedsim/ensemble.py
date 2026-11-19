"""Several runs, summarised as mean, spread and an exceedance probability.

The factory is ``fn(seed) -> Simulation`` and must already have been run, or
pass ``steps`` and this module will call ``run``. Date bounds and coordinates
are sampled only when the caller passes a ``sample`` hook; the hook is how
CHR-06 and the palaeo uncertainty enter without this module knowing either.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

import numpy as np

BANDS = ("mean", "sd", "p05", "p95", "p_exceed")


def summarise(stack: np.ndarray, threshold: float) -> Dict[str, np.ndarray]:
    """``stack`` is ``[n_runs, nx, ny]`` occupancy (or any non-negative field)."""
    data = np.asarray(stack, dtype=float)
    return {
        "mean": data.mean(axis=0),
        "sd": data.std(axis=0),
        "p05": np.percentile(data, 5, axis=0),
        "p95": np.percentile(data, 95, axis=0),
        "p_exceed": (data > threshold).mean(axis=0),
    }


def run_ensemble(factory: Callable[[int], object], n: int = 30, steps: int = 20,
                 threshold: float = 1.0, seed0: int = 0) -> Dict[str, np.ndarray]:
    """Run ``n`` seeds. ``factory(seed)`` returns a simulation that is then run."""
    fields = []
    for k in range(n):
        sim = factory(seed0 + k)
        if steps:
            sim.run(steps)
        fields.append(np.array(sim.grid.occupancy, dtype=float, copy=True))
    return summarise(np.stack(fields, axis=0), threshold)


def sample_inputs(rng: np.random.Generator, spec: dict) -> dict:
    """Draw one realisation of a declared uncertainty spec.

    ``spec`` maps a parameter name to ``{"mean", "sd", "low", "high"}``.
    Values are clipped to ``[low, high]`` when those bounds are present.
    This is the hook X-03 uses for ``ASSUMPTION`` ranges and date SDs.
    """
    drawn = {}
    for name, item in spec.items():
        mean = float(item.get("mean", 0.0))
        sd = float(item.get("sd", 0.0))
        value = float(rng.normal(mean, sd)) if sd else mean
        if "low" in item:
            value = max(value, float(item["low"]))
        if "high" in item:
            value = min(value, float(item["high"]))
        drawn[name] = value
    return drawn

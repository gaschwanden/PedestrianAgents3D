"""Weighted random draw, mirroring ``MyMath.WeightedDrawf`` from the Java code."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


def weighted_draw(
    weights: Sequence[float],
    rng: np.random.Generator,
    ignore_index: Optional[int] = None,
) -> int:
    """Return an index drawn with probability proportional to ``weights``.

    Returns ``-1`` when the total weight is zero (matching the original API).
    ``ignore_index`` optionally excludes one entry (used so a trip does not pick
    the same place as both origin and destination).
    """
    total = 0.0
    for i, w in enumerate(weights):
        if i == ignore_index:
            continue
        total += w * 100.0
    if total <= 0:
        return -1
    r = rng.random() * total
    hit = 0.0
    for i, w in enumerate(weights):
        if i == ignore_index:
            continue
        hit += w * 100.0
        if hit >= r:
            return i
    return -1

"""Convert Dijkstra cost into walking minutes.

The stock :class:`~pedsim.topography.TerrainCost` uses ``base_speed`` as a
unitless multiplier on Tobler's on-the-flat pace. A Dijkstra step costs
``horizontal_metres / (base_speed * slope_term)``, so ``cost * base_speed`` is
the equivalent flat distance in metres. Dividing by Tobler's flat speed
(about 5.04 km/h) turns that into hours.

``ASSUMPTION``: when the cost field is a plain flood-fill (no elevation), each
step is treated as one cell of flat walking at the same pace.
"""
from __future__ import annotations

import math

#: ``6 * exp(-3.5 * |0.05|)`` km/h, Tobler's speed on level ground.
TOBLER_FLAT_KMH = 6.0 * math.exp(-3.5 * 0.05)


def cost_to_minutes(cost: float, base_speed: float = 1.0,
                    flat_kmh: float = TOBLER_FLAT_KMH) -> float:
    """Minutes implied by one Dijkstra cost value. Non-finite cost -> inf."""
    if cost is None or not math.isfinite(cost):
        return math.inf
    pace = flat_kmh if flat_kmh > 0 else TOBLER_FLAT_KMH
    return float(cost) * float(base_speed) / pace * 0.06


def metres_to_minutes(metres: float, speed_factor: float = 1.0,
                      flat_kmh: float = TOBLER_FLAT_KMH) -> float:
    """Minutes to walk ``metres`` on the flat at ``speed_factor`` × Tobler."""
    if not math.isfinite(metres):
        return math.inf
    kmh = flat_kmh * max(speed_factor, 1e-3)
    return max(metres, 0.0) / 1000.0 / kmh * 60.0


def format_minutes(minutes: float) -> str:
    """``h:mm`` for the UI. Data files keep decimal minutes."""
    if not math.isfinite(minutes):
        return "—"
    total = int(round(minutes))
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 60}:{total % 60:02d}"

"""Occupation intervals, co-occupation and the active set inside a time window.

Dates are calibrated BC as positive integers, larger = earlier, matching
:class:`pedsim.sites.Site`. An interval is closed on both ends and written
``[end_bc, start_bc]``: Göbeklitepe is ``[8000, 9500]``. Overlap is counted in
inclusive years (``start - end + 1``), which is what makes a tolerance of 250
years just close a 500-year gap and a tolerance of 249 years leave it open.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Interval:
    """Closed cal-BC range. ``end_bc`` is the later year, ``start_bc`` the earlier."""

    end_bc: int
    start_bc: int

    def __post_init__(self) -> None:
        if int(self.start_bc) < int(self.end_bc):
            raise ValueError(
                f"interval start_bc ({self.start_bc}) is later than end_bc ({self.end_bc}); "
                "larger means earlier"
            )

    def widened(self, tau: int) -> "Interval":
        """Push both ends out by ``tau`` years. ``tau`` < 0 is rejected."""
        t = int(tau)
        if t < 0:
            raise ValueError("tolerance τ must be ≥ 0")
        return Interval(int(self.end_bc) - t, int(self.start_bc) + t)

    def years(self) -> int:
        return int(self.start_bc) - int(self.end_bc) + 1

    def overlaps(self, other: "Interval") -> bool:
        return max(self.end_bc, other.end_bc) <= min(self.start_bc, other.start_bc)

    def intersection(self, other: "Interval") -> Optional["Interval"]:
        end = max(int(self.end_bc), int(other.end_bc))
        start = min(int(self.start_bc), int(other.start_bc))
        if start < end:
            return None
        return Interval(end, start)

    def label(self) -> str:
        return f"{self.start_bc}–{self.end_bc} cal BC"


def site_interval(site, tau: int = 0) -> Optional[Interval]:
    """Occupation interval, or ``None`` when either bound is missing."""
    if getattr(site, "start_bc", None) is None or getattr(site, "end_bc", None) is None:
        return None
    return Interval(int(site.end_bc), int(site.start_bc)).widened(tau)


def _pin(site, pins: Optional[Dict[str, str]]) -> str:
    if pins and site.name in pins:
        return pins[site.name]
    return getattr(site, "pin", None) or ""


def active(site, window: Interval, tau: int = 0,
           undated_policy: str = "exclude",
           pins: Optional[Dict[str, str]] = None) -> bool:
    """Whether ``site`` is inhabited somewhere inside ``window``.

    ``undated_policy`` is ``exclude`` (default), ``include`` or
    ``include_flagged``. The flagged variant still counts as active; callers
    paint it differently via :func:`is_flagged`.
    """
    pin = _pin(site, pins)
    if pin == "always_off":
        return False
    if pin == "always_on":
        return True
    occ = site_interval(site, tau)
    if occ is None:
        return undated_policy in ("include", "include_flagged")
    return occ.overlaps(window)


def is_flagged(site, undated_policy: str = "exclude") -> bool:
    """Undated site drawn hatched when the policy is ``include_flagged``."""
    undated = getattr(site, "start_bc", None) is None or getattr(site, "end_bc", None) is None
    return undated and undated_policy == "include_flagged"


def _effective_interval(site, window: Interval, tau: int,
                        undated_policy: str,
                        pins: Optional[Dict[str, str]]) -> Optional[Interval]:
    """Interval used for overlap math, after pins and the undated policy."""
    pin = _pin(site, pins)
    if pin == "always_off":
        return None
    if pin == "always_on":
        return window
    occ = site_interval(site, tau)
    if occ is None:
        if undated_policy in ("include", "include_flagged"):
            return window
        return None
    return occ


def overlap_years(a, b, window: Interval, tau: int = 0,
                  undated_policy: str = "exclude",
                  pins: Optional[Dict[str, str]] = None) -> int:
    """Inclusive years in ``O_a ∩ O_b ∩ W`` after widening by ``tau``."""
    ia = _effective_interval(a, window, tau, undated_policy, pins)
    ib = _effective_interval(b, window, tau, undated_policy, pins)
    if ia is None or ib is None:
        return 0
    both = ia.intersection(ib)
    if both is None:
        return 0
    in_window = both.intersection(window)
    if in_window is None:
        return 0
    return in_window.years()


def co_occupied(a, b, window: Interval, tau: int = 0,
                undated_policy: str = "exclude",
                pins: Optional[Dict[str, str]] = None) -> bool:
    """True when some year inside the window belongs to both occupations."""
    return overlap_years(a, b, window, tau, undated_policy, pins) > 0


def overlap_weight(a, b, window: Interval, tau: int = 0,
                   undated_policy: str = "exclude",
                   pins: Optional[Dict[str, str]] = None) -> float:
    """``|O_a ∩ O_b ∩ W| / |W|``. Zero when the pair is not co-occupied."""
    years = overlap_years(a, b, window, tau, undated_policy, pins)
    span = window.years()
    if span <= 0:
        return 0.0
    return years / span


def pair_matrix(sites: Sequence, window: Interval, tau: int = 0,
                undated_policy: str = "exclude",
                pins: Optional[Dict[str, str]] = None
                ) -> Tuple[np.ndarray, np.ndarray]:
    """Boolean co-occupation and float overlap weights, both ``[n, n]``."""
    n = len(sites)
    mask = np.zeros((n, n), dtype=bool)
    weights = np.zeros((n, n), dtype=float)
    for i, a in enumerate(sites):
        for j, b in enumerate(sites):
            years = overlap_years(a, b, window, tau, undated_policy, pins)
            if years > 0:
                mask[i, j] = True
                weights[i, j] = years / window.years()
    return mask, weights


def period_group(site, origin_bc: int = 10000, bin_years: int = 500) -> int:
    """Chronology bin of a site's occupation midpoint.

    Bin 0 is the oldest (midpoint at or before ``origin_bc``). This replaces
    the hard-coded PPNA/PPNB split that used to live in ``geo.site_ods``.
    Undated sites stay in group 0 and are not silently given a period.
    """
    if getattr(site, "start_bc", None) is None or getattr(site, "end_bc", None) is None:
        return 0
    mid = 0.5 * (float(site.start_bc) + float(site.end_bc))
    if mid >= origin_bc:
        return 0
    return int((origin_bc - mid) // bin_years)


def sample_interval(site, rng: np.random.Generator, tau: int = 0) -> Optional[Interval]:
    """Draw occupation bounds from their SDs. Truncated so start ≥ end.

    Missing SDs keep the published bound. A site with no dates returns ``None``.
    """
    if getattr(site, "start_bc", None) is None or getattr(site, "end_bc", None) is None:
        return None
    start = float(site.start_bc)
    end = float(site.end_bc)
    sd_s = getattr(site, "start_bc_sd", None)
    sd_e = getattr(site, "end_bc_sd", None)
    if sd_s:
        start = float(rng.normal(start, float(sd_s)))
    if sd_e:
        end = float(rng.normal(end, float(sd_e)))
    start_i = int(round(start))
    end_i = int(round(end))
    if start_i < end_i:
        start_i, end_i = end_i, start_i
    return Interval(end_i, start_i).widened(0 if tau == 0 else 0)


def co_occupation_probability(sites: Sequence, window: Interval, rng: np.random.Generator,
                              n: int = 200, tau: int = 0) -> np.ndarray:
    """Share of date draws in which each pair is co-occupied inside ``window``."""
    count = np.zeros((len(sites), len(sites)), dtype=float)
    for _ in range(n):
        drawn = []
        for s in sites:
            iv = sample_interval(s, rng, tau)
            drawn.append(iv)
        for i, ia in enumerate(drawn):
            for j, ib in enumerate(drawn):
                if ia is None or ib is None:
                    continue
                both = ia.intersection(ib)
                if both is not None and both.intersection(window) is not None:
                    count[i, j] += 1.0
    return count / max(n, 1)


def overrides(pins: Optional[Dict[str, str]]) -> List[Tuple[str, str]]:
    """Pins that are actually set, for the HUD and the run record."""
    if not pins:
        return []
    return sorted((name, mode) for name, mode in pins.items() if mode)

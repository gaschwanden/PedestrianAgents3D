"""Per-simulation research state: chronology, phases, month, provenance badges.

A bare :class:`~pedsim.simulation.Simulation` leaves chronology **off**, so
scenes built before this catalogue keep their old trip draws. A scenario file
turns it on (the schema default). Phase filtering also stays out of the way
until a phase list is attached.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .chronology import Interval, active, co_occupied, is_flagged, overlap_weight
from .phases import Phase, active_ids, member_on


class Research:
    def __init__(self) -> None:
        self.respect_chronology: bool = False
        self.window: Interval = Interval(7000, 10000)
        self.tau: int = 0
        self.undated_policy: str = "exclude"
        self.overlap_weighting: bool = False
        self.pins: Dict[str, str] = {}
        self.phases: List[Phase] = []
        self.phase_mode: str = "manual"          # manual / by_time
        self.manual_phase_ids: Optional[List[str]] = None
        self.phase_overrides: Dict[str, str] = {}
        self.scenario_ref: str = ""
        self.scenario_hash: str = ""
        self.population_rule: str = "per_house"
        self.persons_per_house: float = 5.0
        self.persons_per_m2: float = 0.1
        self.agents_per_person: Optional[float] = None
        self.month: Optional[int] = None
        self.daylight_minutes: float = 720.0
        self.active_share: float = 0.6
        self.task_weights: Dict[str, float] = {}
        self.density_filter: Optional[Tuple[str, str]] = None
        self.terrain_profile: str = "default"
        self.od_mode: str = "uniform"            # uniform / gravity
        self.badges: List[str] = []
        self._calendar = None

    def calendar(self):
        if self._calendar is None:
            from .calendar import load_calendar
            try:
                self._calendar = load_calendar()
            except FileNotFoundError:
                self._calendar = False
        return self._calendar or None

    # ---------------------------------------------------------------- phases
    def current_phase_ids(self) -> Optional[List[str]]:
        """``None`` when no phase list is loaded (every element stays)."""
        if not self.phases:
            return None
        return active_ids(
            self.phases, self.phase_mode,
            self.window if self.phase_mode == "by_time" else None,
            self.manual_phase_ids, self.phase_overrides,
        )

    def phase_allows(self, phase_ids: Sequence[str]) -> bool:
        return member_on(phase_ids, self.current_phase_ids())

    def set_manual_phases(self, ids: Iterable[str]) -> None:
        self.phase_mode = "manual"
        self.manual_phase_ids = list(ids)

    def n_phase_overrides(self) -> int:
        if self.phase_mode != "by_time":
            return 0
        return sum(1 for v in self.phase_overrides.values() if v in ("on", "off"))

    # --------------------------------------------------------------- weights
    def _site(self, name: str):
        if not name:
            return None
        from .sites import find
        try:
            return find(name)
        except KeyError:
            return None

    def site_is_active(self, name: str) -> bool:
        site = self._site(name)
        if site is None:
            # Not a catalogue site: chronology does not remove it.
            return True
        if not self.respect_chronology:
            return True
        return active(site, self.window, self.tau, self.undated_policy, self.pins)

    def site_is_flagged(self, name: str) -> bool:
        site = self._site(name)
        if site is None:
            return False
        return is_flagged(site, self.undated_policy)

    def _event_factor(self, dest_site: str) -> float:
        if not dest_site or self.month is None:
            return 1.0
        cal = self.calendar()
        if cal is None:
            return 1.0
        return cal.event_factor(self.month, dest_site)

    def origin_weight(self, od) -> float:
        if od is None:
            return 0.0
        if not self.phase_allows(getattr(od, "phase_ids", [])):
            return 0.0
        if not self.site_is_active(getattr(od, "site", "") or od.name):
            return 0.0
        return max(0.0, float(od.origin_weight))

    def dest_weight(self, origin_od, dest_od) -> float:
        if dest_od is None:
            return 0.0
        if not self.phase_allows(getattr(dest_od, "phase_ids", [])):
            return 0.0
        o_name = ""
        d_name = ""
        if origin_od is not None:
            o_name = getattr(origin_od, "site", "") or origin_od.name
        d_name = getattr(dest_od, "site", "") or dest_od.name
        if not self.site_is_active(d_name):
            return 0.0
        weight = max(0.0, float(dest_od.dest_weight))
        if self.respect_chronology and o_name and d_name:
            a = self._site(o_name)
            b = self._site(d_name)
            if a is not None and b is not None:
                if not co_occupied(a, b, self.window, self.tau,
                                   self.undated_policy, self.pins):
                    return 0.0
                if self.overlap_weighting:
                    weight *= overlap_weight(a, b, self.window, self.tau,
                                             self.undated_policy, self.pins)
        weight *= self._event_factor(d_name)
        return weight

    def hud_lines(self, population_text: str = "") -> List[str]:
        lines = []
        state = "on" if self.respect_chronology else "off"
        lines.append(
            f"chronology {state}  {self.window.label()}  "
            f"({self.window.years()} yrs, τ={self.tau}, undated: {self.undated_policy})"
        )
        n_pin = len([v for v in self.pins.values() if v])
        if n_pin:
            lines.append(f"{n_pin} override" + ("s" if n_pin != 1 else ""))
        if self.phases:
            ids = self.current_phase_ids() or []
            extra = ""
            n_over = self.n_phase_overrides()
            if n_over:
                extra = f", {n_over} override" + ("s" if n_over != 1 else "")
            lines.append(f"phases ({self.phase_mode}): {', '.join(ids) or 'none'}{extra}")
        if self.month:
            lines.append(f"month {self.month}")
        if population_text:
            lines.append(population_text)
        if self.badges:
            lines.append("⚠ assumption: " + ", ".join(self.badges[:4]))
        if self.scenario_ref:
            lines.append(f"scenario {self.scenario_ref}")
        return lines

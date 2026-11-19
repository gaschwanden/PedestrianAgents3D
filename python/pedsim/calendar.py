"""A twelve-month calendar: river season, daylight and gathering events.

Month numbers are 1–12. Defaults are ``ASSUMPTION`` unless an entry carries a
source. Daylight is computed for 37.2° N with the NOAA solar approximation.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .rivers import Season

LATITUDE_DEG = 37.2

# Representative day-of-year for the middle of each month (non-leap).
MONTH_DOY = {
    1: 15, 2: 46, 3: 75, 4: 106, 5: 136, 6: 167,
    7: 197, 8: 228, 9: 259, 10: 289, 11: 320, 12: 350,
}
MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

_SEASON = {
    "dry": Season.DRY,
    "normal": Season.NORMAL,
    "spring floods": Season.SPRING_FLOOD,
}


def daylight_minutes(latitude_deg: float, doy: int) -> float:
    """Day length in minutes from the NOAA solar approximation.

    ``doy`` is the day of the year, 1–365. The formula is the one NOAA
    publishes for sunrise/sunset (declination Fourier series, then the
    hour angle). It is within a few minutes of the NOAA calculator at
    Şanlıurfa on the solstices; it is not an ephemeris.
    """
    gamma = 2.0 * math.pi / 365.0 * (int(doy) - 1)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.001480 * math.sin(3 * gamma)
    )
    lat = math.radians(latitude_deg)
    # 90.833° is the NOAA zenith: geometric sunset plus refraction and the
    # solar radius. Without it the winter day at this latitude is ~15 min short.
    zenith = math.radians(90.833)
    arg = math.cos(zenith) / (math.cos(lat) * math.cos(decl)) - math.tan(lat) * math.tan(decl)
    arg = min(1.0, max(-1.0, arg))
    hour_angle = math.acos(arg)
    hours = 24.0 * hour_angle / math.pi
    return hours * 60.0


def solstice_minutes(latitude_deg: float = LATITUDE_DEG) -> Dict[str, float]:
    """Day length at the June and December solstices (doy 172 and 355)."""
    return {
        "summer": daylight_minutes(latitude_deg, 172),
        "winter": daylight_minutes(latitude_deg, 355),
    }


@dataclass
class Event:
    name: str
    months: List[int]
    site: str
    attendance_share: float
    duration_days: int = 1
    source: str = ""
    confidence: str = "assumption"

    @property
    def assumption(self) -> bool:
        return (not self.source) or self.confidence == "assumption"


@dataclass
class Month:
    number: int
    name: str
    river_season: Season
    daylight_minutes: float
    task_weights: Dict[str, float] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    source: str = ""
    confidence: str = "assumption"

    @property
    def assumption(self) -> bool:
        return (not self.source) or self.confidence == "assumption"


@dataclass
class Calendar:
    months: Dict[int, Month]
    latitude_deg: float = LATITUDE_DEG
    source: str = ""
    confidence: str = "assumption"

    def month(self, number: int) -> Month:
        if number not in self.months:
            raise KeyError(f"month {number} is not in 1..12")
        return self.months[number]

    def event_factor(self, month_number: int, dest_site: str) -> float:
        """Multiply a destination's weight by ``1 + attendance_share``.

        Several events in the same month add. A site with no event stays at 1.
        """
        factor = 1.0
        month = self.months.get(int(month_number))
        if month is None:
            return factor
        for event in month.events:
            if event.site == dest_site and month_number in event.months:
                factor += float(event.attendance_share)
        return factor

    def badges(self) -> List[str]:
        out = []
        for month in self.months.values():
            if month.assumption:
                out.append(month.name)
            for event in month.events:
                if event.assumption:
                    out.append(event.name)
        return out


def _events_from(entries: List[dict], month_number: int) -> List[Event]:
    out = []
    for entry in entries or []:
        months = [int(m) for m in entry.get("months", [month_number])]
        if month_number not in months:
            continue
        out.append(Event(
            name=str(entry.get("name", "event")),
            months=months,
            site=str(entry.get("site", "")),
            attendance_share=float(entry.get("attendance_share", 0.0)),
            duration_days=int(entry.get("duration_days", 1)),
            source=str(entry.get("source", "")),
            confidence=str(entry.get("confidence", "assumption")),
        ))
    return out


def from_mapping(data: dict) -> Calendar:
    lat = float(data.get("latitude_deg", LATITUDE_DEG))
    months: Dict[int, Month] = {}
    raw_months = data.get("months") or []
    by_num = {int(m["number"]): m for m in raw_months}
    if len(by_num) != 12:
        raise ValueError(f"calendar needs 12 months, found {len(by_num)}")
    for number in range(1, 13):
        entry = by_num[number]
        season_name = str(entry.get("river_season", "normal"))
        if season_name not in _SEASON:
            raise ValueError(f"month {number} has unknown river_season {season_name!r}")
        weights = {str(k): float(v) for k, v in (entry.get("task_weights") or {}).items()}
        months[number] = Month(
            number=number,
            name=str(entry.get("name", MONTH_NAMES[number])),
            river_season=_SEASON[season_name],
            daylight_minutes=daylight_minutes(lat, MONTH_DOY[number]),
            task_weights=weights,
            events=_events_from(data.get("events") or [], number),
            source=str(entry.get("source", "")),
            confidence=str(entry.get("confidence", "assumption")),
        )
    return Calendar(
        months=months, latitude_deg=lat,
        source=str(data.get("source", "")),
        confidence=str(data.get("confidence", "assumption")),
    )


_CACHED: Optional[Calendar] = None
_CACHED_PATH: str = ""


def load_calendar(path: Optional[str] = None) -> Calendar:
    global _CACHED, _CACHED_PATH
    from .scenario import config_path, load_yaml

    path = path or config_path("calendar.yaml")
    if _CACHED is not None and os.path.abspath(path) == _CACHED_PATH:
        return _CACHED
    cal = from_mapping(load_yaml(path))
    _CACHED = cal
    _CACHED_PATH = os.path.abspath(path)
    return cal


def apply_month(sim, month_number: int, calendar: Optional[Calendar] = None) -> Month:
    """Set the river season, daylight and task weights from one month."""
    cal = calendar or load_calendar()
    month = cal.month(int(month_number))
    sim.set_season(month.river_season)
    sim.research.month = month.number
    sim.research.daylight_minutes = month.daylight_minutes
    sim.research.task_weights = dict(month.task_weights)
    sim.research._calendar = cal
    badges = [b for b in cal.badges() if b]
    # Keep population badges and add calendar ones that are assumptions.
    existing = [b for b in sim.research.badges if b not in badges]
    sim.research.badges = existing + badges
    return month

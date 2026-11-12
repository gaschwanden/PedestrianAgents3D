"""GPS tracks: GPX, TCX, FIT and a Strava bulk export, plus GPX written back out.

Parsing uses the standard library for GPX and TCX. FIT needs ``fitdecode``,
which is imported only when a FIT file is actually opened. Tracks without
timestamps are rejected, because a speed cannot be computed from them.
"""
from __future__ import annotations

import csv
import gzip
import io
import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple


WALKING_TYPES = {"walk", "hike", "hiking", "trail walk"}


@dataclass
class Fix:
    lat: float
    lon: float
    time: Optional[datetime] = None
    accuracy_m: Optional[float] = None
    altitude_m: Optional[float] = None


@dataclass
class Track:
    name: str
    fixes: List[Fix]
    activity: str = "walk"
    source_file: str = ""
    walker_id: str = ""
    pclass: str = ""
    load_kg: Optional[float] = None
    route_id: str = ""
    walk_type: str = ""
    footwear: str = ""
    weather: str = ""
    notes: str = ""
    events: List[dict] = field(default_factory=list)

    def has_timestamps(self) -> bool:
        return any(f.time is not None for f in self.fixes)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_time(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_gpx(text: str, name: str = "track") -> Track:
    root = ET.fromstring(text)
    fixes: List[Fix] = []
    label = name
    for el in root.iter():
        if _local(el.tag) == "name" and el.text and label == name:
            label = el.text.strip()
        if _local(el.tag) != "trkpt":
            continue
        lat = float(el.attrib["lat"])
        lon = float(el.attrib["lon"])
        when = None
        alt = None
        acc = None
        for child in el:
            key = _local(child.tag)
            if key == "time":
                when = _parse_time(child.text)
            elif key == "ele" and child.text:
                alt = float(child.text)
            elif key in ("hdop", "accuracy") and child.text:
                acc = float(child.text)
        fixes.append(Fix(lat, lon, when, acc, alt))
    return Track(name=label, fixes=fixes)


def parse_tcx(text: str, name: str = "track") -> Track:
    root = ET.fromstring(text)
    fixes: List[Fix] = []
    for el in root.iter():
        if _local(el.tag) != "Trackpoint":
            continue
        lat = lon = alt = None
        when = None
        for child in el.iter():
            key = _local(child.tag)
            if key == "LatitudeDegrees" and child.text:
                lat = float(child.text)
            elif key == "LongitudeDegrees" and child.text:
                lon = float(child.text)
            elif key == "AltitudeMeters" and child.text:
                alt = float(child.text)
            elif key == "Time" and child.text and when is None:
                when = _parse_time(child.text)
        if lat is None or lon is None:
            continue
        fixes.append(Fix(lat, lon, when, None, alt))
    return Track(name=name, fixes=fixes)


def parse_fit(raw: bytes, name: str = "track") -> Track:
    try:
        import fitdecode
    except ImportError as exc:
        raise ImportError("reading FIT needs fitdecode (`pip install fitdecode`)") from exc
    fixes: List[Fix] = []
    with fitdecode.FitReader(io.BytesIO(raw)) as reader:
        for frame in reader:
            if getattr(frame, "frame_type", None) != fitdecode.FIT_FRAME_DATA:
                continue
            if getattr(frame, "name", "") != "record":
                continue
            values = {f.name: f.value for f in frame.fields}
            lat = values.get("position_lat")
            lon = values.get("position_long")
            if lat is None or lon is None:
                continue
            # FIT semicircles -> degrees
            fixes.append(Fix(
                lat=float(lat) * (180.0 / 2**31),
                lon=float(lon) * (180.0 / 2**31),
                time=values.get("timestamp") if isinstance(values.get("timestamp"), datetime) else None,
                altitude_m=values.get("enhanced_altitude") or values.get("altitude"),
            ))
    return Track(name=name, fixes=fixes)


def read_track_file(path: str) -> Track:
    """Read one GPX, TCX or FIT file. Gzip wrappers are accepted."""
    name = os.path.basename(path)
    opener = gzip.open if name.endswith(".gz") else open
    raw_name = name[:-3] if name.endswith(".gz") else name
    lower = raw_name.lower()
    if lower.endswith(".fit"):
        with opener(path, "rb") as fh:
            return parse_fit(fh.read(), name=raw_name)
    mode = "rt"
    with opener(path, mode, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if lower.endswith(".tcx"):
        return parse_tcx(text, name=raw_name)
    return parse_gpx(text, name=raw_name)


def require_timestamps(track: Track) -> Track:
    if not track.has_timestamps():
        raise ValueError(f"{track.name}: track has no timestamps, so speed cannot be computed")
    return track


def strava_activities(zip_path: str) -> List[dict]:
    """List walking and hiking activities in a Strava bulk export.

    The zip contains ``activities.csv`` and an ``activities/`` folder of
    ``.gpx``, ``.fit`` and ``.tcx`` files, sometimes gzipped.
    """
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next((n for n in zf.namelist() if n.endswith("activities.csv")), None)
        if csv_name is None:
            raise ValueError("bulk export has no activities.csv")
        with zf.open(csv_name) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8")
            for row in csv.DictReader(text):
                kind = (row.get("Activity Type") or row.get("Activity type") or "").strip()
                if kind.casefold() not in WALKING_TYPES:
                    continue
                rows.append({
                    "id": row.get("Activity ID") or row.get("Activity id") or "",
                    "name": row.get("Activity Name") or row.get("Activity name") or "",
                    "type": kind,
                    "date": row.get("Activity Date") or row.get("Activity date") or "",
                    "file": (row.get("Filename") or "").strip(),
                })
    return rows


def load_strava_activity(zip_path: str, file_inside: str) -> Track:
    """Pull one activity file out of a bulk export and parse it."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        match = file_inside
        if match not in names:
            base = os.path.basename(file_inside)
            match = next((n for n in names if os.path.basename(n) == base), None)
        if match is None:
            raise FileNotFoundError(file_inside)
        raw = zf.read(match)
    if match.endswith(".gz"):
        raw = gzip.decompress(raw)
        match = match[:-3]
    name = os.path.basename(match)
    if name.lower().endswith(".fit"):
        track = parse_fit(raw, name=name)
    elif name.lower().endswith(".tcx"):
        track = parse_tcx(raw.decode("utf-8", errors="replace"), name=name)
    else:
        track = parse_gpx(raw.decode("utf-8", errors="replace"), name=name)
    track.source_file = file_inside
    return require_timestamps(track)


def to_gpx(name: str, latlon: Sequence[Tuple[float, float]], run_id: str = "",
           waypoints: Optional[Sequence[Tuple[str, float, float]]] = None) -> str:
    """A GPX 1.1 document. ``latlon`` is a track; ``waypoints`` are named points."""
    def esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    label = esc(name if not run_id else f"{name} [{run_id}]")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="pedsim" xmlns="http://www.topografix.com/GPX/1/1">',
    ]
    for wp_name, lat, lon in waypoints or []:
        parts.append(
            f'<wpt lat="{lat:.7f}" lon="{lon:.7f}"><name>{esc(wp_name)}</name></wpt>'
        )
    if latlon:
        parts.append(f"<trk><name>{label}</name><trkseg>")
        for lat, lon in latlon:
            parts.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"></trkpt>')
        parts.append("</trkseg></trk>")
    parts.append("</gpx>")
    return "\n".join(parts) + "\n"


def write_gpx(path: str, name: str, latlon: Sequence[Tuple[float, float]],
              run_id: str = "", waypoints=None) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_gpx(name, latlon, run_id=run_id, waypoints=waypoints))
    return path

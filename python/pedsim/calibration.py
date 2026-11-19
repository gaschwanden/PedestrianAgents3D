"""Clean a walked track and fit Tobler's speed-slope curve to it.

Elevation used for the slope comes from the DEM, not from the GPS altitude.
Segments inside one track are not independent, so the bootstrap resamples
whole tracks. A private location (a hotel, a house) has the first and last
200 m of a track that starts or ends there removed.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .timing import TOBLER_FLAT_KMH
from .tracks import Fix, Track


@dataclass
class Segment:
    slope: float          # rise/run, signed in the direction of travel
    speed_kmh: float
    length_m: float
    track_id: str


@dataclass
class CleanReport:
    fixes_in: int
    fixes_kept: int
    fixes_dropped_accuracy: int
    stop_seconds_removed: float
    segments: int
    trimmed_private_m: float


def _xy(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    """Local metres without a projection library. Fine over a few kilometres."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    return ((lon - lon0) * m_per_deg_lon, (lat - lat0) * m_per_deg_lat)


def trim_private(fixes: Sequence[Fix], private_latlon: Sequence[Tuple[float, float]],
                 radius_m: float = 200.0) -> Tuple[List[Fix], float]:
    """Drop the start and the end while they lie within ``radius_m`` of a private point.

    Distance is measured along the track, so a track that merely passes the
    hotel later in the walk is left alone. Returns the kept fixes and the
    metres removed.
    """
    if not fixes or not private_latlon:
        return list(fixes), 0.0
    lat0 = fixes[0].lat
    lon0 = fixes[0].lon
    pts = [_xy(f.lat, f.lon, lat0, lon0) for f in fixes]
    priv = [_xy(lat, lon, lat0, lon0) for lat, lon in private_latlon]

    def near(index: int) -> bool:
        x, y = pts[index]
        return any(math.hypot(x - px, y - py) <= radius_m for px, py in priv)

    def along(a: int, b: int) -> float:
        return math.hypot(pts[b][0] - pts[a][0], pts[b][1] - pts[a][1])

    start = 0
    walked = 0.0
    if near(0):
        for i in range(1, len(fixes)):
            walked += along(i - 1, i)
            start = i
            if walked >= radius_m and not near(i):
                break
    end = len(fixes) - 1
    walked_end = 0.0
    if near(end):
        for i in range(len(fixes) - 2, start - 1, -1):
            walked_end += along(i, i + 1)
            end = i
            if walked_end >= radius_m and not near(i):
                break
    if end <= start:
        return [], walked + walked_end
    return list(fixes[start:end + 1]), walked + walked_end


def clean_track(track: Track, elevation_at: Optional[Callable[[float, float], float]] = None,
                private_latlon: Optional[Sequence[Tuple[float, float]]] = None,
                accuracy_max_m: float = 15.0, stop_kmh: float = 0.5,
                stop_seconds: float = 30.0, segment_min_m: float = 20.0,
                segment_max_m: float = 50.0) -> Tuple[List[Segment], CleanReport]:
    """Reproject, drop bad fixes and stops, take height from the DEM, segment.

    ``elevation_at(lat, lon)`` supplies the height. GPS altitude is kept on the
    fix for reference and is not used for the slope.
    """
    if not track.has_timestamps():
        raise ValueError(f"{track.name}: no timestamps")
    incoming = len(track.fixes)
    kept = []
    dropped_acc = 0
    for fix in track.fixes:
        if fix.accuracy_m is not None and fix.accuracy_m > accuracy_max_m:
            dropped_acc += 1
            continue
        if fix.time is None:
            continue
        kept.append(fix)
    trimmed_m = 0.0
    if private_latlon:
        kept, trimmed_m = trim_private(kept, private_latlon)
    # Remove stops: runs slower than stop_kmh lasting longer than stop_seconds.
    if len(kept) >= 2:
        lat0, lon0 = kept[0].lat, kept[0].lon
        moving = [kept[0]]
        stop_s = 0.0
        removed_s = 0.0
        for prev, cur in zip(kept, kept[1:]):
            dt = (cur.time - prev.time).total_seconds()
            if dt <= 0:
                continue
            x0, y0 = _xy(prev.lat, prev.lon, lat0, lon0)
            x1, y1 = _xy(cur.lat, cur.lon, lat0, lon0)
            dist = math.hypot(x1 - x0, y1 - y0)
            kmh = (dist / 1000.0) / (dt / 3600.0)
            if kmh < stop_kmh:
                stop_s += dt
                if stop_s > stop_seconds:
                    removed_s += dt
                    continue
            else:
                stop_s = 0.0
            moving.append(cur)
        kept = moving
    else:
        removed_s = 0.0
    segments: List[Segment] = []
    if len(kept) < 2:
        report = CleanReport(incoming, len(kept), dropped_acc, removed_s, 0, trimmed_m)
        return segments, report
    lat0, lon0 = kept[0].lat, kept[0].lon
    acc_m = 0.0
    acc_t = 0.0
    z0 = elevation_at(kept[0].lat, kept[0].lon) if elevation_at else (kept[0].altitude_m or 0.0)
    anchor = kept[0]
    anchor_z = z0
    for prev, cur in zip(kept, kept[1:]):
        dt = (cur.time - prev.time).total_seconds()
        if dt <= 0:
            continue
        x0, y0 = _xy(prev.lat, prev.lon, lat0, lon0)
        x1, y1 = _xy(cur.lat, cur.lon, lat0, lon0)
        dist = math.hypot(x1 - x0, y1 - y0)
        acc_m += dist
        acc_t += dt
        if acc_m < segment_min_m:
            continue
        if acc_m > segment_max_m and acc_m - dist >= segment_min_m:
            # the step that crossed the max is left for the next segment
            acc_m -= dist
            acc_t -= dt
        z1 = elevation_at(cur.lat, cur.lon) if elevation_at else (cur.altitude_m or anchor_z)
        length = acc_m
        if length <= 0 or acc_t <= 0:
            anchor, anchor_z = cur, z1
            acc_m = acc_t = 0.0
            continue
        slope = (z1 - anchor_z) / length
        speed = (length / 1000.0) / (acc_t / 3600.0)
        segments.append(Segment(slope, speed, length, track.name))
        anchor, anchor_z = cur, z1
        acc_m = 0.0
        acc_t = 0.0
    report = CleanReport(incoming, len(kept), dropped_acc, removed_s, len(segments), trimmed_m)
    return segments, report


def tobler(slope: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    return a * np.exp(-b * np.abs(np.asarray(slope, dtype=float) + c))


def fit_tobler(segments: Sequence[Segment], n_boot: int = 1000,
               rng: Optional[np.random.Generator] = None) -> dict:
    """Non-linear least squares for ``v = a exp(-b |s + c|)``.

    The bootstrap resamples **tracks**, not segments. ``a, b, c`` come back
    with a 95 % interval. SciPy's ``curve_fit`` is used when it imports;
    otherwise a small Gauss-Newton loop does the same job.
    """
    if not segments:
        raise ValueError("no segments to fit")
    rng = rng or np.random.default_rng(0)
    slopes = np.array([s.slope for s in segments], dtype=float)
    speeds = np.array([s.speed_kmh for s in segments], dtype=float)
    tracks = np.array([s.track_id for s in segments])
    a, b, c = _fit_once(slopes, speeds)
    unique = list(dict.fromkeys(tracks.tolist()))
    boots = []
    by_track = {tid: np.where(tracks == tid)[0] for tid in unique}
    for _ in range(n_boot):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        idx = np.concatenate([by_track[tid] for tid in chosen])
        try:
            boots.append(_fit_once(slopes[idx], speeds[idx]))
        except ValueError:
            continue
    boot = np.array(boots) if boots else np.array([[a, b, c]])
    lo = np.percentile(boot, 2.5, axis=0)
    hi = np.percentile(boot, 97.5, axis=0)
    return {
        "a_kmh": float(a), "b": float(b), "c": float(c),
        "a_ci": (float(lo[0]), float(hi[0])),
        "b_ci": (float(lo[1]), float(hi[1])),
        "c_ci": (float(lo[2]), float(hi[2])),
        "n_segments": len(segments),
        "n_tracks": len(unique),
        "n_boot": int(len(boots)),
    }


def _fit_once(slopes: np.ndarray, speeds: np.ndarray) -> Tuple[float, float, float]:
    try:
        from scipy.optimize import curve_fit

        def model(s, a, b, c):
            return tobler(s, a, b, c)

        p0 = (float(np.median(speeds)) or 5.0, 3.5, 0.05)
        bounds = ([0.2, 0.01, -0.3], [15.0, 20.0, 0.3])
        coef, _cov = curve_fit(model, slopes, speeds, p0=p0, bounds=bounds, maxfev=4000)
        return float(coef[0]), float(coef[1]), float(coef[2])
    except Exception:
        return _gauss_newton(slopes, speeds)


def _gauss_newton(slopes: np.ndarray, speeds: np.ndarray) -> Tuple[float, float, float]:
    """A short least-squares fallback so the fit still runs without SciPy."""
    a, b, c = float(np.median(speeds) or 5.0), 3.5, 0.05
    for _ in range(40):
        pred = tobler(slopes, a, b, c)
        resid = speeds - pred
        # numerical Jacobian
        eps = 1e-4
        cols = []
        for params, index in (((a + eps, b, c), 0), ((a, b + eps, c), 1), ((a, b, c + eps), 2)):
            cols.append((tobler(slopes, *params) - pred) / eps)
        jac = np.stack(cols, axis=1)
        step, *_ = np.linalg.lstsq(jac, resid, rcond=None)
        a = float(np.clip(a + step[0], 0.2, 15))
        b = float(np.clip(b + step[1], 0.01, 20))
        c = float(np.clip(c + step[2], -0.3, 0.3))
    return a, b, c


def terrain_from_fit(name: str, fit: dict):
    """A :class:`TerrainCost` whose flat speed matches the fitted ``a``.

    ``base_speed`` stays a multiplier on Tobler's flat pace, which is what the
    Dijkstra already expects. Previous profiles are the caller's to keep.
    """
    from .topography import TerrainCost

    base = float(fit["a_kmh"]) / TOBLER_FLAT_KMH
    return TerrainCost(
        base_speed=base,
        slope_factor=float(fit["b"]),
        slope_offset=float(fit["c"]),
    ), name


def apply_profile(sim, name: str, fit: dict) -> None:
    cost, name = terrain_from_fit(name, fit)
    sim.grid.terrain_cost = cost
    sim.research.terrain_profile = name
    sim.recompute_cost_fields()


def slope_profile(points_xy: Sequence[Tuple[float, float]],
                  elevation_at_xy: Callable[[float, float], float],
                  step_m: float = 10.0) -> dict:
    """Slope along a drawn line, plus a histogram from -30 % to +30 % in 5 % bins."""
    if len(points_xy) < 2:
        return {"distance_m": [], "slope": [], "histogram": []}
    samples = [points_xy[0]]
    for (x0, y0), (x1, y1) in zip(points_xy, points_xy[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(length / step_m))
        for k in range(1, n + 1):
            t = k / n
            samples.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    dist = [0.0]
    slopes = []
    heights = [elevation_at_xy(*samples[0])]
    for a, b in zip(samples, samples[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        z = elevation_at_xy(*b)
        heights.append(z)
        dist.append(dist[-1] + d)
        slopes.append((z - heights[-2]) / d if d else 0.0)
    edges = np.linspace(-0.30, 0.30, 13)
    counts = np.zeros(12, dtype=float)
    lengths = np.zeros(12, dtype=float)
    for s, a, b in zip(slopes, dist, dist[1:]):
        idx = int(np.clip(np.digitize([s], edges)[0] - 1, 0, 11))
        counts[idx] += 1
        lengths[idx] += b - a
    return {
        "distance_m": dist,
        "slope": slopes,
        "bin_edges": edges.tolist(),
        "bin_length_m": lengths.tolist(),
    }


def coverage_gaps(profiles: Sequence[dict], minimum_m: float = 500.0) -> List[dict]:
    """Bins with less than ``minimum_m`` of planned walking, across a route set."""
    if not profiles:
        return []
    total = np.zeros(12, dtype=float)
    edges = profiles[0]["bin_edges"]
    for prof in profiles:
        total += np.asarray(prof["bin_length_m"], dtype=float)
    gaps = []
    for i, length in enumerate(total):
        if length < minimum_m:
            gaps.append({
                "slope_from": edges[i], "slope_to": edges[i + 1],
                "length_m": float(length),
            })
    return gaps


def buffer_overlap(walked: Sequence[Tuple[float, float]],
                   corridor: Sequence[Tuple[float, float]],
                   buffer_m: float = 25.0) -> float:
    """Share of the walked vertices that fall within ``buffer_m`` of the corridor."""
    if not walked or not corridor:
        return 0.0
    hit = 0
    for x, y in walked:
        if any(math.hypot(x - cx, y - cy) <= buffer_m for cx, cy in corridor):
            hit += 1
    return hit / len(walked)


def mean_perpendicular(walked: Sequence[Tuple[float, float]],
                       route: Sequence[Tuple[float, float]]) -> float:
    """Mean distance from walked vertices to the nearest route vertex, in metres."""
    if not walked or not route:
        return math.inf
    total = 0.0
    for x, y in walked:
        total += min(math.hypot(x - rx, y - ry) for rx, ry in route)
    return total / len(walked)


def load_routes(directory: str) -> List[dict]:
    """Load a route library. A route without ``access_notes`` is rejected."""
    import json

    routes = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".geojson"):
            continue
        with open(os.path.join(directory, name), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            if not str(props.get("access_notes", "")).strip():
                raise ValueError(f"{name}: route {props.get('id', '?')} has no access_notes")
            routes.append(feature)
    return routes


def save_fit_plot(path: str, segments: Sequence[Segment], fit: dict) -> str:
    """PNG of the segments, the fitted curve and the default Tobler curve."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    slopes = np.array([s.slope for s in segments])
    speeds = np.array([s.speed_kmh for s in segments])
    grid = np.linspace(float(slopes.min()) - 0.02, float(slopes.max()) + 0.02, 80)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(slopes, speeds, s=12, c="#335588", label="segments")
    ax.plot(grid, tobler(grid, fit["a_kmh"], fit["b"], fit["c"]), color="#c0504d",
            label="fitted")
    ax.plot(grid, tobler(grid, 6.0, 3.5, 0.05), color="#888888", ls="--",
            label="Tobler 6 km/h")
    ax.set_xlabel("slope (rise/run)")
    ax.set_ylabel("speed (km/h)")
    ax.legend(frameon=False)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path

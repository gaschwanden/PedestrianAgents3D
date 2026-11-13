"""Georeferenced input: real DEMs and hydrography into the simulation's frame.

The simulation works in a flat local metric frame -- metres east and north of an
origin -- because that is what a pedestrian cost model needs. Real data arrives
in geographic or projected coordinates. This module is the bridge.

:class:`LocalFrame` pins an origin (usually a site, or the centre of a cluster)
and converts to and from metres via the appropriate UTM zone, so distances in
the simulation are true metres on the ground rather than degrees.

:func:`load_dem` resamples one or more GeoTIFF tiles onto a local grid by
inverse mapping: every destination cell centre is converted to lon/lat and
sampled from the source. That is slower than a warp but it is easy to verify and
it puts the output exactly on the grid the simulation wants.

Requires ``rasterio`` and ``pyproj`` (in ``requirements.txt``); both are
imported lazily so the rest of the package works without them.
"""
from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .rivers import River
from .topography import Topography

LatLon = Tuple[float, float]
BBox = Tuple[float, float, float, float]   # (min_lat, min_lon, max_lat, max_lon)


def utm_epsg(lat: float, lon: float) -> str:
    """EPSG code of the UTM zone containing ``(lat, lon)``.

    Şanlıurfa falls in zone 37N -> ``EPSG:32637``.
    """
    zone = int((lon + 180.0) / 6.0) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


@dataclass
class LocalFrame:
    """A local metric frame: metres east/north of ``(origin_lat, origin_lon)``.

    The projection is the UTM zone of the origin, with the origin's own
    projected coordinates subtracted, so the simulation works near zero instead
    of at 500000, 4100000 -- which keeps float precision and readable numbers.
    """

    origin_lat: float
    origin_lon: float
    epsg: str = ""
    _x0: float = 0.0
    _y0: float = 0.0

    def __post_init__(self) -> None:
        from pyproj import Transformer

        if not self.epsg:
            self.epsg = utm_epsg(self.origin_lat, self.origin_lon)
        self._fwd = Transformer.from_crs("EPSG:4326", self.epsg, always_xy=True)
        self._inv = Transformer.from_crs(self.epsg, "EPSG:4326", always_xy=True)
        self._x0, self._y0 = self._fwd.transform(self.origin_lon, self.origin_lat)

    # -- conversions --------------------------------------------------------
    def to_local(self, lat, lon):
        """Lat/lon -> local metres ``(x east, y north)``. Accepts arrays."""
        x, y = self._fwd.transform(lon, lat)
        return np.asarray(x) - self._x0, np.asarray(y) - self._y0

    def to_latlon(self, x, y):
        """Local metres -> ``(lat, lon)``. Accepts arrays."""
        lon, lat = self._inv.transform(np.asarray(x) + self._x0,
                                       np.asarray(y) + self._y0)
        return np.asarray(lat), np.asarray(lon)

    def to_projected(self, x, y):
        """Local metres -> the underlying UTM easting/northing.

        Needed by :mod:`pedsim.paleo`, whose core coordinates are in UTM 37N.
        """
        return np.asarray(x) + self._x0, np.asarray(y) + self._y0

    def bounds_for(self, bbox: BBox) -> Tuple[float, float, float, float]:
        """Local ``(min_x, min_y, max_x, max_y)`` covering a lat/lon box."""
        min_lat, min_lon, max_lat, max_lon = bbox
        lats = [min_lat, min_lat, max_lat, max_lat]
        lons = [min_lon, max_lon, min_lon, max_lon]
        xs, ys = self.to_local(np.array(lats), np.array(lons))
        return (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))

    @classmethod
    def centred_on(cls, bbox: BBox) -> "LocalFrame":
        min_lat, min_lon, max_lat, max_lon = bbox
        return cls((min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0)


def dem_tiles(pattern: str) -> List[str]:
    """Expand a glob of DEM files, sorted. Raises if nothing matches."""
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no DEM tiles match {pattern!r}")
    return paths


def load_dem(paths: Sequence[str], frame: LocalFrame,
             bounds: Tuple[float, float, float, float],
             cellsize: float = 30.0,
             nodata_fill: Optional[float] = None,
             interpolate: Optional[bool] = None) -> Topography:
    """Resample GeoTIFF tiles onto a local metric grid.

    Parameters
    ----------
    paths:
        One or more DEM files in the same CRS (Copernicus GLO-30 tiles are
        EPSG:4326). They may overlap or tile arbitrarily; later tiles only fill
        cells earlier ones left empty.
    frame:
        The destination frame.
    bounds:
        Destination extent in local metres, ``(min_x, min_y, max_x, max_y)``.
    cellsize:
        Destination cell size in metres. Do not go below the source resolution
        (~30 m for GLO-30) expecting more detail -- you will only interpolate.
    interpolate:
        Blend the four surrounding DEM posts instead of taking the nearest one.
        ``None`` (default) turns it on when ``cellsize`` is finer than half the
        source spacing. Without it a 3 m grid over a 30 m DEM is a staircase:
        flat treads ten cells wide separated by one-cell risers of several
        metres, which the slope model reads as cliffs every 30 m.
    nodata_fill:
        Value for cells no tile covers. ``None`` fills them with the mean of
        what was sampled, which keeps the cost model finite; the caller should
        prefer to clip ``bounds`` to the data instead.

    Notes
    -----
    GLO-30 is a **surface** model (DSM) with ~2.2 m RMSE in Türkiye, and it
    shows today's ground -- including the Atatürk reservoir, and several metres
    of Holocene valley fill. See :mod:`pedsim.paleo` to strip the fill, and note
    that no correction recovers terrain under the reservoir.
    """
    import rasterio

    min_x, min_y, max_x, max_y = bounds
    nx = max(1, int(round((max_x - min_x) / cellsize)))
    ny = max(1, int(round((max_y - min_y) / cellsize)))
    xs = min_x + (np.arange(nx) + 0.5) * cellsize
    ys = min_y + (np.arange(ny) + 0.5) * cellsize
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    lat, lon = frame.to_latlon(X, Y)

    out = np.full((nx, ny), np.nan, dtype=float)
    for path in paths:
        need = np.isnan(out)
        if not need.any():
            break
        with rasterio.open(path) as src:
            left, bottom, right, top = src.bounds
            inside = need & (lon >= left) & (lon <= right) & (lat >= bottom) & (lat <= top)
            if not inside.any():
                continue
            rows, cols = rasterio.transform.rowcol(
                src.transform, lon[inside], lat[inside])
            rows = np.clip(np.asarray(rows), 0, src.height - 1)
            cols = np.clip(np.asarray(cols), 0, src.width - 1)
            band = src.read(1)
            vals = band[rows, cols].astype(float)
            if src.nodata is not None:
                vals[vals == src.nodata] = np.nan
            smooth = interpolate
            if smooth is None:
                post_m = abs(src.transform.e) * 111320.0     # source spacing, metres
                smooth = cellsize < 0.5 * post_m
            if smooth:
                vals = _bilinear(src, band, lon[inside], lat[inside], vals)
            out[inside] = vals

    if np.isnan(out).any():
        fill = nodata_fill
        if fill is None:
            fill = float(np.nanmean(out)) if np.isfinite(out).any() else 0.0
        out = np.where(np.isnan(out), fill, out)
    return Topography(out, x0=float(xs[0]), y0=float(ys[0]), cellsize=cellsize)


def _bilinear(src, band: np.ndarray, lon: np.ndarray, lat: np.ndarray,
              nearest: np.ndarray) -> np.ndarray:
    """Bilinear DEM value at each point; ``nearest`` where a neighbour is nodata.

    Posts sit at pixel centres. Points in the outer half pixel of a tile are
    clamped to its last two rows or columns rather than reaching into the next
    tile, which is exact enough at a 30 m spacing.
    """
    inv = ~src.transform
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    colf = inv.a * lon + inv.b * lat + inv.c
    rowf = inv.d * lon + inv.e * lat + inv.f
    r = np.clip(np.asarray(rowf) - 0.5, 0.0, src.height - 1.0)
    c = np.clip(np.asarray(colf) - 0.5, 0.0, src.width - 1.0)
    r0 = np.minimum(r.astype(int), src.height - 2)
    c0 = np.minimum(c.astype(int), src.width - 2)
    fr = r - r0
    fc = c - c0
    z00 = band[r0, c0].astype(float)
    z01 = band[r0, c0 + 1].astype(float)
    z10 = band[r0 + 1, c0].astype(float)
    z11 = band[r0 + 1, c0 + 1].astype(float)
    top = z00 + (z01 - z00) * fc
    bottom = z10 + (z11 - z10) * fc
    out = top + (bottom - top) * fr
    if src.nodata is not None:
        bad = ((z00 == src.nodata) | (z01 == src.nodata)
               | (z10 == src.nodata) | (z11 == src.nodata))
        out = np.where(bad, nearest, out)
    return out


def _clip_run(path: List[Tuple[float, float]],
              clip: Optional[Tuple[float, float, float, float]]
              ) -> List[Tuple[float, float]]:
    """Longest run of consecutive vertices inside ``clip``, plus one vertex
    beyond each end so the line still reaches the scene edge.

    A reach selected by its bounding box can wander far outside the scene; left
    unclipped it would be drawn across empty space and rasterised into cells
    that do not exist.
    """
    if clip is None:
        return path
    min_x, min_y, max_x, max_y = clip
    inside = [min_x <= x <= max_x and min_y <= y <= max_y for x, y in path]
    best: Tuple[int, int] = (0, 0)
    i = 0
    while i < len(inside):
        if not inside[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(inside) and inside[j + 1]:
            j += 1
        if (j - i) >= (best[1] - best[0]):
            best = (i, j)
        i = j + 1
    lo, hi = best
    if lo == hi and not inside[lo]:
        return []
    return path[max(0, lo - 1):min(len(path), hi + 2)]


def load_rivers(path: str, frame: LocalFrame, bbox: BBox,
                perennial_discharge_cms: float = 0.5,
                max_rivers: int = 40,
                min_length_m: float = 2000.0,
                clip: Optional[Tuple[float, float, float, float]] = None,
                **river_kw) -> List[River]:
    """Read watercourses from a shapefile into :class:`~pedsim.rivers.River`.

    Written for HydroRIVERS v1.0, which carries a long-term average discharge
    (``DIS_AV_CMS``); anything above ``perennial_discharge_cms`` is treated as
    perennial and the rest as seasonal -- the usual case in this landscape, and
    the distinction that drives the season model.

    Only reaches intersecting ``bbox`` are kept, the longest first, capped at
    ``max_rivers`` so a cluster scene stays interactive. ``clip`` (local metres,
    ``(min_x, min_y, max_x, max_y)``) trims each reach to the scene extent.
    """
    import shapefile   # pyshp

    min_lat, min_lon, max_lat, max_lon = bbox
    reader = shapefile.Reader(path)
    fields = [f[0] for f in reader.fields[1:]]
    dis_idx = fields.index("DIS_AV_CMS") if "DIS_AV_CMS" in fields else None
    name_idx = fields.index("HYRIV_ID") if "HYRIV_ID" in fields else None

    candidates: List[Tuple[float, River]] = []
    for shp, rec in zip(reader.iterShapes(), reader.iterRecords()):
        bb = shp.bbox   # (min_lon, min_lat, max_lon, max_lat)
        if bb[2] < min_lon or bb[0] > max_lon or bb[3] < min_lat or bb[1] > max_lat:
            continue
        pts = np.asarray(shp.points, dtype=float)
        if len(pts) < 2:
            continue
        x, y = frame.to_local(pts[:, 1], pts[:, 0])
        path_xy = _clip_run([(float(a), float(b)) for a, b in zip(x, y)], clip)
        if len(path_xy) < 2:
            continue
        dis = float(rec[dis_idx]) if dis_idx is not None else 0.0
        name = f"reach {rec[name_idx]}" if name_idx is not None else "reach"
        r = River(name=name, path=path_xy,
                  perennial=dis >= perennial_discharge_cms,
                  **river_kw)
        length = r.length()
        if length >= min_length_m:
            candidates.append((length, r))
    reader.close()

    candidates.sort(key=lambda t: -t[0])
    return [r for _, r in candidates[:max_rivers]]


def site_ods(frame: LocalFrame, sites_list: Iterable, group_by_period: bool = True):
    """Turn catalogue entries into origin/destination places in local metres.

    Only sites with a usable coordinate are included -- an unlocated or
    conflicting one cannot be routed to honestly. Each site is both a source and
    a sink, since cluster-scale movement is between settlements in both
    directions.

    When ``group_by_period`` is set, the group id comes from
    :func:`pedsim.chronology.period_group` (500-year bins of the occupation
    midpoint) rather than a hard-coded PPNA/PPNB cut.
    """
    from .chronology import period_group
    from .od import OD

    out = []
    for s in sites_list:
        if not getattr(s, "usable", False):
            continue
        x, y = frame.to_local(s.lat, s.lon)
        group = period_group(s) if group_by_period else 0
        out.append(OD(float(x), float(y), group=group,
                      origin_weight=1.0, dest_weight=1.0, name=s.name,
                      site=s.name, kind="site"))
    return out

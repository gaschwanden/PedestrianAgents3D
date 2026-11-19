"""Importers for archaeological site layouts and terrain.

Two entry points, matching the two things a user typically has for an ancient
site such as Göbekli Tepe:

* :func:`load_site` -- a *simple* outline importer. You give it building /
  enclosure / wall outlines and tag each one with a role. Structures tagged as
  ``source`` or ``sink`` become the origins and destinations of pedestrian
  trips; structures tagged ``building`` / ``wall`` / ``obstacle`` block
  movement. It reads either a small custom JSON schema or a GeoJSON
  ``FeatureCollection``.

* :func:`load_topography` -- reads a terrain elevation model from an ESRI ASCII
  grid (``.asc``), a NumPy array (``.npy``), a regular XYZ/CSV point grid, or a
  grayscale heightmap image, and returns a :class:`~pedsim.topography.Topography`.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .geometry import Polygon, polygon_bounds, polygon_centroid
from .od import OD
from .topography import Topography

# Roles that block pedestrian movement.
BLOCKING_ROLES = {"building", "wall", "obstacle", "structure"}
# Roles that generate/absorb pedestrians.
SOURCE_ROLES = {"source", "entrance", "gate"}
SINK_ROLES = {"sink", "destination"}
BOTH_ROLES = {"source_sink", "place", "od", "plaza"}


@dataclass
class SiteFeature:
    name: str
    polygon: Polygon
    role: str
    group: int = 0
    origin_weight: float = 1.0
    dest_weight: float = 1.0
    od_point: Optional[Tuple[float, float]] = None

    @property
    def is_blocking(self) -> bool:
        return self.role in BLOCKING_ROLES

    @property
    def is_source(self) -> bool:
        return self.role in SOURCE_ROLES or self.role in BOTH_ROLES

    @property
    def is_sink(self) -> bool:
        return self.role in SINK_ROLES or self.role in BOTH_ROLES

    @property
    def is_od(self) -> bool:
        return self.is_source or self.is_sink

    def od_position(self) -> Tuple[float, float]:
        if self.od_point is not None:
            return self.od_point
        return polygon_centroid(self.polygon)


@dataclass
class ArchaeologicalSite:
    features: List[SiteFeature] = field(default_factory=list)
    boundary: Optional[Polygon] = None
    boundary_pad: float = 20.0
    # If True, source/sink structures also block movement (agents must enter via
    # a doorway). By default they are walkable so their centroid OD is reachable.
    block_source_sink: bool = False

    # ---------------------------------------------------------------- geometry
    def bounds(self) -> Tuple[float, float, float, float]:
        if self.boundary:
            return polygon_bounds(self.boundary)
        xs: List[float] = []
        ys: List[float] = []
        for f in self.features:
            for x, y in f.polygon:
                xs.append(x)
                ys.append(y)
        if not xs:
            raise ValueError("site has no geometry to derive bounds from")
        pad = self.boundary_pad
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def building_polygons(self) -> List[Polygon]:
        polys = [f.polygon for f in self.features if f.is_blocking]
        if self.block_source_sink:
            polys += [f.polygon for f in self.features if f.is_od]
        return polys

    def obstacle_polygons(self) -> List[Polygon]:
        return []

    def source_sink_features(self) -> List[SiteFeature]:
        return [f for f in self.features if f.is_od]

    def build_ods(self) -> List[OD]:
        ods: List[OD] = []
        for f in self.features:
            if not f.is_od:
                continue
            x, y = f.od_position()
            ods.append(
                OD(
                    x=x,
                    y=y,
                    group=f.group,
                    origin_weight=f.origin_weight if f.is_source else 0.0,
                    dest_weight=f.dest_weight if f.is_sink else 0.0,
                    name=f.name,
                )
            )
        return ods


# ------------------------------------------------------------------- site I/O
def _feature_from_custom(obj: dict) -> Optional[SiteFeature]:
    poly = obj.get("polygon") or obj.get("outline")
    if not poly:
        return None
    poly = [(float(p[0]), float(p[1])) for p in poly]
    role = str(obj.get("role", "building")).lower()
    od_point = obj.get("od") or obj.get("od_point")
    if od_point is not None:
        od_point = (float(od_point[0]), float(od_point[1]))
    return SiteFeature(
        name=str(obj.get("name", "")),
        polygon=poly,
        role=role,
        group=int(obj.get("group", 0)),
        origin_weight=float(obj.get("origin_weight", 1.0)),
        dest_weight=float(obj.get("dest_weight", 1.0)),
        od_point=od_point,
    )


def _feature_from_geojson(feat: dict) -> Optional[SiteFeature]:
    geom = feat.get("geometry") or {}
    props = feat.get("properties") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = coords[0][0]
    else:
        return None
    poly = [(float(p[0]), float(p[1])) for p in ring]
    role = str(props.get("role", props.get("type", "building"))).lower()
    od_point = props.get("od") or props.get("od_point")
    if od_point is not None:
        od_point = (float(od_point[0]), float(od_point[1]))
    return SiteFeature(
        name=str(props.get("name", "")),
        polygon=poly,
        role=role,
        group=int(props.get("group", 0)),
        origin_weight=float(props.get("origin_weight", 1.0)),
        dest_weight=float(props.get("dest_weight", 1.0)),
        od_point=od_point,
    )


def load_site(path: str, **kwargs) -> ArchaeologicalSite:
    """Load an :class:`ArchaeologicalSite` from a JSON or GeoJSON file.

    Custom schema::

        {
          "boundary": [[x, y], ...],          # optional site extent
          "features": [
            {"name": "Enclosure D", "role": "sink",   "polygon": [[x,y], ...],
             "group": 0, "origin_weight": 0.3, "dest_weight": 1.0},
            {"name": "North gate",  "role": "source", "polygon": [[x,y], ...]},
            {"name": "Perimeter wall", "role": "wall", "polygon": [[x,y], ...]}
          ]
        }

    GeoJSON: a ``FeatureCollection`` whose feature ``properties`` carry ``role``
    (and optionally ``group``/``origin_weight``/``dest_weight``).
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    features: List[SiteFeature] = []
    boundary: Optional[Polygon] = None

    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            props = feat.get("properties") or {}
            if str(props.get("role", "")).lower() == "boundary":
                geom = feat.get("geometry") or {}
                if geom.get("type") == "Polygon":
                    boundary = [(float(p[0]), float(p[1])) for p in geom["coordinates"][0]]
                continue
            sf = _feature_from_geojson(feat)
            if sf is not None:
                features.append(sf)
    else:
        raw_boundary = data.get("boundary")
        if raw_boundary:
            boundary = [(float(p[0]), float(p[1])) for p in raw_boundary]
        for obj in data.get("features", []):
            sf = _feature_from_custom(obj)
            if sf is not None:
                features.append(sf)

    return ArchaeologicalSite(features=features, boundary=boundary, **kwargs)


# ------------------------------------------------------------- topography I/O
def _load_ascii_grid(path: str) -> Topography:
    header = {}
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    data_start = 0
    keys = {"ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter",
            "cellsize", "nodata_value"}
    for idx, line in enumerate(lines):
        parts = line.split()
        if parts and parts[0].lower() in keys:
            header[parts[0].lower()] = float(parts[1])
            data_start = idx + 1
        else:
            break
    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    cellsize = float(header["cellsize"])
    if "xllcorner" in header:
        x0 = header["xllcorner"]
        y0 = header["yllcorner"]
    else:
        x0 = header["xllcenter"]
        y0 = header["yllcenter"]
    nodata = header.get("nodata_value", -9999.0)

    rows = []
    for line in lines[data_start:]:
        vals = line.split()
        if vals:
            rows.append([float(v) for v in vals])
    arr = np.array(rows, dtype=float)  # [row, col], row 0 = north (top)
    arr[arr == nodata] = np.nan
    # ASCII grids list north-to-south; flip so row index increases with +y.
    arr = np.flipud(arr)
    # Convert [row=y, col=x] -> [ix, iy].
    elev = arr.T
    return Topography(elev, x0, y0, cellsize)


def _load_npy(path: str, bounds: Tuple[float, float, float, float]) -> Topography:
    arr = np.load(path)
    min_x, min_y, max_x, max_y = bounds
    nx, ny = arr.shape
    cellsize = (max_x - min_x) / (nx - 1) if nx > 1 else 1.0
    return Topography(arr.astype(float), min_x, min_y, cellsize)


def _load_xyz(path: str) -> Topography:
    pts = np.loadtxt(path, delimiter=None)
    if pts.shape[1] < 3:
        raise ValueError("XYZ file needs at least 3 columns")
    xs = np.unique(pts[:, 0])
    ys = np.unique(pts[:, 1])
    elev = np.full((xs.shape[0], ys.shape[0]), np.nan)
    xi = {v: i for i, v in enumerate(xs)}
    yi = {v: i for i, v in enumerate(ys)}
    for x, y, z in pts[:, :3]:
        elev[xi[x], yi[y]] = z
    cellsize = float(xs[1] - xs[0]) if xs.shape[0] > 1 else 1.0
    return Topography(elev, float(xs[0]), float(ys[0]), cellsize)


def _load_image(
    path: str,
    bounds: Tuple[float, float, float, float],
    z_min: float,
    z_max: float,
) -> Topography:
    from PIL import Image

    img = Image.open(path).convert("F")
    arr = np.asarray(img, dtype=float)  # [row=y-down, col=x]
    arr = np.flipud(arr)  # make row index increase with +y
    lo, hi = float(arr.min()), float(arr.max())
    if hi > lo:
        arr = (arr - lo) / (hi - lo)
    else:
        arr = np.zeros_like(arr)
    elev = (z_min + arr * (z_max - z_min)).T  # -> [ix, iy]
    min_x, min_y, max_x, max_y = bounds
    nx = elev.shape[0]
    cellsize = (max_x - min_x) / (nx - 1) if nx > 1 else 1.0
    return Topography(elev, min_x, min_y, cellsize)


def load_topography(
    path: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    z_min: float = 0.0,
    z_max: float = 1.0,
) -> Topography:
    """Load a :class:`~pedsim.topography.Topography` from a file.

    Supported formats (by extension):

    * ``.asc`` / ``.txt`` -- ESRI ASCII grid (fully georeferenced; ``bounds`` and
      ``z_*`` are ignored).
    * ``.xyz`` / ``.csv`` -- a regular grid of ``x y z`` rows.
    * ``.npy`` -- a 2D NumPy array ``[ix, iy]``; requires ``bounds``.
    * image (``.png`` / ``.tif`` / ``.jpg`` ...) -- grayscale heightmap; requires
      ``bounds`` and the elevation range ``z_min``..``z_max``.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".asc",):
        return _load_ascii_grid(path)
    if ext in (".xyz", ".csv"):
        return _load_xyz(path)
    if ext in (".npy",):
        if bounds is None:
            raise ValueError("bounds is required for .npy topography")
        return _load_npy(path, bounds)
    if ext in (".txt",):
        # Ambiguous: try ASCII-grid header first, fall back to XYZ.
        try:
            return _load_ascii_grid(path)
        except Exception:
            return _load_xyz(path)
    # Assume an image heightmap.
    if bounds is None:
        raise ValueError("bounds is required for image heightmaps")
    return _load_image(path, bounds, z_min, z_max)

"""An offline basemap the project is allowed to carry: relief from its own DEM.

Satellite and street tiles from Google, Esri or the OpenStreetMap tile servers
may not be bulk-downloaded or cached, so the field pack cannot contain them.
The Copernicus DEM can be redistributed with attribution, so the pack ships a
shaded-relief image rendered from it. It is one JPEG whose rows are spaced
evenly in Web-Mercator northing, because that is how a map client stretches an
image between four corner coordinates.
"""
from __future__ import annotations

import glob
import math
import os
from typing import Optional, Tuple

import numpy as np

ATTRIBUTION = "Relief: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA"


def _merc(lat: np.ndarray) -> np.ndarray:
    return np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0))


def _inv_merc(y: np.ndarray) -> np.ndarray:
    return np.degrees(2.0 * np.arctan(np.exp(y)) - np.pi / 2.0)


def sample_dem(paths, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Nearest DEM value at each lon/lat; NaN where no tile covers the point."""
    import rasterio

    out = np.full(lon.shape, np.nan, dtype=float)
    for path in paths:
        need = np.isnan(out)
        if not need.any():
            break
        with rasterio.open(path) as src:
            left, bottom, right, top = src.bounds
            inside = need & (lon >= left) & (lon <= right) & (lat >= bottom) & (lat <= top)
            if not inside.any():
                continue
            rows, cols = rasterio.transform.rowcol(src.transform, lon[inside], lat[inside])
            rows = np.clip(np.asarray(rows), 0, src.height - 1)
            cols = np.clip(np.asarray(cols), 0, src.width - 1)
            vals = src.read(1)[rows, cols].astype(float)
            if src.nodata is not None:
                vals[vals == src.nodata] = np.nan
            out[inside] = vals
    return out


def hillshade(elev: np.ndarray, dx: float, dy: float, azimuth: float = 315.0,
              altitude: float = 45.0, exaggeration: float = 2.0) -> np.ndarray:
    """Lambert shading in 0..1. ``elev`` has north on the first row."""
    gy, gx = np.gradient(elev * exaggeration, dy, dx)
    gy = -gy                                 # rows run north to south
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, -gy)            # downslope direction, clockwise from north
    az = math.radians(azimuth)
    alt = math.radians(altitude)
    shade = (math.sin(alt) * np.cos(slope)
             + math.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(shade, 0.0, 1.0)


def render(paths, bbox: Tuple[float, float, float, float],
           max_side: int = 3600) -> Tuple[np.ndarray, list]:
    """Shaded relief for ``bbox = (south, west, north, east)``.

    Returns the RGB image and its corners ``[nw, ne, se, sw]`` as lon/lat.
    """
    south, west, north, east = bbox
    mid = math.radians((south + north) / 2.0)
    width_m = (east - west) * 111320.0 * math.cos(mid)
    height_m = (north - south) * 111320.0
    px = max(30.0, max(width_m, height_m) / max_side)
    w = int(round(width_m / px))
    h = int(round(height_m / px))
    lons = west + (np.arange(w) + 0.5) / w * (east - west)
    ys = _merc(np.array([north, south]))
    lats = _inv_merc(ys[0] + (np.arange(h) + 0.5) / h * (ys[1] - ys[0]))
    LON, LAT = np.meshgrid(lons, lats)
    elev = sample_dem(paths, LON, LAT)
    if np.isnan(elev).all():
        raise RuntimeError("no DEM tile covers the basemap extent")
    elev = np.where(np.isnan(elev), np.nanmean(elev), elev)
    shade = hillshade(elev, width_m / w, height_m / h)
    # Dark-theme relief: mid greys with a slight warm tint that rises with height,
    # so density colours and white labels stay readable on top.
    lo, hi = np.percentile(elev, [2, 98])
    t = np.clip((elev - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    base = np.stack([62 + 46 * t, 66 + 38 * t, 60 + 22 * t], axis=-1)
    rgb = base * (0.45 + 0.95 * shade[..., None])
    image = np.clip(rgb, 0, 255).astype(np.uint8)
    corners = [[west, north], [east, north], [east, south], [west, south]]
    return image, corners


def write_basemap(root: str, data_dir: Optional[str] = None, pad_deg: float = 0.08,
                  progress=None) -> dict:
    """Write ``basemap.jpg`` for the cluster extent. Returns its index entry,
    or an entry saying why there is none."""
    from . import scenes, sites

    data_dir = data_dir or scenes.DATA_DIR
    tiles = sorted(glob.glob(os.path.join(data_dir, scenes.DEM_GLOB)))
    if not tiles:
        return {"file": "", "reason": "no DEM downloaded when the pack was built"}
    if progress:
        progress("basemap relief")
    south, west, north, east = sites.bounds(usable_only=False)
    bbox = (south - pad_deg, west - pad_deg, north + pad_deg, east + pad_deg)
    image, corners = render(tiles, bbox)
    from PIL import Image

    path = os.path.join(root, "basemap.jpg")
    Image.fromarray(image).save(path, quality=82, optimize=True)
    return {
        "file": "basemap.jpg", "corners": corners,
        "width": int(image.shape[1]), "height": int(image.shape[0]),
        "attribution": ATTRIBUTION,
    }

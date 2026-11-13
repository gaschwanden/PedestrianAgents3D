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


# --------------------------------------------------------- satellite and roads
# Two more layers the pack may legally carry:
#
# * Sentinel-2 cloudless 2016 by EOX (https://s2maps.eu), CC BY 4.0. Ten metre
#   pixels: fields, tracks, wadis and excavation shelters are visible, single
#   walls are not. Later yearly mosaics are non-commercial only, so 2016 it is.
# * OpenStreetMap roads, tracks and place names (ODbL), fetched through
#   Overpass as vector data. This is map *data*, which may be redistributed
#   with attribution; the rendered OSM tiles may not be bulk-downloaded.
#
# Both need the network when the pack is built. Tiles and query results are
# cached under ``data/raw/basemap_cache`` so a rebuild does not ask again.

S2_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
S2_ATTRIBUTION = ("Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH "
                  "(Contains modified Copernicus Sentinel data 2016 & 2017), CC BY 4.0")
OSM_ATTRIBUTION = "Roads and place names © OpenStreetMap contributors, ODbL"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "pedsim-pack/0.5 (offline field pack builder)"


def _cache_dir(data_dir: Optional[str] = None) -> str:
    from . import scenes

    path = os.path.join(data_dir or scenes.DATA_DIR, "basemap_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _get(url: str, cache_path: str, data: Optional[bytes] = None, timeout: int = 60) -> bytes:
    import urllib.request

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        with open(cache_path, "rb") as fh:
            return fh.read()
    import time
    import urllib.error

    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            break
        except urllib.error.HTTPError as error:
            # public servers answer 429 / 502 / 504 when busy: wait and ask again
            if error.code not in (429, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))
    with open(cache_path, "wb") as fh:
        fh.write(payload)
    return payload


def _tile_xy(lon: float, lat: float, z: int) -> Tuple[float, float]:
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _tile_lonlat(x: float, y: float, z: int) -> Tuple[float, float]:
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lon, lat


def write_satellite(root: str, name: str, bbox: Tuple[float, float, float, float],
                    zoom: int, data_dir: Optional[str] = None, quality: int = 80) -> dict:
    """Stitch Sentinel-2 cloudless tiles covering ``bbox = (south, west, north,
    east)`` into ``<name>.jpg``. Whole tiles are kept, so the corners are tile
    edges and the image is exactly linear in Web-Mercator."""
    import io

    from PIL import Image

    south, west, north, east = bbox
    x0, y0 = (int(math.floor(v)) for v in _tile_xy(west, north, zoom))
    x1, y1 = (int(math.floor(v)) for v in _tile_xy(east, south, zoom))
    cache = _cache_dir(data_dir)
    sheet = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            raw = _get(S2_URL.format(z=zoom, x=tx, y=ty),
                       os.path.join(cache, f"s2_{zoom}_{tx}_{ty}.jpg"))
            sheet.paste(Image.open(io.BytesIO(raw)).convert("RGB"),
                        ((tx - x0) * 256, (ty - y0) * 256))
    sheet.save(os.path.join(root, f"{name}.jpg"), quality=quality, optimize=True)
    w_lon, n_lat = _tile_lonlat(x0, y0, zoom)
    e_lon, s_lat = _tile_lonlat(x1 + 1, y1 + 1, zoom)
    return {
        "file": f"{name}.jpg", "zoom": zoom,
        "corners": [[w_lon, n_lat], [e_lon, n_lat], [e_lon, s_lat], [w_lon, s_lat]],
        "width": sheet.size[0], "height": sheet.size[1],
    }


_ROAD_RANK = {
    "motorway": 1, "trunk": 1, "primary": 1, "secondary": 2, "tertiary": 2,
    "unclassified": 3, "residential": 3, "service": 3, "road": 3,
    "track": 4, "path": 4, "footway": 4,
}


def write_osm(root: str, name: str, bbox: Tuple[float, float, float, float],
              detail: bool, data_dir: Optional[str] = None) -> dict:
    """Roads and place names for ``bbox`` as ``<name>.geojson``.

    ``detail`` adds minor roads, tracks and paths (village scale); without it
    only through roads and settlements are kept (cluster scale).
    """
    import json
    import urllib.parse

    south, west, north, east = bbox
    box = f"({south:.5f},{west:.5f},{north:.5f},{east:.5f})"
    roads = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|"
             "service|road|track|path|footway") if detail else (
             "motorway|trunk|primary|secondary|tertiary")
    places = "city|town|village|hamlet" if detail else "city|town|village"
    query = (f'[out:json][timeout:120];('
             f'way["highway"~"^({roads})$"]{box};'
             f'node["place"~"^({places})$"]{box};'
             f');out geom;')
    key = f"osm_{name}_{'d' if detail else 'c'}_{box}.json".replace(",", "_")
    raw = _get(OVERPASS_URL, os.path.join(_cache_dir(data_dir), key),
               data=urllib.parse.urlencode({"data": query}).encode("ascii"), timeout=180)
    features = []
    for el in json.loads(raw).get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way" and el.get("geometry"):
            features.append({
                "type": "Feature",
                "properties": {"kind": "road", "rank": _ROAD_RANK.get(tags.get("highway"), 4),
                               "name": tags.get("name", "")},
                "geometry": {"type": "LineString", "coordinates": [
                    [round(p["lon"], 6), round(p["lat"], 6)] for p in el["geometry"]]},
            })
        elif el["type"] == "node" and tags.get("name"):
            features.append({
                "type": "Feature",
                "properties": {"kind": "place", "place": tags.get("place", ""),
                               "name": tags["name"]},
                "geometry": {"type": "Point",
                             "coordinates": [round(el["lon"], 6), round(el["lat"], 6)]},
            })
    with open(os.path.join(root, f"{name}.geojson"), "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh,
                  ensure_ascii=False, separators=(",", ":"))
    return {"file": f"{name}.geojson", "features": len(features)}


def write_scene_maps(root: str, scenes_index: list, village_margin_m: float = 1500.0,
                     data_dir: Optional[str] = None, progress=None) -> dict:
    """Satellite image and road overlay for every packed scene.

    ``scenes_index`` is the pack index's scene list (each row needs ``id``,
    ``scale`` and the scene's lon/lat ``bounds``). A scene whose download fails
    is listed under ``failed`` and simply has no entry: the client falls back
    to relief.
    """
    out = {"satellite": {}, "osm": {}, "failed": [],
           "attribution": {"satellite": S2_ATTRIBUTION, "osm": OSM_ATTRIBUTION}}
    for row in scenes_index:
        b = row["bounds"]
        if row["scale"] == "cluster":
            bbox = (b["south"], b["west"], b["north"], b["east"])
            zoom, detail = 12, False
        else:
            lat = (b["south"] + b["north"]) / 2.0
            dlat = village_margin_m / 111320.0
            dlon = village_margin_m / (111320.0 * math.cos(math.radians(lat)))
            bbox = (b["south"] - dlat, b["west"] - dlon, b["north"] + dlat, b["east"] + dlon)
            zoom, detail = 14, True
        if progress:
            progress(f"maps for {row['label']}")
        for kind, make in (
            ("satellite", lambda: write_satellite(root, "sat-" + row["id"], bbox, zoom, data_dir)),
            ("osm", lambda: write_osm(root, "osm-" + row["id"], bbox, detail, data_dir)),
        ):
            try:
                out[kind][row["id"]] = make()
            except Exception as error:      # no network, server busy: not fatal
                out["failed"].append({"scene": row["id"], "kind": kind,
                                      "error": f"{type(error).__name__}: {error}"})
    return out

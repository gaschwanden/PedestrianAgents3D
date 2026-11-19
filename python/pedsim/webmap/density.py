"""Occupancy in geographic space, in three units, as a Cloud-Optimised GeoTIFF.

The grid is ``[x, y]`` with x east and y north. A north-up GeoTIFF stores rows
from the north, so the array is transposed and flipped on the way out.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple

import numpy as np


def density_array(occupancy: np.ndarray, mode: str = "trips_per_day",
                  n_agents: int = 1, n_days: float = 1.0) -> np.ndarray:
    """``raw`` visits, ``trips_per_day`` (per agent and day), or ``relative`` 0–1.

    The relative stretch is a percentile stretch (2nd to 98th) so a single
    busy cell does not flatten the rest. The spatial order of cells is unchanged.
    """
    data = np.asarray(occupancy, dtype=float)
    if mode == "raw":
        return data
    if mode == "trips_per_day":
        return data / max(n_agents, 1) / max(float(n_days), 1e-6)
    if mode == "relative":
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            return np.zeros_like(data)
        lo, hi = np.percentile(finite, [2, 98])
        if hi <= lo:
            hi = lo + 1.0
        return np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    raise ValueError(f"unknown density mode {mode!r}")


def write_geotiff(path: str, arrays: Sequence[np.ndarray], origin_xy: Tuple[float, float],
                  cellsize: float, band_names: Sequence[str], crs: str = "EPSG:32637",
                  nodata: float = -9999.0) -> str:
    """Write a tiled GeoTIFF. ``origin_xy`` is the south-west corner, in ``crs``.

    Requires rasterio. The array axes are ``[x, y]`` (east, north).
    """
    try:
        import rasterio
        from rasterio.transform import from_origin
    except ImportError as exc:  # pragma: no cover
        raise ImportError("writing a GeoTIFF needs rasterio") from exc

    stack = [np.asarray(a, dtype=np.float32) for a in arrays]
    nx, ny = stack[0].shape
    # north-up: row 0 is the northern edge. Our y index 0 is the southern edge.
    north_up = [np.flipud(a.T) for a in stack]
    west, south = origin_xy
    north = south + ny * cellsize
    transform = from_origin(west, north, cellsize, cellsize)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": len(north_up),
        "width": nx,
        "height": ny,
        "crs": crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": min(256, nx),
        "blockysize": min(256, ny),
        "compress": "deflate",
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        for i, (band, name) in enumerate(zip(north_up, band_names), start=1):
            out = np.where(np.isfinite(band), band, nodata).astype(np.float32)
            dst.write(out, i)
            dst.set_band_description(i, name)
    return path


def occupancy_to_cog(sim, path: str, mode: str = "trips_per_day",
                     n_days: float = 1.0, frame=None) -> str:
    """Write the simulation's occupancy. ``frame`` shifts local metres into UTM."""
    grid = sim.grid
    data = density_array(grid.occupancy, mode=mode, n_agents=sim.num_agents, n_days=n_days)
    west, south = grid.sx, grid.sy
    if frame is not None:
        east, north = frame.to_projected(np.array([west]), np.array([south]))
        west, south = float(east[0]), float(north[0])
    return write_geotiff(path, [data], (west, south), grid.gridsize, [mode])

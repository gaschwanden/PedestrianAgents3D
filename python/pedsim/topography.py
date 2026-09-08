"""Topography (terrain elevation) and the slope-dependent movement cost model.

The original simulation walks on a flat plane: every navigable grid step costs
the same. Real settlements such as Göbekli Tepe sit on and around hills, and
pedestrians expend extra effort walking uphill, so they tend to contour around
slopes rather than climb straight over them.

We model that with two pieces:

* :class:`Topography` -- a georeferenced elevation raster that can be sampled at
  any world coordinate (bilinear) and resampled onto the navigation grid.
* :class:`TerrainCost` -- converts a single grid step (its horizontal length and
  its rise/fall) into a traversal cost using *Tobler's hiking function*, the
  standard model for walking speed as a function of slope.

The navigation grid then builds its cost-to-destination field with a
slope-weighted Dijkstra search instead of a uniform-cost flood fill, which makes
agents prefer gentle, contour-following routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np


class Topography:
    """A regular elevation grid with a simple world transform.

    ``elevation`` is indexed ``[ix, iy]`` where ``ix`` runs along +x and ``iy``
    along +y. The world coordinate of sample ``(ix, iy)`` is::

        x = x0 + ix * cellsize
        y = y0 + iy * cellsize
    """

    def __init__(self, elevation: np.ndarray, x0: float, y0: float, cellsize: float):
        self.elevation = np.asarray(elevation, dtype=float)
        if self.elevation.ndim != 2:
            raise ValueError("elevation must be a 2D array")
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.cellsize = float(cellsize)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        nx, ny = self.elevation.shape
        return (
            self.x0,
            self.y0,
            self.x0 + (nx - 1) * self.cellsize,
            self.y0 + (ny - 1) * self.cellsize,
        )

    def sample(self, x: float, y: float) -> float:
        """Bilinearly sample the elevation at world coordinate ``(x, y)``.

        Coordinates outside the raster are clamped to the nearest edge.
        """
        nx, ny = self.elevation.shape
        fx = (x - self.x0) / self.cellsize
        fy = (y - self.y0) / self.cellsize
        fx = min(max(fx, 0.0), nx - 1.0)
        fy = min(max(fy, 0.0), ny - 1.0)
        ix = int(np.floor(fx))
        iy = int(np.floor(fy))
        ix1 = min(ix + 1, nx - 1)
        iy1 = min(iy + 1, ny - 1)
        tx = fx - ix
        ty = fy - iy
        e = self.elevation
        top = e[ix, iy] * (1 - tx) + e[ix1, iy] * tx
        bot = e[ix, iy1] * (1 - tx) + e[ix1, iy1] * tx
        return float(top * (1 - ty) + bot * ty)

    def sample_grid(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Resample onto grid cell centres, returning an ``[nx, ny]`` array."""
        out = np.empty((xs.shape[0], ys.shape[0]), dtype=float)
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                out[i, j] = self.sample(x, y)
        return out

    @classmethod
    def from_function(
        cls,
        func: Callable[[float, float], float],
        bounds: Tuple[float, float, float, float],
        nx: int,
        ny: int,
    ) -> "Topography":
        """Build a topography by evaluating ``func(x, y)`` on a regular grid."""
        min_x, min_y, max_x, max_y = bounds
        xs = np.linspace(min_x, max_x, nx)
        ys = np.linspace(min_y, max_y, ny)
        elev = np.empty((nx, ny), dtype=float)
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                elev[i, j] = func(x, y)
        cellsize = (max_x - min_x) / (nx - 1) if nx > 1 else 1.0
        return cls(elev, min_x, min_y, cellsize)


@dataclass
class TerrainCost:
    """Slope-dependent step-cost model based on Tobler's hiking function.

    Tobler's function gives walking speed ``v`` (arbitrary units) as::

        v = base_speed * exp(-slope_factor * |slope + slope_offset|)

    where ``slope`` is rise/run (dimensionless). The cost of a step is its
    horizontal length divided by that speed, i.e. proportional to travel time.
    A small negative ``slope_offset`` reproduces the real effect that the fastest
    walking is on a gentle downhill rather than dead flat.

    Parameters
    ----------
    base_speed:
        Speed on the flat. Only relative values matter for routing.
    slope_factor:
        How strongly slope penalises speed. ``3.5`` is Tobler's original value;
        larger values make agents avoid hills more aggressively.
    slope_offset:
        Slope at which walking is fastest is ``-slope_offset``.
    impassable_slope:
        Steps steeper than this (absolute rise/run) are treated as impassable.
    """

    base_speed: float = 1.0
    slope_factor: float = 3.5
    slope_offset: float = 0.05
    impassable_slope: float = 1.2

    def speed(self, slope: float) -> float:
        return self.base_speed * np.exp(-self.slope_factor * abs(slope + self.slope_offset))

    def step_cost(self, dz: float, horizontal_dist: float) -> float:
        """Cost of walking one step of horizontal length ``horizontal_dist`` with
        elevation change ``dz`` (positive = uphill). Returns ``inf`` if too steep.
        """
        if horizontal_dist <= 0:
            return float("inf")
        slope = dz / horizontal_dist
        if abs(slope) > self.impassable_slope:
            return float("inf")
        return horizontal_dist / self.speed(slope)

"""Importing published site plans: hand-drawn excavation drawings as obstacles.

At village scale the obstacles that matter are walls, and for these sites the
walls exist as **ink on paper** -- figure plates in excavation reports, drawn by
hand at some scale the caption may or may not state. None of them are
georeferenced. So this module does the one thing that makes such a drawing
usable: it pins the image to the ground with a **similarity transform** (scale,
rotation, translation) that the user supplies, and then samples the ink onto the
simulation grid.

Two ways to pin it, matching what plans actually carry:

* :meth:`Georeference.from_control_points` -- two points whose ground position
  you know (an excavation grid intersection, a trench corner, a datum). This is
  the accurate route, and it solves scale and rotation together.
* :meth:`Georeference.from_scale_bar` -- a scale bar and a north arrow, which is
  what most published plates give you. Less accurate, because it fixes the
  *orientation and size* but leaves the *position* to a single anchor point.

A similarity transform is deliberate. Affine or projective fits would absorb the
draughtsman's distortion into a skew that has no physical meaning, and would let
a badly-placed control point silently stretch the plan. A rigid scale-and-rotate
either fits or visibly does not, which is the honest failure mode.

The ink becomes a **blocking layer**, not building footprints. Tracing a
hand-drawn wall into a clean polygon is a separate and unreliable problem; a
mask says exactly what the drawing says -- "something is here" -- without
inventing corners the draughtsman never drew.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .layers import BLOCK, FRICTION, Layer

Point = Tuple[float, float]


@dataclass(frozen=True)
class ControlPoint:
    """A point identified both on the image and on the ground.

    ``pixel`` is ``(column, row)`` in image coordinates, with the row measured
    downwards from the top as images are stored. ``world`` is ``(x, y)`` in the
    simulation's local metric frame, y upwards.
    """

    pixel: Point
    world: Point
    label: str = ""


@dataclass(frozen=True)
class Georeference:
    """Similarity transform from image pixels to world metres.

    ``world = translation + scale * R(rotation) @ (px, -py)``

    The ``-py`` is the image/world y-axis flip, done once here so nothing
    downstream has to remember it.
    """

    scale: float          # metres per pixel
    rotation: float       # radians, counter-clockwise
    tx: float
    ty: float
    residual_m: float = 0.0     # fit error, 0.0 for an exact two-point fit
    note: str = ""

    # -- construction -------------------------------------------------------
    @classmethod
    def from_control_points(cls, a: ControlPoint, b: ControlPoint) -> "Georeference":
        """Fit scale, rotation and translation from two known points.

        Two points are exactly enough for a similarity transform, so the fit is
        exact by construction -- which is why you should choose them as far
        apart as the drawing allows. Two points 20 mm apart on a plate will
        amplify any misclick across the whole plan.
        """
        pdx = b.pixel[0] - a.pixel[0]
        pdy = -(b.pixel[1] - a.pixel[1])
        wdx = b.world[0] - a.world[0]
        wdy = b.world[1] - a.world[1]
        plen = math.hypot(pdx, pdy)
        wlen = math.hypot(wdx, wdy)
        if plen <= 0:
            raise ValueError("the two control points are the same pixel")
        if wlen <= 0:
            raise ValueError("the two control points have the same ground position")
        scale = wlen / plen
        rotation = math.atan2(wdy, wdx) - math.atan2(pdy, pdx)
        geo = cls(scale, rotation, 0.0, 0.0)
        # place the transform so control point ``a`` lands where it should
        x0, y0 = geo._rotate_scale(a.pixel[0], -a.pixel[1])
        return cls(scale, rotation, a.world[0] - x0, a.world[1] - y0,
                   note=f"2 control points {plen:.0f} px apart "
                        f"({wlen:.1f} m on the ground)")

    @classmethod
    def from_scale_bar(cls, anchor: ControlPoint, bar_pixels: float,
                       bar_metres: float, north_deg: float = 0.0) -> "Georeference":
        """Fit from a scale bar and a north arrow.

        Parameters
        ----------
        anchor:
            One point tying the image to the ground. With only a scale bar this
            is the sole positional constraint, so choose something meaningful --
            the centre of the excavation area, or a feature you can also see on
            satellite imagery.
        bar_pixels, bar_metres:
            Length of the plan's scale bar, measured in pixels, and what it says
            it represents.
        north_deg:
            Compass bearing of the image's *up* direction. 0 for a north-up
            plan; 90 if up on the page points east. Most published plans are
            north-up or close to it, but check the arrow rather than assuming.
        """
        if bar_pixels <= 0 or bar_metres <= 0:
            raise ValueError("the scale bar needs a positive length in both units")
        scale = bar_metres / bar_pixels
        rotation = -math.radians(north_deg)
        geo = cls(scale, rotation, 0.0, 0.0)
        x0, y0 = geo._rotate_scale(anchor.pixel[0], -anchor.pixel[1])
        return cls(scale, rotation, anchor.world[0] - x0, anchor.world[1] - y0,
                   note=f"scale bar {bar_metres:g} m = {bar_pixels:g} px, "
                        f"north {north_deg:g}deg from image up")

    # -- transforms ---------------------------------------------------------
    def _rotate_scale(self, x, y):
        c, s = math.cos(self.rotation), math.sin(self.rotation)
        return self.scale * (x * c - y * s), self.scale * (x * s + y * c)

    def to_world(self, px, py):
        """Image pixel(s) -> world metres. Accepts scalars or arrays."""
        x, y = self._rotate_scale(np.asarray(px, dtype=float),
                                  -np.asarray(py, dtype=float))
        return x + self.tx, y + self.ty

    def to_pixel(self, wx, wy):
        """World metres -> image pixel(s). The inverse of :meth:`to_world`."""
        x = np.asarray(wx, dtype=float) - self.tx
        y = np.asarray(wy, dtype=float) - self.ty
        c, s = math.cos(-self.rotation), math.sin(-self.rotation)
        px = (x * c - y * s) / self.scale
        py = (x * s + y * c) / self.scale
        return px, -py

    @property
    def metres_per_pixel(self) -> float:
        return self.scale

    @property
    def north_deg(self) -> float:
        """Bearing of the image's up direction, the inverse of the constructor
        argument."""
        return -math.degrees(self.rotation) % 360.0

    def check(self, points: Sequence[ControlPoint]) -> float:
        """Root-mean-square ground error over ``points``, in metres.

        Use it with a *third* point the fit did not see. A two-point fit is
        exact on its own points and tells you nothing about whether the plan is
        actually a faithful similarity of the ground.
        """
        if not points:
            return 0.0
        errs = []
        for cp in points:
            wx, wy = self.to_world(*cp.pixel)
            errs.append(math.hypot(float(wx) - cp.world[0], float(wy) - cp.world[1]))
        return float(np.sqrt(np.mean(np.square(errs))))


@dataclass
class SitePlan:
    """A published plan pinned to the ground and ready to sample.

    ``image`` is ``[rows, cols]`` greyscale in 0..1, 0 = black ink, 1 = white
    paper. Colour input is converted on load.
    """

    image: np.ndarray
    geo: Georeference
    name: str = "plan"
    source: str = ""          # citation, so an imported wall can be traced back

    def __post_init__(self) -> None:
        img = np.asarray(self.image, dtype=float)
        if img.ndim == 3:
            img = img[..., :3].mean(axis=2)
        if img.max() > 1.0:
            img = img / 255.0
        self.image = np.clip(img, 0.0, 1.0)

    # -- loading ------------------------------------------------------------
    @classmethod
    def load(cls, path: str, geo: Georeference, name: str = "",
             source: str = "") -> "SitePlan":
        """Read an image file (PNG, JPEG, TIFF...) via Pillow."""
        from PIL import Image

        with Image.open(path) as im:
            arr = np.asarray(im.convert("L"), dtype=float) / 255.0
        return cls(arr, geo, name or os.path.splitext(os.path.basename(path))[0],
                   source)

    @property
    def shape(self) -> Tuple[int, int]:
        """``(rows, cols)`` of the image."""
        return self.image.shape[0], self.image.shape[1]

    def world_corners(self) -> List[Point]:
        """The image's four corners in world metres, clockwise from top-left."""
        rows, cols = self.shape
        px = [0.0, cols, cols, 0.0]
        py = [0.0, 0.0, rows, rows]
        xs, ys = self.geo.to_world(np.array(px), np.array(py))
        return [(float(x), float(y)) for x, y in zip(xs, ys)]

    def world_bounds(self) -> Tuple[float, float, float, float]:
        """``(min_x, min_y, max_x, max_y)`` covered by the plan, in metres."""
        pts = self.world_corners()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def ground_size(self) -> Tuple[float, float]:
        """Ground width and height the image covers, in metres."""
        rows, cols = self.shape
        return cols * self.geo.scale, rows * self.geo.scale

    # -- ink ----------------------------------------------------------------
    def ink(self, threshold: float = 0.5) -> np.ndarray:
        """Boolean mask of drawn ink: anything darker than ``threshold``.

        Hand-drawn plans are dark line and hatching on light paper, so a single
        darkness threshold is usually enough. Scans with a grey or yellowed
        background need a *higher* threshold, not a lower one; inspect the
        histogram if the mask comes out empty or solid.
        """
        return self.image < threshold

    def coverage(self, threshold: float = 0.5) -> float:
        """Fraction of the image that is ink. A sanity check: a plan that comes
        out 90 % ink means the threshold is wrong, not that the site was solid
        wall."""
        return float(self.ink(threshold).mean())

    # -- sampling onto a grid ----------------------------------------------
    def sample(self, xs: np.ndarray, ys: np.ndarray,
               threshold: float = 0.5) -> np.ndarray:
        """Sample the ink mask at world coordinates, returning ``[nx, ny]``.

        Cells falling outside the image are ``False`` -- a plan only claims to
        describe the ground it covers, and the area around it is *unknown*, not
        empty. Keep that in mind when the plan is smaller than the scene.
        """
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        px, py = self.geo.to_pixel(X, Y)
        rows, cols = self.shape
        col = np.round(px).astype(int)
        row = np.round(py).astype(int)
        inside = (col >= 0) & (col < cols) & (row >= 0) & (row < rows)
        out = np.zeros(X.shape, dtype=bool)
        ink = self.ink(threshold)
        out[inside] = ink[row[inside], col[inside]]
        return out

    def covered(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Which cells the plan actually covers, ``[nx, ny]``.

        Worth drawing alongside the walls: it is the difference between "the
        plan says there is nothing here" and "the plan does not reach here".
        """
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        px, py = self.geo.to_pixel(X, Y)
        rows, cols = self.shape
        return ((px >= 0) & (px < cols) & (py >= 0) & (py < rows))

    # -- layers -------------------------------------------------------------
    def wall_layer(self, xs: np.ndarray, ys: np.ndarray, threshold: float = 0.5,
                   name: str = "", color: Tuple[int, int, int] = (225, 190, 140)
                   ) -> Layer:
        """The ink as an impassable layer -- walls you cannot walk through."""
        mask = self.sample(xs, ys, threshold)
        return Layer(name or f"{self.name} walls", mask.astype(float),
                     kind=BLOCK, color=color,
                     description=f"walls traced from {self.source or self.name}")

    def rough_layer(self, xs: np.ndarray, ys: np.ndarray, threshold: float = 0.5,
                    cost: float = 3.0, name: str = "",
                    color: Tuple[int, int, int] = (200, 170, 120)) -> Layer:
        """The ink as *costly* rather than impassable.

        The right choice for rubble, collapse, or a wall you believe was low
        enough to climb -- and for a plan you do not fully trust, where blocking
        outright would overstate what the drawing shows.
        """
        mask = self.sample(xs, ys, threshold).astype(float) * cost
        return Layer(name or f"{self.name} rubble", mask, kind=FRICTION,
                     color=color,
                     description=f"rough going traced from {self.source or self.name}")

    def coverage_layer(self, xs: np.ndarray, ys: np.ndarray,
                       name: str = "") -> Layer:
        """Where the plan has anything to say at all, as a display layer."""
        from .layers import INFO

        return Layer(name or f"{self.name} extent",
                     self.covered(xs, ys).astype(float), kind=INFO,
                     color=(150, 200, 255),
                     description="area the plan actually covers")


def add_plan_to(sim, plan: SitePlan, threshold: float = 0.5,
                blocking: bool = True, cost: float = 3.0) -> Layer:
    """Import a plan into a running simulation and re-route around it.

    Returns the layer that was added, so its weight can be tuned or it can be
    removed again -- an imported interpretation should stay something you can
    switch off.
    """
    g = sim.grid
    layer = (plan.wall_layer(g.xs, g.ys, threshold) if blocking
             else plan.rough_layer(g.xs, g.ys, threshold, cost))
    sim.add_layer(layer)
    return layer

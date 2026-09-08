"""Generate a synthetic Göbekli Tepe-like dataset.

Writes two files that exercise the importers:

* ``data/gobekli_site.json`` -- archaeological outlines: circular enclosures as
  pedestrian *sinks* (destinations), perimeter gates as *sources*, and a few
  rectangular structures as movement blockers.
* ``data/gobekli_dem.asc`` -- an ESRI ASCII elevation grid of the tell (a
  "potbelly hill"): an elongated central mound plus a steeper south-western
  ridge, so slope-aware agents visibly detour to gentler ground.

This is illustrative synthetic data, not survey data.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

EXTENT = 150.0  # half-width of the (square) site, metres


def circle(cx: float, cy: float, r: float, n: int = 32):
    return [
        [cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)]
        for k in range(n)
    ]


def rect(cx: float, cy: float, w: float, h: float, angle: float = 0.0):
    hw, hh = w / 2, h / 2
    ca, sa = math.cos(angle), math.sin(angle)
    pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [[cx + px * ca - py * sa, cy + px * sa + py * ca] for px, py in pts]


def build_site() -> dict:
    features = []

    # Four monumental circular enclosures near the summit -> destinations (sinks)
    # with a small origin weight so some trips also move between them.
    enclosures = [
        ("Enclosure A", 20, 25, 16),
        ("Enclosure B", -25, 15, 14),
        ("Enclosure C", -10, -25, 18),
        ("Enclosure D", 30, -18, 15),
    ]
    for name, cx, cy, r in enclosures:
        features.append({
            "name": name,
            "role": "sink",
            "group": 0,
            "origin_weight": 0.15,
            "dest_weight": 1.0,
            "polygon": circle(cx, cy, r, 36),
        })

    # Perimeter gates where pilgrims arrive -> pure sources at the base of the tell.
    gates = [
        ("N gate", 0, 132),
        ("NE gate", 95, 95),
        ("E gate", 133, 0),
        ("S gate", 0, -132),
        ("SW gate", -95, -95),
        ("W gate", -133, 5),
    ]
    for name, cx, cy in gates:
        features.append({
            "name": name,
            "role": "source",
            "group": 1,
            "origin_weight": 1.0,
            "dest_weight": 0.0,
            "polygon": circle(cx, cy, 6, 20),
        })

    # A few rectangular structures that block movement (ancillary buildings/walls).
    blockers = [
        ("Wall 1", 60, 40, 8, 46, 0.4),
        ("Wall 2", -55, -45, 50, 8, -0.3),
        ("Store building", -60, 55, 20, 14, 0.2),
        ("Terrace wall", 55, -60, 44, 7, 1.1),
    ]
    for name, cx, cy, w, h, ang in blockers:
        features.append({
            "name": name,
            "role": "building",
            "polygon": rect(cx, cy, w, h, ang),
        })

    boundary = [[-EXTENT, -EXTENT], [EXTENT, -EXTENT], [EXTENT, EXTENT], [-EXTENT, EXTENT]]
    return {"boundary": boundary, "features": features}


def elevation_function(x: float, y: float) -> float:
    """The tell: an elongated central mound + a steep SW ridge."""
    # Elongated main mound (steeper N-S than E-W).
    main = 18.0 * math.exp(-(((x) / 95.0) ** 2 + ((y) / 70.0) ** 2))
    # Steeper secondary ridge to the south-west that agents should avoid.
    rx, ry = x + 70, y + 55
    ridge = 12.0 * math.exp(-((rx / 26.0) ** 2 + (ry / 55.0) ** 2))
    # Gentle regional tilt.
    tilt = 0.02 * y
    return main + ridge + tilt


def write_ascii_grid(path: str, nx: int = 121, ny: int = 121) -> None:
    xs = np.linspace(-EXTENT, EXTENT, nx)
    ys = np.linspace(-EXTENT, EXTENT, ny)
    elev = np.empty((nx, ny))  # [ix, iy]
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            elev[i, j] = elevation_function(x, y)
    cellsize = (2 * EXTENT) / (nx - 1)
    # ESRI ASCII lists rows north (max y) first; loader flips + transposes back.
    rows = np.flipud(elev.T)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"ncols {nx}\n")
        fh.write(f"nrows {ny}\n")
        fh.write(f"xllcorner {-EXTENT}\n")
        fh.write(f"yllcorner {-EXTENT}\n")
        fh.write(f"cellsize {cellsize}\n")
        fh.write("NODATA_value -9999\n")
        for r in range(rows.shape[0]):
            fh.write(" ".join(f"{v:.3f}" for v in rows[r]) + "\n")


def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    site = build_site()
    site_path = os.path.join(DATA, "gobekli_site.json")
    with open(site_path, "w", encoding="utf-8") as fh:
        json.dump(site, fh, indent=2)
    dem_path = os.path.join(DATA, "gobekli_dem.asc")
    write_ascii_grid(dem_path)
    print(f"wrote {site_path}")
    print(f"wrote {dem_path}")


if __name__ == "__main__":
    main()

"""Corridor centrelines from a density raster.

Cells at or above a threshold are thinned to a one-cell skeleton and then
traced into polylines. Douglas–Peucker simplifies them at half a cell.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np


def threshold_mask(density: np.ndarray, threshold: float = None,
                   percentile: float = 90.0) -> np.ndarray:
    data = np.asarray(density, dtype=float)
    if threshold is None:
        positive = data[data > 0]
        threshold = float(np.percentile(positive, percentile)) if positive.size else 1.0
    return data >= threshold


def skeletonise(mask: np.ndarray) -> np.ndarray:
    """Zhang–Suen thinning. ``mask`` is boolean, True = corridor."""
    img = np.asarray(mask, dtype=np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            to_clear = []
            nx, ny = img.shape
            for i in range(1, nx - 1):
                for j in range(1, ny - 1):
                    if img[i, j] == 0:
                        continue
                    p = [
                        img[i, j],
                        img[i, j + 1], img[i + 1, j + 1], img[i + 1, j],
                        img[i + 1, j - 1], img[i, j - 1], img[i - 1, j - 1],
                        img[i - 1, j], img[i - 1, j + 1],
                    ]
                    neighbors = p[1:]
                    n_sum = int(sum(neighbors))
                    if n_sum < 2 or n_sum > 6:
                        continue
                    transitions = 0
                    seq = neighbors + [neighbors[0]]
                    for a, b in zip(seq, seq[1:]):
                        if a == 0 and b == 1:
                            transitions += 1
                    if transitions != 1:
                        continue
                    if step == 0:
                        if p[1] * p[3] * p[5] != 0:
                            continue
                        if p[3] * p[5] * p[7] != 0:
                            continue
                    else:
                        if p[1] * p[3] * p[7] != 0:
                            continue
                        if p[1] * p[5] * p[7] != 0:
                            continue
                    to_clear.append((i, j))
            if to_clear:
                changed = True
                for i, j in to_clear:
                    img[i, j] = 0
    return img.astype(bool)


def _neighbours(i: int, j: int, img: np.ndarray) -> List[Tuple[int, int]]:
    out = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            ni, nj = i + di, j + dj
            if 0 <= ni < img.shape[0] and 0 <= nj < img.shape[1] and img[ni, nj]:
                out.append((ni, nj))
    return out


def trace(skel: np.ndarray) -> List[List[Tuple[int, int]]]:
    """Walk the skeleton into polylines, starting at endpoints and junctions."""
    img = skel.copy()
    lines = []
    nx, ny = img.shape
    endpoints = []
    for i in range(nx):
        for j in range(ny):
            if img[i, j] and len(_neighbours(i, j, img)) != 2:
                endpoints.append((i, j))
    if not endpoints:
        # a closed loop: start anywhere
        ys, xs = np.where(img.T) if False else (None, None)
        found = np.argwhere(img)
        if found.size:
            endpoints.append(tuple(found[0]))
    seen = set()
    for start in endpoints:
        for nxt in _neighbours(*start, img):
            key = (start, nxt)
            if key in seen:
                continue
            line = [start, nxt]
            seen.add(key)
            prev, cur = start, nxt
            while True:
                nbs = [p for p in _neighbours(*cur, img) if p != prev]
                if not nbs:
                    break
                nxt = nbs[0]
                seen.add((cur, nxt))
                line.append(nxt)
                if len(_neighbours(*nxt, img)) != 2:
                    break
                prev, cur = cur, nxt
            if len(line) >= 2:
                lines.append(line)
    return lines


def douglas_peucker(points: Sequence[Tuple[float, float]], tolerance: float) -> List[Tuple[float, float]]:
    if len(points) < 3 or tolerance <= 0:
        return list(points)
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    worst = 0.0
    index = 0
    for i, (x, y) in enumerate(points[1:-1], start=1):
        dist = abs(dy * x - dx * y + end[0] * start[1] - end[1] * start[0]) / length
        if dist > worst:
            worst = dist
            index = i
    if worst <= tolerance:
        return [start, end]
    left = douglas_peucker(points[:index + 1], tolerance)
    right = douglas_peucker(points[index:], tolerance)
    return left[:-1] + right


def extract_corridors(density: np.ndarray, cellsize: float, origin: Tuple[float, float],
                      threshold: float = None, mean_density: np.ndarray = None) -> List[dict]:
    """Polylines in world metres. Each has ``mean_density`` and ``coords``."""
    mask = threshold_mask(density, threshold=threshold)
    if not mask.any():
        return []
    skel = skeletonise(mask)
    lines = trace(skel)
    ox, oy = origin
    out = []
    source = density if mean_density is None else mean_density
    for line in lines:
        world = [(ox + i * cellsize, oy + j * cellsize) for i, j in line]
        simple = douglas_peucker(world, tolerance=0.5 * cellsize)
        values = [float(source[i, j]) for i, j in line]
        out.append({
            "coords": simple,
            "mean_density": float(np.mean(values)) if values else 0.0,
            "p_exceed": 1.0,
        })
    return out

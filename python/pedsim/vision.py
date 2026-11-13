"""The vision-cone scan for every walker at once.

:meth:`pedsim.agent.Agent.vision_scan` is the reference: one walker, one
sight-line, one cell at a time, as in the Java original. It is also most of the
run time, because each tick reads a few hundred thousand cells from Python.
:func:`scan_all` computes the same thing for all walkers with array operations.

"The same" is literal. Every value is produced by the same floating-point
operations in the same order (ray angles by repeated addition, ``cos``/``sin``
from :mod:`math`, penalties summed along the ray), candidates are listed in the
same order, and each walker makes its one random draw in the same sequence. A
run therefore gives the same occupancy array bit for bit either way; the test
suite checks that.
"""
from __future__ import annotations

import math
from typing import List

import numpy as np


def _cost_stack(grid):
    """Cost fields as one ``(k, nx, ny)`` array plus ``od index -> k``."""
    fields = grid._cost_fields
    cached = getattr(grid, "_vision_stack", None)
    if cached is not None:
        keys, arrays, stack, slot = cached
        if len(keys) == len(fields) and all(
                fields.get(k) is a for k, a in zip(keys, arrays)):
            return stack, slot
    keys = list(fields.keys())
    arrays = [fields[k] for k in keys]
    stack = (np.stack(arrays) if arrays
             else np.zeros((0, grid.nx, grid.ny), dtype=float))
    slot = {k: n for n, k in enumerate(keys)}
    grid._vision_stack = (keys, arrays, stack, slot)
    return stack, slot


def scan_all(sim) -> None:
    """Run the vision scan for every active agent. Sets ``far_px``/``far_py``."""
    grid = sim.grid
    nx, ny = grid.nx, grid.ny
    cone = int(sim.cone_vision)
    stack, slot = _cost_stack(grid)
    step = sim.radius_divider

    agents: List = []       # walkers that get as far as casting rays
    curr: List[float] = []
    targets: List[int] = []
    cos_all: List[float] = []
    sin_all: List[float] = []
    owner: List[int] = []
    for a in sim.agents:
        if not a.active:
            continue
        a.far_px = -1
        a.far_py = -1
        k = slot.get(a.target)
        if k is None:
            continue
        if not (0 <= a.px < nx and 0 <= a.py < ny):
            continue
        d = stack[k, min(max(int(a.px), 0), nx - 1), min(max(int(a.py), 0), ny - 1)]
        if not math.isfinite(d):
            continue
        angle = 0.0
        if a.vy != 0:
            angle = -math.atan(a.vx / a.vy)
        if a.vy < 0:
            angle = math.pi + math.atan(a.vx / -a.vy)
        n = len(agents)
        j_angle = angle
        end = math.pi + angle + step
        while j_angle < end:
            cos_all.append(math.cos(j_angle))
            sin_all.append(math.sin(j_angle))
            owner.append(n)
            j_angle += step
        agents.append(a)
        curr.append(d)
        targets.append(k)
    if not agents:
        return
    if cone <= 1 or not owner:
        for a in agents:
            sim.weighted_index([])
        return

    own = np.asarray(owner, dtype=np.intp)
    reach = np.arange(1, cone, dtype=float)
    X = reach[None, :] * np.asarray(cos_all)[:, None]          # (rays, cone-1)
    Y = reach[None, :] * np.asarray(sin_all)[:, None]
    px = np.fromiter((a.px for a in agents), dtype=float, count=len(agents))
    py = np.fromiter((a.py for a in agents), dtype=float, count=len(agents))
    # int() and astype both truncate toward zero
    PX = (px[own][:, None] + X).astype(np.intp)
    PY = (py[own][:, None] + Y).astype(np.intp)
    outside = (PX < 0) | (PX >= nx) | (PY < 0) | (PY >= ny)
    PXc = np.clip(PX, 0, nx - 1)
    PYc = np.clip(PY, 0, ny - 1)
    wall = ~grid.walkable[PXc, PYc] & ~outside
    stopped = outside | wall
    # cells strictly before the first stop on each ray are the ones seen through
    seen = ~np.logical_or.accumulate(stopped, axis=1)

    if sim.accumulate_visibility:
        # the sight-line marks every cell it crosses, and the wall it ends on
        first = stopped & ~np.logical_or.accumulate(
            np.pad(stopped, ((0, 0), (1, 0)))[:, :-1], axis=1)
        mark = seen | (first & wall)
        rows = np.nonzero(mark)
        mi, mj = PXc[rows], PYc[rows]
        np.add.at(grid.visibility, (mi, mj), 1.0)
        groups = np.fromiter((a.group for a in agents), dtype=np.intp,
                             count=len(agents))[own][rows[0]]
        ok = (groups >= 0) & (groups < grid.num_groups)
        np.add.at(grid.visibility_o, (mi[ok], mj[ok], groups[ok]), 1.0)

    D = stack[np.asarray(targets, dtype=np.intp)[own][:, None], PXc, PYc]
    left = D
    if grid.step_penalty is not None:
        # the going crossed so far along the ray, summed in walking order
        left = D + np.cumsum(np.where(seen, grid.step_penalty[PXc, PYc], 0.0), axis=1)
    with np.errstate(invalid="ignore"):
        good = seen & np.isfinite(D) & (D >= 0) & (left < np.asarray(curr)[own][:, None])

    flat = np.flatnonzero(good)
    width = cone - 1
    who = own[flat // width]
    bounds = np.searchsorted(who, np.arange(len(agents) + 1))
    weights = (X * X + Y * Y).ravel()[flat].tolist()
    cx = PX.ravel()[flat].tolist()
    cy = PY.ravel()[flat].tolist()
    edges = bounds.tolist()
    for n, a in enumerate(agents):
        s, e = edges[n], edges[n + 1]
        idx = sim.weighted_index(weights[s:e])
        if idx != -1:
            a.far_px = cx[s + idx]
            a.far_py = cy[s + idx]

"""Pedestrian agent.

The steering here is a faithful port of the original project and is deliberately
*not* a perfect shortest-path follower. Every step an agent:

1. **Scans the flood-fill with a cone of vision** (:meth:`Agent.vision_scan`).
   It sweeps a ~180° arc of straight rays (``radius_divider`` apart, up to
   ``cone_vision`` cells long) across the cost-to-target field. Each ray stops at
   the first wall (line-of-sight is blocked by obstacles), and every visible cell
   along the way whose cost-to-target is lower than the agent's current cell
   becomes a candidate "far pixel". A weighted random draw that **favours the
   longest clear lines of sight** picks the waypoint the agent will head for.
   This is what produces natural, sight-line-driven, slightly wandering motion
   rather than everyone tracing the exact same geodesic.

2. **Steers toward that far pixel** (:meth:`Agent.set_dir_to_target`). Only if
   the vision scan found nothing does it fall back to a short-range neighbour
   search of the cost field; if even that fails it gives up ("lost").

3. **Moves** a fixed step, deposits **occupancy** onto the heat map, and checks
   whether it has reached its destination.
"""
from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .simulation import Simulation

DIED_TARGET_REACHED = 0
DIED_TARGET_GONE = 1
DIED_LOST = 2


class Agent:
    def __init__(self, sim: "Simulation"):
        self.sim = sim
        self.active = False
        self.origin = -1
        self.target = -1
        self.px = 0.0
        self.py = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.speed = sim.speed
        self.age = 0
        self.far_px = -1
        self.far_py = -1
        self.group = 0
        self.trace: list[tuple[float, float]] = []
        self.record_trace = False

    # --------------------------------------------------------------- lifecycle
    def die(self, reason: int) -> None:
        self.active = False
        self.far_px = -1
        self.far_py = -1
        self.target = -1
        self.origin = -1
        self.age = 0

    def renew(self) -> bool:
        """Assign a fresh origin/destination trip by weighted draw, and place the
        agent at the chosen origin. Returns False if no valid trip exists."""
        sim = self.sim
        assigned = sim.draw_trip()
        if assigned is None:
            return False
        o, d = assigned
        grid = sim.grid
        self.origin = o
        self.target = d
        self.group = sim.ods[o].group
        self.px = (sim.ods[o].x - grid.sx) / grid.gridsize
        self.py = (sim.ods[o].y - grid.sy) / grid.gridsize
        self.vx = 0.0
        self.vy = 0.0
        self.far_px = -1
        self.far_py = -1
        self.age = 0
        self.active = True
        self.record_trace = sim.rng.random() * 100 < sim.trace_percent
        self.trace = [(self.px, self.py)] if self.record_trace else []
        return True

    # ------------------------------------------------------------------ vision
    def _cost_here(self, cost) -> float:
        i = min(max(int(self.px), 0), cost.shape[0] - 1)
        j = min(max(int(self.py), 0), cost.shape[1] - 1)
        return cost[i, j]

    def vision_scan(self) -> None:
        """Scan the flood-fill along a cone of straight sight-lines and choose a
        far waypoint, weighted towards the longest clear line of sight."""
        sim = self.sim
        grid = sim.grid
        self.far_px = -1
        self.far_py = -1
        cost = grid.cost_field(self.target)
        if cost is None:
            return
        nx, ny = grid.nx, grid.ny
        if not (0 <= self.px < nx and 0 <= self.py < ny):
            return

        curr_d = self._cost_here(cost)
        if not math.isfinite(curr_d):
            return

        # Initial look direction from current velocity (matches the original).
        angle = 0.0
        if self.vy != 0:
            angle = -math.atan(self.vx / self.vy)
        if self.vy < 0:
            angle = math.pi + math.atan(self.vx / -self.vy)

        candidates: list[tuple[int, int]] = []
        weights: list[float] = []

        step = sim.radius_divider
        j_angle = angle
        end = math.pi + angle + step
        while j_angle < end:
            cos_j = math.cos(j_angle)
            sin_j = math.sin(j_angle)
            for i in range(1, sim.cone_vision):
                x = i * cos_j
                y = i * sin_j
                pixx = int(self.px + x)
                pixy = int(self.py + y)
                if pixx < 0 or pixx >= nx or pixy < 0 or pixy >= ny:
                    break
                if not grid.walkable[pixx, pixy]:
                    break  # line of sight blocked by a wall
                d = cost[pixx, pixy]
                if math.isfinite(d) and d >= 0 and d < curr_d:
                    candidates.append((pixx, pixy))
                    weights.append(x * x + y * y)  # favour longer sight-lines
            j_angle += step

        idx = sim.weighted_index(weights)
        if idx != -1:
            self.far_px, self.far_py = candidates[idx]

    # ------------------------------------------------------------- steering
    def set_dir_to_target(self) -> None:
        """Set velocity toward the far pixel; fall back to a local neighbour
        search of the cost field, else give up."""
        sim = self.sim
        grid = sim.grid
        cost = grid.cost_field(self.target)
        if cost is None:
            return
        self.vx = 0.0
        self.vy = 0.0

        dx = 0.0
        dy = 0.0
        if self.far_px != -1 and self.far_py != -1:
            dx = self.far_px - self.px
            dy = self.far_py - self.py
            mag = math.hypot(dx, dy)
            if mag > 0:
                self.vx += dx / mag
                self.vy += dy / mag
                return

        # Fallback: inspect the cost field in a growing neighbourhood and head to
        # the cheapest cell found (agents otherwise get stuck against walls).
        min_d = math.inf
        mx = my = -1
        nx, ny = grid.nx, grid.ny
        for depth in range(1, 4):
            for kk in range(-depth, depth + 1):
                xxx = int(self.px) + kk
                if xxx < 0 or xxx >= nx:
                    continue
                for kkk in range(-depth, depth + 1):
                    if kk == 0 and kkk == 0:
                        continue
                    yyy = int(self.py) + kkk
                    if yyy < 0 or yyy >= ny:
                        continue
                    d = cost[xxx, yyy]
                    if math.isfinite(d) and 0 < d < min_d:
                        min_d = d
                        mx, my = xxx, yyy
        if mx != -1:
            dx = mx - self.px
            dy = my - self.py
            mag = math.hypot(dx, dy)
            if mag > 0:
                self.vx += dx / mag
                self.vy += dy / mag
        else:
            self.die(DIED_LOST)

    def move(self) -> None:
        grid = self.sim.grid
        mag = math.hypot(self.vx, self.vy)
        if mag > 0:
            self.px += self.vx / mag * self.speed
            self.py += self.vy / mag * self.speed
        self.px = min(max(self.px, 0), grid.nx - 1)
        self.py = min(max(self.py, 0), grid.ny - 1)
        if self.record_trace:
            self.trace.append((self.px, self.py))
        self.age += 1

    def mark_occupancy(self) -> None:
        sim = self.sim
        grid = sim.grid
        if self.age < 2:
            return
        xx = min(max(int(self.px), 0), grid.nx - 1)
        yy = min(max(int(self.py), 0), grid.ny - 1)
        if not grid.walkable[xx, yy]:
            return
        grid.add_occupancy(xx, yy, 1.0)
        if sim.blur_occupancy and 0 < xx < grid.nx - 1 and 0 < yy < grid.ny - 1:
            rex = self.px - xx
            b = sim.blur_decay
            grid.occupancy[xx - 1, yy] += (1.0 - rex) * b
            grid.occupancy[xx + 1, yy] += rex * b
            grid.occupancy[xx, yy - 1] += (1.0 - rex) * b
            grid.occupancy[xx, yy + 1] += (1.0 - rex) * b

    def target_check(self) -> None:
        sim = self.sim
        grid = sim.grid
        if self.target < 0 or self.target >= len(sim.ods) or sim.ods[self.target] is None:
            self.die(DIED_TARGET_GONE)
            self.renew()
            return
        od = sim.ods[self.target]
        odpx = grid.cell_x(od.x)
        odpy = grid.cell_y(od.y)
        if abs(self.px - odpx) < 3 and abs(self.py - odpy) < 3:
            self.die(DIED_TARGET_REACHED)
            self.renew()

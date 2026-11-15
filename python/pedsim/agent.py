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
        #: OD this walker first set out from; trips restart there when the
        #: simulation has ``respawn_at_origin`` on. ``die`` leaves it alone.
        self.home = -1
        self.origin = -1
        self.target = -1
        #: Which grid this walker is on: 0 is the scene's own grid, k > 0 the
        #: k-th fine patch of a nested scene (see :mod:`pedsim.nested`).
        self.level = 0
        self.px = 0.0
        self.py = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.speed = sim.speed
        self.age = 0
        self.far_px = -1
        self.far_py = -1
        self.group = 0
        self.trace = None  # optional pedsim.traces.Trace
        self.pclass = ""
        self.task = ""
        self.load_kg = 0.0
        self.speed_factor = 1.0
        self.day_minutes_used = 0.0

    @property
    def grid(self):
        """The grid this walker is on."""
        if self.level == 0:
            return self.sim.grid
        return self.sim.patches[self.level - 1].grid

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
        if getattr(sim, "tasks_enabled", False) and getattr(sim, "task_model", None) is not None:
            plan = sim.task_model.next_for(sim, self)
            if plan is None:
                return False
            o, d = plan.origin, plan.dest
            self.task = plan.task_id
            self.load_kg = plan.load_kg
        else:
            assigned = None
            if getattr(sim, "respawn_at_origin", False) and self.home >= 0:
                # back where this walker set out from, off to a new destination
                d = sim.draw_destination(self.home)
                if d is not None:
                    assigned = (self.home, d)
            if assigned is None:
                assigned = sim.draw_trip()
            if assigned is None:
                return False
            o, d = assigned
        self.origin = o
        self.home = o
        self.target = d
        self.group = sim.ods[o].group
        self._apply_class_speed()
        if sim.patches:
            from .nested import level_at
            self.level = level_at(sim, sim.ods[o].x, sim.ods[o].y)
        grid = self.grid
        self.px = (sim.ods[o].x - grid.sx) / grid.gridsize
        self.py = (sim.ods[o].y - grid.sy) / grid.gridsize
        self.vx = 0.0
        self.vy = 0.0
        self.far_px = -1
        self.far_py = -1
        self.age = 0
        self.active = True
        # Deactivate any previous trace and (optionally) start a new one.
        if self.trace is not None:
            self.trace.active = False
        self.trace = None
        if sim.record_traces:
            from .traces import Trace

            draw = sim.rng.random() * 100 < sim.trace_percent
            self.trace = Trace(self, draw=draw)
            sim.traces.append(self.trace)
            self.trace.update(sim)
        return True

    def _apply_class_speed(self) -> None:
        """Speed = scene speed × class factor × load factor (A8)."""
        from .population import load_factor

        sim = self.sim
        k = getattr(sim, "load_k", 0.2)
        max_load = 20.0
        if getattr(sim, "population", None) is not None and self.pclass:
            spec = sim.population.get(self.pclass)
            if spec is not None:
                self.speed_factor = spec.speed_factor
                max_load = spec.max_load_kg
        factor = load_factor(self.load_kg, max_load, k=k)
        self.speed = sim.speed * self.speed_factor * factor

    # ------------------------------------------------------------------ vision
    def _cost_here(self, cost) -> float:
        i = min(max(int(self.px), 0), cost.shape[0] - 1)
        j = min(max(int(self.py), 0), cost.shape[1] - 1)
        return cost[i, j]

    def vision_scan(self) -> None:
        """Scan the flood-fill along a cone of straight sight-lines and choose a
        far waypoint, weighted towards the longest clear line of sight."""
        sim = self.sim
        grid = self.grid
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
        accumulate = sim.accumulate_visibility
        # nested lists: same values as the arrays, far cheaper to read per cell
        penalty = grid.penalty_rows()
        walk = grid.walkable_rows()
        rows = grid.cost_rows(self.target)
        isfinite = math.isfinite

        step = sim.radius_divider
        j_angle = angle
        end = math.pi + angle + step
        while j_angle < end:
            cos_j = math.cos(j_angle)
            sin_j = math.sin(j_angle)
            # cost of the rough going crossed so far along this sight-line
            acc = 0.0
            for i in range(1, sim.cone_vision):
                x = i * cos_j
                y = i * sin_j
                pixx = int(self.px + x)
                pixy = int(self.py + y)
                if pixx < 0 or pixx >= nx or pixy < 0 or pixy >= ny:
                    break
                # Accumulate sight-line visibility (incl. the wall cell we stop
                # at) -- this feeds the facade-visibility analysis.
                if accumulate:
                    grid.add_visibility(pixx, pixy, self.group)
                if not walk[pixx][pixy]:
                    break  # line of sight blocked by a wall
                if penalty is not None:
                    acc += penalty[pixx][pixy]
                d = rows[pixx][pixy]
                # Walking straight here costs the going along the way; only
                # worth it if the cost saved covers it. With no rough ground
                # ``acc`` is 0 and this is the original ``d < curr_d`` test.
                if isfinite(d) and d >= 0 and d + acc < curr_d:
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
        grid = self.grid
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
        grid = self.grid
        mag = math.hypot(self.vx, self.vy)
        if mag > 0:
            self.px += self.vx / mag * self.speed
            self.py += self.vy / mag * self.speed
        self.px = min(max(self.px, 0), grid.nx - 1)
        self.py = min(max(self.py, 0), grid.ny - 1)
        self.age += 1

    def mark_occupancy(self) -> None:
        sim = self.sim
        grid = self.grid
        if self.age < 2:
            return
        xx = min(max(int(self.px), 0), grid.nx - 1)
        yy = min(max(int(self.py), 0), grid.ny - 1)
        if not grid.walkable[xx, yy]:
            return
        grid.add_occupancy(xx, yy, 1.0)
        if hasattr(sim, "note_category"):
            sim.note_category(xx, yy, self)
        if sim.blur_occupancy and 0 < xx < grid.nx - 1 and 0 < yy < grid.ny - 1:
            rex = self.px - xx
            b = sim.blur_decay
            grid.occupancy[xx - 1, yy] += (1.0 - rex) * b
            grid.occupancy[xx + 1, yy] += rex * b
            grid.occupancy[xx, yy - 1] += (1.0 - rex) * b
            grid.occupancy[xx, yy + 1] += (1.0 - rex) * b

    def target_check(self) -> None:
        sim = self.sim
        grid = self.grid
        if self.target < 0 or self.target >= len(sim.ods) or sim.ods[self.target] is None:
            self.die(DIED_TARGET_GONE)
            self.renew()
            return
        od = sim.ods[self.target]
        if sim.patches:
            from .nested import level_at
            if level_at(sim, od.x, od.y) != self.level:
                return          # the place is on another grid: not there yet
        odpx = grid.cell_x(od.x)
        odpy = grid.cell_y(od.y)
        if abs(self.px - odpx) < 3 and abs(self.py - odpy) < 3:
            self.die(DIED_TARGET_REACHED)
            self.renew()

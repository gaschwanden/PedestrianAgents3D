"""Daily tasks: a catalogue, a trip chain, and a record of demand that could
not be met because nothing was in range.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .rivers import Season
from .timing import cost_to_minutes, metres_to_minutes


@dataclass
class Task:
    id: str
    description: str
    destination_kind: str
    eligible: List[str]
    frequency: str = ""
    load_kg: float = 0.0
    load_return_kg: float = 0.0
    season_note: str = ""
    source: str = ""
    confidence: str = "assumption"
    multi_day: bool = False

    @property
    def assumption(self) -> bool:
        return (not self.source) or self.confidence == "assumption"


def load_tasks(path: Optional[str] = None) -> List[Task]:
    from .scenario import config_path, load_yaml

    path = path or config_path("tasks.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    data = load_yaml(path)
    tasks = []
    for entry in data.get("tasks", []):
        tasks.append(Task(
            id=str(entry["id"]),
            description=str(entry.get("description", "")),
            destination_kind=str(entry.get("destination_kind", entry.get("kind", ""))),
            eligible=[str(c) for c in entry.get("eligible", [])],
            frequency=str(entry.get("frequency", "")),
            load_kg=float(entry.get("load_kg", 0) or 0),
            load_return_kg=float(entry.get("load_return_kg", entry.get("load_kg", 0)) or 0),
            season_note=str(entry.get("season_note", "")),
            source=str(entry.get("source", "")),
            confidence=str(entry.get("confidence", "assumption")),
            multi_day=bool(entry.get("multi_day", False)),
        ))
    if not tasks:
        raise ValueError(f"{path} contains no tasks")
    return tasks


def kind_matches(od_kind: str, wanted: str) -> bool:
    """``resource`` matches ``resource:plants``. A qualified kind matches only itself."""
    if not wanted or not od_kind:
        return False
    if od_kind == wanted:
        return True
    if ":" not in wanted:
        return od_kind.split(":", 1)[0] == wanted
    return False


def trip_minutes(sim, origin_idx: int, dest_idx: int, speed_factor: float = 1.0) -> float:
    """Walking minutes between two ODs, from the cost field when there is one."""
    grid = sim.grid
    dest = sim.ods[dest_idx]
    origin = sim.ods[origin_idx]
    if dest is None or origin is None:
        return math.inf
    cost = grid.cost_field(dest_idx)
    if cost is not None:
        i = min(max(grid.cell_x(origin.x), 0), grid.nx - 1)
        j = min(max(grid.cell_y(origin.y), 0), grid.ny - 1)
        value = float(cost[i, j])
        if math.isfinite(value):
            if grid.elevation is not None and grid.terrain_cost is not None:
                minutes = cost_to_minutes(value, grid.terrain_cost.base_speed)
            else:
                steps = value - 1.0 if value >= 1.0 else value
                minutes = metres_to_minutes(max(steps, 0.0) * grid.gridsize, 1.0)
            return minutes / max(speed_factor, 1e-3)
    metres = math.hypot(dest.x - origin.x, dest.y - origin.y)
    return metres_to_minutes(metres, speed_factor)


def cost_metres(sim, origin_idx: int, dest_idx: int) -> float:
    """Travel distance in metres. Dijkstra cost is converted; a flood fill is
    counted as steps × cell size. Euclidean is the fallback."""
    grid = sim.grid
    dest = sim.ods[dest_idx]
    origin = sim.ods[origin_idx]
    if dest is None or origin is None:
        return math.inf
    eucl = math.hypot(dest.x - origin.x, dest.y - origin.y)
    cost = grid.cost_field(dest_idx)
    if cost is None:
        return eucl
    i = min(max(grid.cell_x(origin.x), 0), grid.nx - 1)
    j = min(max(grid.cell_y(origin.y), 0), grid.ny - 1)
    value = float(cost[i, j])
    if not math.isfinite(value):
        return math.inf
    if grid.elevation is not None and grid.terrain_cost is not None:
        return value * float(grid.terrain_cost.base_speed)
    steps = value - 1.0 if value >= 1.0 else value
    return max(steps, 0.0) * grid.gridsize


@dataclass
class TripPlan:
    task_id: str
    origin: int
    dest: int
    load_kg: float
    minutes: float


@dataclass
class TaskModel:
    tasks: List[Task]
    allocation: str = "by_class"     # by_class / uniform
    k_nearest: int = 3
    unmet: List[dict] = field(default_factory=list)
    log: List[dict] = field(default_factory=list)

    def by_id(self, task_id: str) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def eligible(self, task: Task, class_id: str) -> bool:
        if self.allocation == "uniform" or not class_id:
            return True
        if not task.eligible:
            return True
        return class_id in task.eligible

    def _candidates(self, sim, origin_idx: int, task: Task, max_range_m: float) -> List[tuple]:
        """(metres, od_index) within range, nearest first."""
        found = []
        season_dry = getattr(sim, "season", None) is Season.DRY
        for idx, od in enumerate(sim.ods):
            if od is None or idx == origin_idx:
                continue
            if not kind_matches(od.kind, task.destination_kind):
                continue
            if not sim.research.phase_allows(od.phase_ids):
                continue
            if task.id == "water" and season_dry and "stream" in od.tags:
                if any(other is not None and "cistern" in other.tags for other in sim.ods):
                    continue
            metres = cost_metres(sim, origin_idx, idx)
            if metres <= max_range_m:
                found.append((metres, idx))
        found.sort()
        return found[: self.k_nearest]

    def _home_index(self, sim, agent) -> Optional[int]:
        if agent.origin >= 0 and sim.ods[agent.origin] is not None:
            od = sim.ods[agent.origin]
            if od.kind in ("house", "site", "gate"):
                return agent.origin
        for idx, od in enumerate(sim.ods):
            if od is None:
                continue
            if od.kind == "house" and sim.research.phase_allows(od.phase_ids):
                return idx
        for idx, od in enumerate(sim.ods):
            if od is not None and od.origin_weight > 0:
                return idx
        return None

    def max_range(self, sim, agent) -> float:
        if self.allocation == "uniform":
            return 1.0e9
        pop = getattr(sim, "population", None)
        if pop is not None and agent.pclass:
            spec = pop.get(agent.pclass)
            if spec is not None:
                return spec.max_range_m
        return 30_000.0

    def budget_minutes(self, sim) -> float:
        return float(sim.research.daylight_minutes) * float(sim.research.active_share)

    def next_for(self, sim, agent) -> Optional[TripPlan]:
        """Pick a task chain that still fits in the day's remaining minutes.

        Returns None when the budget is spent or every task is out of range.
        Out-of-range tasks are logged as unmet demand and are not assigned.
        """
        remaining = self.budget_minutes(sim) - float(agent.day_minutes_used)
        if remaining <= 1.0:
            return None
        home = self._home_index(sim, agent)
        if home is None:
            return None
        weights = sim.research.task_weights or {}
        order = list(self.tasks)
        sim.rng.shuffle(order)
        for task in order:
            if task.id == "home":
                continue
            if not self.eligible(task, agent.pclass):
                continue
            weight = float(weights.get(task.id, 1.0))
            if weight <= 0:
                continue
            if sim.rng.random() > min(1.0, weight):
                continue
            max_range = self.max_range(sim, agent)
            near = self._candidates(sim, home, task, max_range)
            if not near:
                self.unmet.append({
                    "task": task.id, "pclass": agent.pclass,
                    "reason": "unmet demand", "range_m": max_range,
                })
                continue
            _metres, dest = near[int(sim.rng.integers(0, len(near)))]
            minutes = trip_minutes(sim, home, dest, agent.speed_factor or 1.0)
            if minutes > remaining and not task.multi_day:
                self.unmet.append({
                    "task": task.id, "pclass": agent.pclass,
                    "reason": "over budget", "minutes": minutes,
                })
                continue
            agent.day_minutes_used += min(minutes, remaining) if math.isfinite(minutes) else 0.0
            agent.task = task.id
            agent.load_kg = task.load_kg
            self.log.append({
                "task": task.id, "pclass": agent.pclass,
                "minutes": minutes, "load_kg": task.load_kg,
            })
            return TripPlan(task.id, home, dest, task.load_kg,
                            minutes if math.isfinite(minutes) else 0.0)
        return None


def day_summary(model: TaskModel) -> Dict[str, float]:
    """Minutes walked and unmet counts, for the metrics table."""
    by_class: Dict[str, List[float]] = {}
    for row in model.log:
        by_class.setdefault(row["pclass"] or "all", []).append(float(row["minutes"]))
    summary = {
        "tasks_done": float(len(model.log)),
        "unmet": float(len(model.unmet)),
    }
    for key, values in by_class.items():
        summary[f"minutes_{key}"] = float(sum(values))
    return summary

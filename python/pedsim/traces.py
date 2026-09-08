"""Agent trajectory traces (port of the Java ``Trace`` class).

Each trace records the world-space path of one agent while it is active, ages
over time, and fades out. Traces can be coloured by the origin OD group
(``display_tracesO``) or with the default blue palette (``display_traces``).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

_GROUP_RGB = {
    0: (255, 0, 0),
    1: (0, 255, 0),
    2: (0, 0, 255),
}
_DEFAULT_RGB = (0, 50, 200)


class Trace:
    def __init__(self, agent, draw: bool, max_age: int = 800):
        self.agent = agent
        self.points: List[Tuple[float, float, float]] = []
        self.age = 0
        self.max_age = max_age
        self.active = True
        self.draw_me = draw
        self.start_od = agent.origin
        self.end_od = agent.target
        self.start_group = agent.group

    def add_pos(self, x: float, y: float, z: float = 0.0) -> None:
        self.points.append((x, y, z))

    def update(self, sim) -> None:
        if self.active and self.agent.active:
            g = sim.grid
            self.add_pos(
                self.agent.px * g.gridsize + g.sx,
                self.agent.py * g.gridsize + g.sy,
                0.0,
            )
        self.age += 1
        if self.age > self.max_age:
            self.active = False

    def color(self, by_group: bool) -> Tuple[float, float, float, float]:
        """Return an RGBA (0..1) colour that fades with age."""
        fade = max(0.0, (self.max_age - self.age) / self.max_age)
        if by_group:
            base = _GROUP_RGB.get(self.start_group, (150, 150, 150))
        else:
            base = _DEFAULT_RGB
        return (base[0] / 255.0, base[1] / 255.0, base[2] / 255.0, fade)

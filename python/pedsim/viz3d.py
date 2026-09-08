"""3D visualisation -- the closest matplotlib analogue of the original OpenGL
view: terrain surface, extruded buildings, ground obstacles, ODs, agents and
traces, with a rotatable camera and an optional spinning animation.

This restores the "3D" character of the Java sketch (which rendered extruded
buildings in a tilt/rotate/zoom camera) while adding real terrain relief, which
the flat-ground original never had.
"""
from __future__ import annotations

from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection  # noqa: E402

from .building import Building  # noqa: E402
from .simulation import Simulation  # noqa: E402

_GROUP_COLORS = ["#ff9600", "#39d353", "#4aa3ff", "#ff5d5d", "#c77dff"]
_LAYER_COLORS = {
    "WATERBODY": "#4aa3ff",
    "STREETS": "#888888",
    "OBSTACLES_LOW": "#5a6b3b",
    "OBSTACLES_HIGH": "#6b5a3b",
    "PARK": "#3b6b3b",
}


def _ground_z(sim: Simulation, x: float, y: float) -> float:
    if sim.grid.topography is not None:
        return sim.grid.topography.sample(x, y)
    return 0.0


def _terrain_surface(ax, sim: Simulation) -> float:
    g = sim.grid
    xs = np.linspace(g.min_x, g.max_x, min(g.nx, 140))
    ys = np.linspace(g.min_y, g.max_y, min(g.ny, 140))
    X, Y = np.meshgrid(xs, ys)
    if g.topography is not None:
        Z = np.array([[g.topography.sample(x, y) for x in xs] for y in ys])
        ax.plot_surface(X, Y, Z, cmap="terrain", alpha=0.7, linewidth=0,
                        antialiased=True, zorder=0)
        return float(Z.max() - Z.min())
    Z = np.zeros_like(X)
    ax.plot_surface(X, Y, Z, color="#20242c", alpha=0.5, linewidth=0, zorder=0)
    return 1.0


def _extrude_building(ax, sim: Simulation, b: Building, wall_color, roof_color) -> None:
    poly = b.footprint.as_xy()
    if len(poly) < 3:
        return
    base = min(_ground_z(sim, x, y) for x, y in poly)
    top = base + max(b.height, 1.0)
    walls = []
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        walls.append([(x0, y0, base), (x1, y1, base), (x1, y1, top), (x0, y0, top)])
    ax.add_collection3d(Poly3DCollection(walls, facecolor=wall_color, edgecolor="#cbd5e1",
                                         linewidths=0.3, alpha=0.95))
    roof = [[(x, y, top) for x, y in poly]]
    ax.add_collection3d(Poly3DCollection(roof, facecolor=roof_color, edgecolor="#cbd5e1",
                                         linewidths=0.3, alpha=0.95))


def _draw_ground_polys(ax, sim: Simulation) -> None:
    for o in sim.obstacles:
        poly = o.footprint.as_xy()
        if len(poly) < 3:
            continue
        z = min(_ground_z(sim, x, y) for x, y in poly) + 0.2
        color = _LAYER_COLORS.get(o.layer, "#556")
        ax.add_collection3d(Poly3DCollection([[(x, y, z) for x, y in poly]],
                                             facecolor=color, edgecolor="none", alpha=0.6))


def _draw_base(ax, sim: Simulation, show_obstacles=True) -> float:
    g = sim.grid
    relief = _terrain_surface(ax, sim)
    if show_obstacles:
        _draw_ground_polys(ax, sim)
    for b in sim.buildings:
        _extrude_building(ax, sim, b, wall_color="#8a91a0", roof_color="#5b6270")
    # ODs
    for od in sim.ods:
        if od is None:
            continue
        z = _ground_z(sim, od.x, od.y) + 1.0
        ax.scatter([od.x], [od.y], [z], c=_GROUP_COLORS[od.group % len(_GROUP_COLORS)],
                   marker="o" if od.is_source else "s", s=40, edgecolors="white",
                   linewidths=0.5, depthshade=False)
    ax.set_xlim(g.min_x, g.max_x)
    ax.set_ylim(g.min_y, g.max_y)
    ax.set_box_aspect((g.max_x - g.min_x, g.max_y - g.min_y,
                       max(relief * 4, (g.max_x - g.min_x) * 0.25)))
    ax.set_facecolor("#0d0d0f")
    ax.set_axis_off()
    return relief


def render_3d_scene(sim: Simulation, path: str, title: str = "",
                    elev: float = 40, azim: float = -60) -> str:
    fig = plt.figure(figsize=(11, 8))
    fig.patch.set_facecolor("#0d0d0f")
    ax = fig.add_subplot(111, projection="3d")
    _draw_base(ax, sim)
    ax.view_init(elev=elev, azim=azim)
    if title:
        ax.set_title(title, color="white")
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def animate_3d(sim: Simulation, steps: int, path: str, fps: int = 20,
               title: str = "", warmup: int = 0, spin: bool = True,
               elev: float = 40, azim0: float = -60) -> str:
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

    for _ in range(warmup):
        sim.step()

    fig = plt.figure(figsize=(11, 8))
    fig.patch.set_facecolor("#0d0d0f")
    ax = fig.add_subplot(111, projection="3d")
    _draw_base(ax, sim)
    if title:
        ax.set_title(title, color="white")

    scat = ax.scatter([], [], [], s=12, c="#ffb020", depthshade=False, zorder=10)

    def agent_xyz():
        xs, ys, zs, cs = [], [], [], []
        for a in sim.active_agents:
            x = sim.grid.world_x(a.px)
            y = sim.grid.world_y(a.py)
            xs.append(x); ys.append(y)
            zs.append(_ground_z(sim, x, y) + 1.5)
            cs.append(_GROUP_COLORS[a.group % len(_GROUP_COLORS)])
        return xs, ys, zs, cs

    def update(frame):
        sim.step()
        xs, ys, zs, cs = agent_xyz()
        scat._offsets3d = (xs, ys, zs)
        if cs:
            scat.set_color(cs)
        if spin:
            ax.view_init(elev=elev, azim=azim0 + frame * (360.0 / steps))
        return (scat,)

    anim = FuncAnimation(fig, update, frames=steps, blit=False, interval=1000 / fps)
    if path.lower().endswith(".gif"):
        anim.save(path, writer=PillowWriter(fps=fps))
    else:
        try:
            anim.save(path, writer=FFMpegWriter(fps=fps, bitrate=2600))
        except Exception:
            path = path.rsplit(".", 1)[0] + ".gif"
            anim.save(path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return path

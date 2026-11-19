"""Matplotlib visualisation and animation (headless-friendly).

Renders the site (topography, boundary, blocking structures, source/sink
places), the live agents, and derived layers such as the occupancy heat map and
the cost-to-destination flood-fill. Animations are written with ffmpeg (mp4) or
Pillow (gif).
"""
from __future__ import annotations

from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from .importers import ArchaeologicalSite  # noqa: E402
from .simulation import Simulation  # noqa: E402

_GROUP_COLORS = ["#ff9600", "#39d353", "#4aa3ff", "#ff5d5d", "#c77dff"]


def _extent(sim: Simulation):
    g = sim.grid
    return [g.min_x, g.max_x, g.min_y, g.max_y]


def draw_base(
    ax,
    sim: Simulation,
    site: Optional[ArchaeologicalSite] = None,
    show_topography: bool = True,
    show_walls: bool = True,
) -> None:
    """Draw the static scene (terrain + structures + OD places) onto ``ax``."""
    g = sim.grid
    ax.set_facecolor("#0d0d0f")
    ax.set_aspect("equal")
    ax.set_xlim(g.min_x, g.max_x)
    ax.set_ylim(g.min_y, g.max_y)

    _LAYER_COLORS = {
        "WATERBODY": "#274b6b",
        "STREETS": "#3a3f47",
        "OBSTACLES_LOW": "#39412b",
        "OBSTACLES_HIGH": "#4a3f2b",
        "PARK": "#2b4a2b",
    }

    if show_topography and g.elevation is not None:
        elev = g.elevation.T  # [ix,iy] -> [row=y, col=x]
        ax.imshow(elev, origin="lower", extent=_extent(sim), cmap="terrain",
                  alpha=0.85, aspect="equal")
        levels = np.linspace(np.nanmin(elev), np.nanmax(elev), 14)
        ax.contour(
            np.linspace(g.min_x, g.max_x, elev.shape[1]),
            np.linspace(g.min_y, g.max_y, elev.shape[0]),
            elev, levels=levels, colors="#00000055", linewidths=0.5,
        )

    # Site boundary.
    if sim.site_polygon:
        ax.add_patch(MplPolygon(np.array(sim.site_polygon), closed=True, fill=False,
                                edgecolor="#9aa0aa", linewidth=1.2, linestyle="--"))

    # Obstacles (coloured by DXF layer).
    for o in sim.obstacles:
        poly = o.footprint.as_xy()
        if len(poly) >= 3:
            ax.add_patch(MplPolygon(np.array(poly), closed=True,
                                    facecolor=_LAYER_COLORS.get(o.layer, "#333"),
                                    edgecolor="none", alpha=0.7))

    # Buildings.
    if show_walls:
        for b in sim.buildings:
            poly = b.footprint.as_xy()
            if len(poly) >= 3:
                ax.add_patch(MplPolygon(np.array(poly), closed=True, facecolor="#6b7280",
                                        edgecolor="#cbd5e1", linewidth=0.8, alpha=0.9))

    # Optional archaeological enclosure outlines (source/sink rings).
    if site is not None and hasattr(site, "source_sink_features"):
        for f in site.source_sink_features():
            ax.add_patch(MplPolygon(np.array(f.polygon), closed=True, fill=False,
                                    edgecolor=_GROUP_COLORS[f.group % len(_GROUP_COLORS)],
                                    linewidth=1.6))

    # OD markers: circle = source, square = sink, star = both.
    for od in sim.ods:
        color = _GROUP_COLORS[od.group % len(_GROUP_COLORS)]
        if od.is_source and od.is_sink:
            marker = "*"
        elif od.is_source:
            marker = "o"
        else:
            marker = "s"
        ax.scatter(
            [od.x], [od.y], c=color, marker=marker, s=90,
            edgecolors="white", linewidths=0.8, zorder=5,
        )


def plot_scene(
    sim: Simulation,
    site: Optional[ArchaeologicalSite] = None,
    path: Optional[str] = None,
    title: str = "",
    show_topography: bool = True,
):
    fig, ax = plt.subplots(figsize=(10, 8))
    draw_base(ax, sim, site, show_topography=show_topography)
    if title:
        ax.set_title(title, color="white")
    fig.patch.set_facecolor("#0d0d0f")
    ax.tick_params(colors="#888")
    if path:
        fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)
    return path


def plot_cost_field(sim: Simulation, target_key: int, path: str, title: str = ""):
    """Visualise a flood-fill (cost-to-destination) field as filled contours."""
    g = sim.grid
    cost = sim.grid.cost_field(target_key)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_aspect("equal")
    field = np.array(cost.T, dtype=float)
    finite = np.isfinite(field)
    masked = np.ma.array(field, mask=~finite)
    im = ax.imshow(masked, origin="lower", extent=_extent(sim), cmap="viridis", aspect="equal")
    if finite.any():
        levels = np.linspace(field[finite].min(), field[finite].max(), 25)
        ax.contour(
            np.linspace(g.min_x, g.max_x, field.shape[1]),
            np.linspace(g.min_y, g.max_y, field.shape[0]),
            masked, levels=levels, colors="#ffffff33", linewidths=0.5,
        )
    od = sim.ods[target_key]
    ax.scatter([od.x], [od.y], c="red", marker="*", s=160, edgecolors="white", zorder=5)
    fig.colorbar(im, ax=ax, label="least-effort cost to destination")
    if title:
        ax.set_title(title)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_occupancy(sim: Simulation, site: Optional[ArchaeologicalSite], path: str, title: str = ""):
    g = sim.grid
    fig, ax = plt.subplots(figsize=(10, 8))
    draw_base(ax, sim, site, show_topography=True, show_walls=True)
    occ = g.occupancy.T
    masked = np.ma.array(occ, mask=occ <= 0)
    ax.imshow(masked, origin="lower", extent=_extent(sim), cmap="hot", alpha=0.75, aspect="equal")
    if title:
        ax.set_title(title, color="white")
    fig.patch.set_facecolor("#0d0d0f")
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def plot_facade_visibility(sim: Simulation, path: str, by_group: bool = False,
                           site=None, title: str = ""):
    """Colour each building facade segment by the visibility accumulated in the
    grid cell it faces (``display_facadevisibility`` / ``...O``)."""
    import matplotlib.collections as mc

    g = sim.grid
    fig, ax = plt.subplots(figsize=(10, 8))
    draw_base(ax, sim, site, show_topography=g.elevation is not None, show_walls=False)
    segments = []
    colors = []
    maxv = max(g.max_boundary_visibility, 1e-6)
    for b in sim.buildings:
        fp = b.footprint
        for i, seg in enumerate(fp.seg_points):
            refs = fp.seg_pixrefs[i] if i < len(fp.seg_pixrefs) else []
            for j in range(len(seg) - 1):
                if j >= len(refs):
                    break
                px, py = refs[j]
                if not g.in_bounds(px, py):
                    continue
                if by_group:
                    vals = g.visibility_o[px, py]
                    r = min(1.0, vals[0] / maxv) if g.num_groups > 0 else 0
                    gg = min(1.0, vals[1] / maxv) if g.num_groups > 1 else 0
                    bb = min(1.0, vals[2] / maxv) if g.num_groups > 2 else 0
                    colors.append((r, gg, bb, 0.9))
                else:
                    v = min(1.0, g.visibility[px, py] / maxv)
                    colors.append((1.0, 1.0 - v, 1.0 - v, 0.9))
                segments.append([seg[j], seg[j + 1]])
    lc = mc.LineCollection(segments, colors=colors, linewidths=3)
    ax.add_collection(lc)
    if title:
        ax.set_title(title, color="white")
    fig.patch.set_facecolor("#0d0d0f")
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def plot_traces(sim: Simulation, path: str, by_group: bool = False, site=None,
                title: str = ""):
    """Draw agent trajectory traces (``display_traces`` / ``...O``)."""
    fig, ax = plt.subplots(figsize=(10, 8))
    draw_base(ax, sim, site, show_topography=g_has_topo(sim), show_walls=True)
    for t in sim.traces:
        if not t.draw_me or len(t.points) < 3:
            continue
        pts = np.array([(p[0], p[1]) for p in t.points])
        ax.plot(pts[:, 0], pts[:, 1], color=t.color(by_group), linewidth=1.0)
    if title:
        ax.set_title(title, color="white")
    fig.patch.set_facecolor("#0d0d0f")
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def plot_isovist(sim: Simulation, iso, path: str, site=None, title: str = ""):
    """Fill the visibility polygon computed from a viewpoint."""
    from matplotlib.patches import Polygon as MplPolygon

    fig, ax = plt.subplots(figsize=(10, 8))
    draw_base(ax, sim, site, show_topography=g_has_topo(sim), show_walls=True)
    poly = np.array(iso.polygon())
    ax.add_patch(MplPolygon(poly, closed=True, facecolor="#ffe45e", edgecolor="#ffd000",
                            alpha=0.35, zorder=3))
    ax.scatter([iso.ox], [iso.oy], c="#ffd000", marker="*", s=140,
               edgecolors="black", zorder=5)
    if title:
        ax.set_title(title, color="white")
    fig.patch.set_facecolor("#0d0d0f")
    fig.savefig(path, dpi=120, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def g_has_topo(sim: Simulation) -> bool:
    return sim.grid.elevation is not None


def animate(
    sim: Simulation,
    steps: int,
    path: str,
    site: Optional[ArchaeologicalSite] = None,
    fps: int = 20,
    trail: bool = True,
    title: str = "",
    warmup: int = 0,
):
    """Run ``steps`` ticks and write an animation to ``path`` (.mp4 or .gif)."""
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

    for _ in range(warmup):
        sim.step()

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor("#0d0d0f")
    draw_base(ax, sim, site, show_topography=True, show_walls=True)
    if title:
        ax.set_title(title, color="white")

    scat = ax.scatter([], [], s=10, c="#ffb020", edgecolors="none", zorder=6)
    occ_im = ax.imshow(
        np.ma.array(np.zeros((sim.grid.ny, sim.grid.nx)), mask=True),
        origin="lower", extent=_extent(sim), cmap="hot", alpha=0.6, aspect="equal", zorder=4,
    )

    def update(_frame):
        sim.step()
        pts = sim.agent_positions_world()
        if len(pts):
            scat.set_offsets(pts)
            colors = [
                _GROUP_COLORS[a.group % len(_GROUP_COLORS)] for a in sim.active_agents
            ]
            scat.set_color(colors)
        else:
            scat.set_offsets(np.empty((0, 2)))
        if trail:
            occ = sim.grid.occupancy.T
            occ_im.set_data(np.ma.array(occ, mask=occ <= 0))
            if sim.grid.max_occupancy > 0:
                occ_im.set_clim(0, sim.grid.max_occupancy)
        return scat, occ_im

    anim = FuncAnimation(fig, update, frames=steps, blit=False, interval=1000 / fps)

    if path.lower().endswith(".gif"):
        anim.save(path, writer=PillowWriter(fps=fps))
    else:
        try:
            anim.save(path, writer=FFMpegWriter(fps=fps, bitrate=2400))
        except Exception:
            gif = path.rsplit(".", 1)[0] + ".gif"
            anim.save(gif, writer=PillowWriter(fps=fps))
            path = gif
    plt.close(fig)
    return path

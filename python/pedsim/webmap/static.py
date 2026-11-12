"""A static map figure: density, a scale bar, a north arrow, attribution, run id.

Online basemaps via contextily are optional. With no basemap the figure is the
density itself, which is what an offline pack can produce.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple

import numpy as np


def render_static(occupancy: np.ndarray, path: str, cellsize: float,
                  run_id: str = "", attribution: str = "© OpenStreetMap contributors",
                  sites: Optional[Sequence[Tuple[float, float, str]]] = None,
                  title: str = "", dpi: int = 150) -> str:
    """Write a PNG. ``sites`` are ``(x_m, y_m, name)`` in the same frame as the grid.

    The PNG text chunk ``pedsim`` stores the attribution and the run id so a
    test (and a later reader) can recover them without OCR.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrow

    data = np.asarray(occupancy, dtype=float)
    # imshow wants row 0 at the top; flip so north is up
    shown = np.flipud(data.T)
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(shown, cmap="inferno", origin="upper",
                   extent=(0, data.shape[0] * cellsize, 0, data.shape[1] * cellsize))
    fig.colorbar(im, ax=ax, fraction=0.04, label="trips / cell / day")
    if sites:
        for x, y, name in sites:
            ax.scatter([x], [y], c="white", s=18, zorder=3)
            ax.text(x, y, "  " + name, color="white", fontsize=7, va="center")
    width = data.shape[0] * cellsize
    bar = _nice_bar(width)
    x0 = width * 0.08
    y0 = data.shape[1] * cellsize * 0.06
    ax.plot([x0, x0 + bar], [y0, y0], color="white", lw=3, solid_capstyle="butt")
    ax.text(x0, y0, f"  {bar/1000:.0f} km" if bar >= 1000 else f"  {bar:.0f} m",
            color="white", fontsize=8, va="bottom")
    nx_ = width * 0.9
    ny_ = data.shape[1] * cellsize * 0.86
    ax.add_patch(FancyArrow(nx_, ny_, 0, data.shape[1] * cellsize * 0.06,
                            width=cellsize * 0.4, head_width=cellsize * 1.2,
                            head_length=cellsize * 1.5, color="white", length_includes_head=True))
    ax.text(nx_, ny_ + data.shape[1] * cellsize * 0.08, "N", color="white",
            ha="center", fontsize=9)
    footer = f"{attribution}    {run_id}".strip()
    fig.text(0.01, 0.01, footer, fontsize=7, color="#333333")
    if title:
        ax.set_title(title)
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fig.savefig(path, dpi=dpi, metadata={"pedsim": footer, "run_id": run_id,
                                        "attribution": attribution})
    plt.close(fig)
    return path


def _nice_bar(width_m: float) -> float:
    target = width_m / 5.0
    for candidate in (50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000):
        if candidate >= target * 0.5:
            return float(candidate)
    return float(target)

"""End-to-end Göbekli Tepe demo.

Loads the synthetic site + terrain through the importers, then builds two
simulations -- one on flat ground and one that is slope-aware -- and produces:

* the rendered scene over the topography,
* the flood-fill (cost-to-destination) field, flat vs. slope-aware,
* least-effort routes for the same gate->enclosure trips, flat vs. slope-aware
  (showing agents contour around the steep ridge instead of climbing it),
* an occupancy heat map after running the crowd,
* an animation of the vision-driven agents.

Run:  python examples/run_demo.py [output_dir]
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from pedsim import Simulation, TerrainCost, load_site, load_topography  # noqa: E402
from pedsim import viz  # noqa: E402

import build_dataset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def pick_output_dir() -> str:
    if len(sys.argv) > 1:
        out = sys.argv[1]
    elif os.path.isdir("/opt/cursor/artifacts"):
        out = "/opt/cursor/artifacts"
    else:
        out = os.path.join(HERE, "out")
    os.makedirs(out, exist_ok=True)
    return out


def trace_descent(grid, key, start_world):
    """Follow the steepest descent of a cost field from a start point to the
    destination -- the ideal least-effort route the field encodes."""
    cost = grid.cost_field(key)
    i = min(max(grid.cell_x(start_world[0]), 0), grid.nx - 1)
    j = min(max(grid.cell_y(start_world[1]), 0), grid.ny - 1)
    path = [(grid.world_x(i), grid.world_y(j))]
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for _ in range(4000):
        best = cost[i, j]
        bi, bj = i, j
        for di, dj in neighbors:
            ni, nj = i + di, j + dj
            if 0 <= ni < grid.nx and 0 <= nj < grid.ny and math.isfinite(cost[ni, nj]):
                if cost[ni, nj] < best:
                    best = cost[ni, nj]
                    bi, bj = ni, nj
        if (bi, bj) == (i, j):
            break
        i, j = bi, bj
        path.append((grid.world_x(i), grid.world_y(j)))
        if best <= 0.5:
            break
    return np.array(path)


def main() -> None:
    out = pick_output_dir()

    if not os.path.exists(os.path.join(DATA, "gobekli_site.json")):
        build_dataset.main()

    site = load_site(os.path.join(DATA, "gobekli_site.json"))
    topo = load_topography(os.path.join(DATA, "gobekli_dem.asc"))
    print(f"loaded site: {len(site.features)} features, "
          f"{len(site.build_ods())} OD places; terrain bounds {topo.bounds}")

    gridsize = 3.0
    common = dict(gridsize=gridsize, num_agents=160, release_rate=12,
                  cone_vision=60, seed=7)

    # Slope-aware simulation (agents avoid the hill); exaggerate slope penalty.
    sim_topo = Simulation.from_site(
        site, topography=topo,
        terrain_cost=TerrainCost(slope_factor=7.0, impassable_slope=1.0),
        **common,
    )
    # Flat-ground control (topography ignored).
    sim_flat = Simulation.from_site(site, **common)

    # 1) Scene over topography ------------------------------------------------
    viz.plot_scene(sim_topo, site, os.path.join(out, "pedsim_scene.png"),
                   title="Göbekli Tepe (synthetic): terrain, enclosures (sinks), gates (sources)")

    # 2) Flood-fill cost field to Enclosure C, flat vs slope-aware -----------
    target = next(k for k, od in enumerate(sim_topo.ods) if od.name == "Enclosure C")
    viz.plot_cost_field(sim_flat, target, os.path.join(out, "pedsim_costfield_flat.png"),
                        title="Cost to Enclosure C — flat ground (least distance)")
    viz.plot_cost_field(sim_topo, target, os.path.join(out, "pedsim_costfield_topo.png"),
                        title="Cost to Enclosure C — slope-aware (least effort)")

    # 3) Route comparison for a few gate -> enclosure trips ------------------
    fig, ax = plt.subplots(figsize=(10, 8))
    viz.draw_base(ax, sim_topo, site, show_topography=True, show_walls=True)
    trips = [("W gate", "Enclosure C"), ("SW gate", "Enclosure A"), ("S gate", "Enclosure B")]
    for gate_name, enc_name in trips:
        gate = next(od for od in sim_topo.ods if od.name == gate_name)
        key = next(k for k, od in enumerate(sim_topo.ods) if od.name == enc_name)
        # Flat routing must share a cost field -> reuse the flat sim's field.
        fkey = next(k for k, od in enumerate(sim_flat.ods) if od.name == enc_name)
        flat_path = trace_descent(sim_flat.grid, fkey, (gate.x, gate.y))
        topo_path = trace_descent(sim_topo.grid, key, (gate.x, gate.y))
        ax.plot(flat_path[:, 0], flat_path[:, 1], color="#ff3b3b", lw=2.4,
                label="flat (over the hill)" if gate_name == "W gate" else None)
        ax.plot(topo_path[:, 0], topo_path[:, 1], color="#22e0ff", lw=2.4,
                label="slope-aware (around)" if gate_name == "W gate" else None)
    ax.legend(loc="upper right", facecolor="#222", labelcolor="white")
    ax.set_title("Least-effort routes: flat vs slope-aware", color="white")
    fig.patch.set_facecolor("#0d0d0f")
    fig.savefig(os.path.join(out, "pedsim_routes_comparison.png"), dpi=120,
                facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)

    # 4) Run the crowd and save an occupancy heat map ------------------------
    for _ in range(400):
        sim_topo.step()
    viz.plot_occupancy(sim_topo, site, os.path.join(out, "pedsim_occupancy.png"),
                       title="Pedestrian occupancy after 400 ticks (slope-aware)")
    print(f"active agents after run: {len(sim_topo.active_agents)}")

    # 5) Animation -----------------------------------------------------------
    sim_anim = Simulation.from_site(
        site, topography=topo,
        terrain_cost=TerrainCost(slope_factor=7.0, impassable_slope=1.0),
        **common,
    )
    path = viz.animate(sim_anim, steps=220, path=os.path.join(out, "pedsim_gobekli_demo.mp4"),
                       site=site, fps=20, warmup=30,
                       title="Vision-driven pedestrians on the tell (slope-aware)")
    print(f"wrote animation: {path}")
    print(f"artifacts written to: {out}")


if __name__ == "__main__":
    main()

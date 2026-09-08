"""Full-feature showcase.

Exercises every ported capability and writes artifacts:

* 3D scene render + spinning 3D animation of the crowd (the "is it 3D?" answer),
* path-overlap occupancy, facade visibility (total and per-OD-group),
* traces (default and per-group), isovist from a viewpoint,
* a live editing example (add + split a building),

on the *original* DXF scene shipped with the project, plus a 3D render of the
Göbekli Tepe topography scene.

Run:  python examples/run_features.py [output_dir]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim import (  # noqa: E402
    ANALYSIS_FACADE_VIS,
    ANALYSIS_FACADE_VIS_O,
    ANALYSIS_NONE,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ANALYSIS_TRACES_O,
    Simulation,
    TerrainCost,
    load_site,
    load_topography,
)
from pedsim import viz, viz3d  # noqa: E402

import build_dataset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT = "/workspace/text"
DATA = os.path.join(HERE, "data")


def out_dir() -> str:
    if len(sys.argv) > 1:
        d = sys.argv[1]
    elif os.path.isdir("/opt/cursor/artifacts"):
        d = "/opt/cursor/artifacts"
    else:
        d = os.path.join(HERE, "out")
    os.makedirs(d, exist_ok=True)
    return d


def dxf_scene(mode, **kw) -> Simulation:
    return Simulation.from_dxf(
        os.path.join(TEXT, "GSite.dxf"),
        os.path.join(TEXT, "GBuildings.dxf"),
        os.path.join(TEXT, "GObstacles.dxf"),
        os.path.join(TEXT, "GOD.txt"),
        gridsize=6.0, num_agents=130, release_rate=15, cone_vision=45,
        analysis_mode=mode, seed=4, **kw,
    )


def main() -> None:
    out = out_dir()

    # --- 3D static render of the original scene ----------------------------
    sim = dxf_scene(ANALYSIS_PATHOVERLAP)
    for _ in range(120):
        sim.step()
    viz3d.render_3d_scene(sim, os.path.join(out, "pedsim_dxf_3d.png"),
                          title="Original DXF scene rendered in 3D", elev=45, azim=-60)
    viz.plot_occupancy(sim, None, os.path.join(out, "pedsim_pathoverlap.png"),
                       title="Path overlap (occupancy heat map)")

    # --- facade visibility (total + by OD group) ---------------------------
    fv = dxf_scene(ANALYSIS_FACADE_VIS)
    for _ in range(140):
        fv.step()
    viz.plot_facade_visibility(fv, os.path.join(out, "pedsim_facade_visibility.png"),
                               by_group=False, title="Facade visibility")
    fvo = dxf_scene(ANALYSIS_FACADE_VIS_O)
    for _ in range(140):
        fvo.step()
    viz.plot_facade_visibility(fvo, os.path.join(out, "pedsim_facade_visibility_group.png"),
                               by_group=True, title="Facade visibility by origin group (RGB)")

    # --- traces (default + by group) ---------------------------------------
    tr = dxf_scene(ANALYSIS_TRACES)
    for _ in range(200):
        tr.step()
    viz.plot_traces(tr, os.path.join(out, "pedsim_traces.png"), by_group=False,
                    title="Agent traces")
    tro = dxf_scene(ANALYSIS_TRACES_O)
    for _ in range(200):
        tro.step()
    viz.plot_traces(tro, os.path.join(out, "pedsim_traces_group.png"), by_group=True,
                    title="Agent traces by origin group")

    # --- isovist from a source location ------------------------------------
    iso_sim = dxf_scene(ANALYSIS_NONE)
    src = next(od for od in iso_sim.ods if od is not None and od.is_source)
    iso = iso_sim.compute_isovist(src.x, src.y, ray_length=3000.0)
    viz.plot_isovist(iso_sim, iso, os.path.join(out, "pedsim_isovist.png"),
                     title=f"Isovist (visibility polygon) from a gate  [area={iso.area():.0f}]")

    # --- editing example: add + split a building ---------------------------
    ed = dxf_scene(ANALYSIS_PATHOVERLAP)
    b = ed.add_building([(250, -40), (300, -40), (300, 10), (250, 10)], height=18)
    ed.split_building(b, 240, -15, 310, -15)
    for _ in range(60):
        ed.step()
    viz3d.render_3d_scene(ed, os.path.join(out, "pedsim_edit_3d.png"),
                          title="Editing: added + split building (3D)", elev=48, azim=-50)

    # --- spinning 3D animation of the crowd --------------------------------
    anim_sim = dxf_scene(ANALYSIS_PATHOVERLAP)
    path = viz3d.animate_3d(anim_sim, steps=160,
                            path=os.path.join(out, "pedsim_dxf_3d_spin.mp4"),
                            title="Vision-driven pedestrians (3D, rotating camera)",
                            fps=20, warmup=40, spin=True, elev=42, azim0=-60)
    print("3D animation:", path)

    # --- topography scene in 3D --------------------------------------------
    if not os.path.exists(os.path.join(DATA, "gobekli_site.json")):
        build_dataset.main()
    site = load_site(os.path.join(DATA, "gobekli_site.json"))
    topo = load_topography(os.path.join(DATA, "gobekli_dem.asc"))
    tsim = Simulation.from_site(site, topography=topo,
                                terrain_cost=TerrainCost(slope_factor=7.0, impassable_slope=1.0),
                                gridsize=4.0, num_agents=120, release_rate=12,
                                cone_vision=50, seed=5)
    viz3d.render_3d_scene(tsim, os.path.join(out, "pedsim_topo_3d.png"),
                          title="Göbekli Tepe: terrain relief in 3D", elev=42, azim=-55)

    print("artifacts written to", out)


if __name__ == "__main__":
    main()

"""Launch the interactive pedsim viewer.

Interactive (opens a window; use the on-screen controls):

    python examples/run_viewer.py --scene dxf
    python examples/run_viewer.py --scene gobekli

Scripted demo (drives itself for a fixed number of frames; used for recording):

    python examples/run_viewer.py --scene dxf --demo --frames 900
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim import (  # noqa: E402
    ANALYSIS_FACADE_VIS,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ANALYSIS_TRACES_O,
    Simulation,
    TerrainCost,
    load_site,
    load_topography,
)
from pedsim.viewer import Viewer  # noqa: E402

import build_dataset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT = "/workspace/text"
DATA = os.path.join(HERE, "data")


def build_dxf_scene() -> Simulation:
    return Simulation.from_dxf(
        os.path.join(TEXT, "GSite.dxf"),
        os.path.join(TEXT, "GBuildings.dxf"),
        os.path.join(TEXT, "GObstacles.dxf"),
        os.path.join(TEXT, "GOD.txt"),
        gridsize=6.0, num_agents=160, release_rate=18, cone_vision=45,
        analysis_mode=ANALYSIS_PATHOVERLAP, seed=6,
    )


def build_gobekli_scene() -> Simulation:
    if not os.path.exists(os.path.join(DATA, "gobekli_site.json")):
        build_dataset.main()
    site = load_site(os.path.join(DATA, "gobekli_site.json"))
    topo = load_topography(os.path.join(DATA, "gobekli_dem.asc"))
    sim = Simulation.from_site(
        site, topography=topo,
        terrain_cost=TerrainCost(slope_factor=7.0, impassable_slope=1.0),
        gridsize=4.0, num_agents=150, release_rate=14, cone_vision=50,
        analysis_mode=ANALYSIS_PATHOVERLAP, seed=5,
    )
    return sim, site


def demo_script(viewer: Viewer):
    """A timeline that exercises the viewer for the recording."""
    g = viewer.sim.grid
    cx, cy = (g.min_x + g.max_x) / 2, (g.min_y + g.max_y) / 2

    def zoom(f):
        return lambda v: v._zoom(f, (v.W // 2, v.H // 2))

    def pan(dx, dy):
        def _p(v):
            v.cx += dx
            v.cy += dy
        return _p

    def mode(m):
        return lambda v: v.set_analysis_mode(m)

    def source(x, y):
        return lambda v: v.add_source(x, y, group=1)

    def sink(x, y):
        return lambda v: v.add_sink(x, y, group=2)

    def ison(x, y):
        def _i(v):
            v.isovist_follow = True
            v.isovist_at(x, y)
        return _i

    span = g.max_x - g.min_x
    # timeline in SECONDS
    return [
        (1.0, zoom(1.4)),
        (4.0, mode(ANALYSIS_TRACES)),
        (7.0, pan(span * 0.12, 0)),
        (9.5, mode(ANALYSIS_TRACES_O)),
        (12.5, source(cx - span * 0.1, cy)),
        (13.0, sink(cx + span * 0.1, cy)),
        (14.0, mode(ANALYSIS_PATHOVERLAP)),
        (17.0, mode(ANALYSIS_FACADE_VIS)),
        (20.0, ison(cx, cy)),
        (22.0, zoom(1 / 1.4)),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=["dxf", "gobekli"], default="dxf")
    ap.add_argument("--demo", action="store_true", help="run the self-driving demo")
    ap.add_argument("--frames", type=int, default=None, help="auto-quit after N frames")
    ap.add_argument("--duration", type=float, default=None,
                    help="auto-quit after N wall-clock seconds")
    ap.add_argument("--record-dir", default=None,
                    help="render one PNG per frame into this dir (offscreen)")
    ap.add_argument("--record-fps", type=int, default=25)
    args = ap.parse_args()

    site = None
    if args.scene == "gobekli":
        sim, site = build_gobekli_scene()
    else:
        sim = build_dxf_scene()

    viewer = Viewer(sim, site=site, title=f"pedsim viewer [{args.scene}]")
    script = demo_script(viewer) if args.demo else None
    viewer.run(duration=args.duration, max_frames=args.frames, script=script,
               record_dir=args.record_dir, record_fps=args.record_fps)


if __name__ == "__main__":
    main()

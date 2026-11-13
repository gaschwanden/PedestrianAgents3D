"""Command line for the research features.

    python -m pedsim.scenario --odd
    python -m pedsim run scenario.yaml
    python -m pedsim hypotheses list
    python -m pedsim hypotheses run R G --site Göbeklitepe
    python -m pedsim serve --pack goebekli
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pedsim")
    sub = parser.add_subparsers(dest="cmd")

    odd = sub.add_parser("scenario", help="scenario tools")
    odd.add_argument("--odd", action="store_true")
    odd.add_argument("--out", default="")

    run = sub.add_parser("run", help="run a scenario file")
    run.add_argument("path")
    run.add_argument("--out", default="runs")
    run.add_argument("--year", action="store_true")
    run.add_argument("--sweep-time", default="", help="WIDTH:STEP in years, e.g. 300:50")

    hyp = sub.add_parser("hypotheses", help="residential vs gathering")
    hyp.add_argument("action", choices=["list", "run"])
    hyp.add_argument("families", nargs="*")
    hyp.add_argument("--site", default="Göbeklitepe")
    hyp.add_argument("--out", default="runs/hypotheses")
    hyp.add_argument("--seeds", default="1")

    srv = sub.add_parser("serve", help="serve the field client on the local network")
    srv.add_argument("--port", type=int, default=0)
    srv.add_argument("--cert", default="", help="PEM certificate, for https")
    srv.add_argument("--key", default="", help="PEM private key, for https")
    pack = sub.add_parser("pack", help="build an offline data pack")
    pack.add_argument("action", nargs="?", default="build")
    pack.add_argument("--area", default="goebekli")
    pack.add_argument("--no-maps", action="store_true",
                      help="skip the satellite and road downloads (no network needed)")
    pack.add_argument("--save-dir", default="",
                      help="folder of desktop saves (<site>.geometry.json) to pack")

    compare = sub.add_parser("compare", help="compare two phase sets")
    compare.add_argument("--phases", nargs=2, metavar=("A", "B"))

    args = parser.parse_args(argv)
    if args.cmd == "scenario" and args.odd:
        from .scenario import render_odd, write_odd
        if args.out:
            write_odd(args.out)
            print(args.out)
        else:
            print(render_odd())
        return 0
    if args.cmd == "run":
        from .scenario import run_scenario
        result = run_scenario(args.path, out_dir=args.out)
        print(result.record["run_id"])
        if args.year:
            _year(args.path, args.out)
        if args.sweep_time:
            _sweep(args.path, args.out, args.sweep_time)
        return 0
    if args.cmd == "hypotheses":
        from .hypotheses import compare, list_families
        if args.action == "list":
            for key, text in list_families():
                print(f"{key}: {text}")
            return 0
        families = args.families or ["R", "G"]
        seeds = [int(s) for s in args.seeds.split(",")]
        compare(families, site=args.site, seeds=seeds, out_dir=args.out)
        print(os.path.join(args.out, "report.md"))
        return 0
    if args.cmd == "serve":
        from .serve import serve
        serve(port=args.port, cert=args.cert, key=args.key)
        return 0
    if args.cmd == "pack":
        from .pack import build_pack
        print(build_pack(args.area, publish_web=True, save_dir=args.save_dir,
                         maps=not args.no_maps,
                         progress=lambda m: print("  " + m, flush=True)))
        return 0
    if args.cmd == "compare":
        print("phase comparison needs a village geometry; see pedsim.phases")
        return 0
    parser.print_help()
    return 1


def _year(path: str, out: str) -> None:
    from .calendar import MONTH_NAMES, apply_month, load_calendar
    from .scenario import load_scenario, synthetic_scene, apply_scenario
    import numpy as np

    scenario = load_scenario(path)
    scenario["calendar_month"] = None
    sim = synthetic_scene(scenario)
    apply_scenario(sim, scenario)
    cal = load_calendar()
    bands = []
    for month in range(1, 13):
        apply_month(sim, month, cal)
        sim.grid.reset_analysis()
        sim.run(int(scenario["steps"]))
        bands.append(sim.grid.occupancy.copy())
    stack = np.stack(bands, axis=0)
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "density_monthly.npy"), stack)
    with open(os.path.join(out, "density_monthly_bands.txt"), "w", encoding="utf-8") as fh:
        for number, name in MONTH_NAMES.items():
            fh.write(f"{number},{name}\n")
    try:
        from .webmap.density import write_geotiff
        write_geotiff(
            os.path.join(out, "density_monthly.tif"),
            bands, (sim.grid.sx, sim.grid.sy), sim.grid.gridsize,
            [MONTH_NAMES[i] for i in range(1, 13)],
        )
    except ImportError:
        pass


def _sweep(path: str, out: str, spec: str) -> None:
    width_s, step_s = spec.split(":")
    width, step = int(width_s), int(step_s)
    from .chronology import Interval
    from .scenario import apply_scenario, load_scenario, synthetic_scene

    scenario = load_scenario(path)
    sim = synthetic_scene(scenario)
    apply_scenario(sim, scenario)
    start = sim.research.window.start_bc
    end = sim.research.window.end_bc
    labels = []
    bands = []
    cursor = start
    while cursor - width >= end:
        window_end = cursor - width
        sim.research.window = Interval(window_end, cursor)
        sim.grid.reset_analysis()
        sim.run(max(5, int(scenario["steps"]) // 4))
        bands.append(sim.grid.occupancy.copy())
        labels.append(f"{cursor}-{window_end}")
        cursor -= step
    if not bands:
        return
    import numpy as np
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "density_timeseries.npy"), np.stack(bands))
    with open(os.path.join(out, "density_timeseries_bands.txt"), "w", encoding="utf-8") as fh:
        for label in labels:
            fh.write(label + "\n")


if __name__ == "__main__":
    sys.exit(main())

"""Ready-made scenes for the Göbekli Tepe / Taş Tepeler study.

Two scales, built from the real downloaded data:

* :func:`cluster_scene` -- the whole settlement group over ~80 km. Terrain from
  Copernicus GLO-30, watercourses from HydroRIVERS, settlements from
  :mod:`pedsim.sites`, optionally de-alluviated with :mod:`pedsim.paleo`.
* :func:`village_scene` -- one settlement in detail, where walls and buildings
  are the obstacles rather than the landscape.

:func:`build_app` wires them into a :class:`~pedsim.app.TwoScaleApp` so the
viewer can start at the cluster and drill into whichever sites have a detailed
map. Sites without one are still drawn and selectable -- the interface says
there is no map rather than inventing a scene.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import geo, paleo, sites
from .app import Scale, Scene, TwoScaleApp
from .rivers import River, Season
from .simulation import Simulation
from .topography import TerrainCost, Topography

#: Default data location: ``data/raw`` at the repo root.
DATA_DIR = os.environ.get(
    "PEDSIM_DATA",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")),
)

DEM_GLOB = "Copernicus_DSM_*.tif"
RIVERS_SHP = os.path.join("HydroRIVERS_v10_eu_shp", "HydroRIVERS_v10_eu.shp")


def data_available(data_dir: str = DATA_DIR) -> bool:
    """Is the downloaded geodata present? Scenes fall back to synthetic terrain
    if not, so the viewer still runs on a fresh clone."""
    import glob

    return bool(glob.glob(os.path.join(data_dir, DEM_GLOB)))


# --------------------------------------------------------------------- cluster
def cluster_scene(data_dir: str = DATA_DIR, cellsize: float = 250.0,
                  pad_m: float = 6000.0, paleo_correct: bool = True,
                  max_rivers: int = 20, num_agents: int = 400,
                  seed: Optional[int] = 7,
                  progress=None) -> Simulation:
    """The settlement-cluster simulation.

    Parameters
    ----------
    cellsize:
        Grid resolution in metres. 250 m keeps a ~80 km landscape solvable in a
        few seconds; there is no point going below the DEM's own ~30 m anyway.
    paleo_correct:
        Strip post-10 ka valley aggradation where there is data for it (the
        Culap Suyu basin). Elsewhere the modern surface is used unchanged --
        see :mod:`pedsim.paleo` for why no honest correction exists.
    max_rivers:
        Longest reaches to keep. At this scale a "river" is really the valley
        floor you have to cross, so channels are widened accordingly.

    Notes
    -----
    Rivers are given a width of several cells: at 250 m resolution a 20 m
    channel is invisible, but crossing the Culap floodplain genuinely is a
    several-hundred-metre affair, so the widened band is the more faithful
    representation of the obstacle.
    """
    say = progress or (lambda _m: None)
    catalogue = sites.located(usable_only=True)
    bbox = sites.bounds(usable_only=True)
    frame = geo.LocalFrame.centred_on(bbox)
    b = frame.bounds_for(bbox)
    bounds = (b[0] - pad_m, b[1] - pad_m, b[2] + pad_m, b[3] + pad_m)

    if data_available(data_dir):
        import glob

        say("loading Copernicus GLO-30 terrain")
        tiles = sorted(glob.glob(os.path.join(data_dir, DEM_GLOB)))
        topo = geo.load_dem(tiles, frame, bounds, cellsize=cellsize)
        if paleo_correct:
            say("stripping post-10 ka valley fill (Culap cores)")
            topo = _apply_paleo(topo, frame)
        rivers = []
        shp = os.path.join(data_dir, RIVERS_SHP)
        if os.path.exists(shp):
            say("loading HydroRIVERS watercourses")
            chan = max(2.5 * cellsize, 300.0)
            rivers = geo.load_rivers(
                shp, frame, bbox, max_rivers=max_rivers,
                min_length_m=5000.0, clip=bounds,
                width=chan, bank_width=2.0 * chan,
                crossing_cost=5.0, attraction=0.35)
    else:
        say("no downloaded DEM found - using synthetic relief")
        topo = _synthetic_relief(bounds, cellsize)
        rivers = []

    ods = geo.site_ods(frame, catalogue)
    say(f"routing between {len(ods)} settlements")
    sim = Simulation(
        bounds=bounds, ods=ods, gridsize=cellsize,
        topography=topo,
        # a long-distance traveller contours more than a villager: steep ground
        # is worth a real detour when the journey is tens of kilometres
        terrain_cost=TerrainCost(slope_factor=4.5, impassable_slope=0.9),
        rivers=rivers, season=Season.NORMAL,
        num_agents=num_agents, release_rate=8, speed=1.2,
        cone_vision=60, num_groups=3, seed=seed,
    )
    sim.frame = frame            # keep the georeference with the scene
    sim.scene_scale = Scale.CLUSTER
    return sim


def _apply_paleo(topo: Topography, frame: geo.LocalFrame) -> Topography:
    """De-alluviate a cluster DEM where the Culap cores constrain it."""
    nx, ny = topo.elevation.shape
    xs = topo.x0 + np.arange(nx) * topo.cellsize
    ys = topo.y0 + np.arange(ny) * topo.cellsize
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    east, north = frame.to_projected(X, Y)
    corrected, _unc = paleo.correct_dem(topo.elevation, east, north)
    return Topography(corrected, topo.x0, topo.y0, topo.cellsize)


def _synthetic_relief(bounds, cellsize: float) -> Topography:
    """Stand-in relief so the cluster scene still runs without the downloads."""
    min_x, min_y, max_x, max_y = bounds
    nx = max(2, int((max_x - min_x) / cellsize))
    ny = max(2, int((max_y - min_y) / cellsize))
    xs = np.linspace(0.0, 1.0, nx)[:, None]
    ys = np.linspace(0.0, 1.0, ny)[None, :]
    elev = (600.0 + 180.0 * np.sin(3.1 * xs) * np.cos(2.7 * ys)
            + 60.0 * np.sin(9.0 * xs + 2.0 * ys))
    return Topography(elev, min_x, min_y, cellsize)


# --------------------------------------------------------------------- village
def village_scene(site_name: str, data_dir: str = DATA_DIR,
                  extent_m: float = 1200.0, cellsize: float = 2.0,
                  num_agents: int = 250, seed: Optional[int] = 3,
                  progress=None) -> Simulation:
    """A single settlement at village scale.

    The terrain is a high-resolution crop of the same DEM around the site, which
    is honest but nearly flat at this extent -- at village scale the obstacles
    that matter are walls and buildings, imported from a plan or drawn in. The
    scene therefore starts with the site boundary and a ring of gate ODs, ready
    for a wall plan to be laid over it.
    """
    say = progress or (lambda _m: None)
    site = sites.find(site_name)
    if not site.usable:
        raise ValueError(f"{site.name} has no usable coordinate "
                         f"({site.confidence.value}) -- cannot build a village scene")
    frame = geo.LocalFrame(site.lat, site.lon)
    half = extent_m / 2.0
    bounds = (-half, -half, half, half)

    if data_available(data_dir):
        import glob

        say(f"cropping terrain around {site.name}")
        tiles = sorted(glob.glob(os.path.join(data_dir, DEM_GLOB)))
        topo = geo.load_dem(tiles, frame, bounds, cellsize=cellsize)
    else:
        topo = _synthetic_relief(bounds, cellsize)

    # Gates on the perimeter: a village's traffic enters from the landscape, so
    # the cluster-scale routes have somewhere to arrive.
    from .od import OD

    r = half * 0.86
    ods = []
    for i, ang in enumerate(np.linspace(0.0, 2.0 * np.pi, 7)[:-1]):
        ods.append(OD(float(r * np.cos(ang)), float(r * np.sin(ang)),
                      group=i % 3, origin_weight=1.0, dest_weight=1.0,
                      name=f"gate {i + 1}"))
    ods.append(OD(0.0, 0.0, group=0, origin_weight=0.4, dest_weight=1.5,
                  name="centre"))

    sim = Simulation(
        bounds=bounds, ods=ods, gridsize=cellsize, topography=topo,
        terrain_cost=TerrainCost(slope_factor=3.5),
        num_agents=num_agents, release_rate=15, speed=0.5,
        num_groups=3, seed=seed,
    )
    sim.frame = frame
    sim.scene_scale = Scale.SITE
    say(f"{site.name}: {sim.grid.nx}x{sim.grid.ny} cells at {cellsize:g} m")
    return sim


# ------------------------------------------------------------------------ app
def build_app(data_dir: str = DATA_DIR, save_dir: str = ".",
              detail_sites: Optional[List[str]] = None,
              progress=None, **cluster_kw) -> TwoScaleApp:
    """Assemble the two-scale application.

    ``detail_sites`` names the settlements that get a village-scale scene. It
    defaults to the sites with a *published* coordinate, since a village scene
    centred on an approximate point would imply a precision the survey data
    does not support.
    """
    if detail_sites is None:
        detail_sites = [s.name for s in sites.located(usable_only=True)
                        if s.confidence.value == "published"]

    cluster = Scene(
        name="Taş Tepeler cluster", scale=Scale.CLUSTER,
        builder=lambda: cluster_scene(data_dir, progress=progress, **cluster_kw),
        description="settlement cluster: rivers and relief drive the routes",
    )
    details: Dict[str, Scene] = {}
    for name in detail_sites:
        details[name] = Scene(
            name=name, scale=Scale.SITE, site_name=name,
            builder=(lambda n=name: village_scene(n, data_dir, progress=progress)),
            description=_village_description(name),
        )
    return TwoScaleApp(cluster, details, save_dir=save_dir)


def _village_description(name: str) -> str:
    from . import maps as _maps

    if _maps.has_village_plan(name):
        src = _maps.importable(name)[0]
        return f"village scale: published plan available ({src.citation.split('.')[0]})"
    return "village scale: DEM only — no published wall plan yet"

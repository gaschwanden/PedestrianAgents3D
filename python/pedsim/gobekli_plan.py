"""Göbeklitepe, southeast hollow: the 2024 building-phase plan as a scene.

Source: Clare, L. (2024) *Documenta Praehistorica* 51, Fig. 4, "Göbeklitepe.
Plan of the southeast hollow (main excavation area) showing the (preliminary)
building phases" (drawing M. Kinzel, German Archaeological Institute,
Göbeklitepe Project 2024). The plate has a 10 m scale bar, a north arrow, the
labelled 10 m trench grid, and walls coloured by eight building phases.

This module reads that plate and turns it into a walkable scene:

* **walls** -- every pixel whose colour matches one of the eight legend colours,
  kept per phase, so a phase can be switched on and off;
* **pillars** -- the solid black blocks (T-pillars seen from above);
* **georeference** -- scale from the trench grid, north from the arrow, and one
  anchor point, see :data:`ANCHOR_LATLON`.

What it does **not** take from the plate: uncoloured stonework (walls the
authors did not assign to a phase), the pale reconstruction outlines, floors,
benches and bedrock features. Unassigned stonework is therefore walkable here.

The plate itself is not shipped. Put it at
``data/raw/plans/gobeklitepe_clare2024_fig4.png`` (RGB); the scene and the pack
then carry only the derived wall raster.

Everything marked ASSUMPTION below is a modelling choice to be replaced by the
excavators' own values: the phase dates, the anchor, the entrances.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

CITATION = ("Clare, L. (2024) Documenta Praehistorica 51, Fig. 4. Drawing: M. Kinzel, "
            "German Archaeological Institute, Göbeklitepe Project 2024.")

PLAN_FILE = os.path.join("plans", "gobeklitepe_clare2024_fig4.png")

#: Pixels per metre: the trench grid repeats every 215.5 px and every 10 m.
PX_PER_M = 21.55

#: Where the plate sits on the ground. The plate's pixel ``ANCHOR_PX`` (the
#: middle of buildings A-D) is put on the middle of the membrane roof over the
#: main excavation area, measured on Esri World Imagery. ASSUMPTION: the roof
#: is centred on the four buildings. Expect about +-10 m; two surveyed trench
#: corners would replace this with something exact.
ANCHOR_PX = (622.0, 1065.0)
ANCHOR_LATLON = (37.22321, 38.92245)

#: Region of the plate that holds the drawing (left, top, right, bottom): the
#: legend, the title block and the scale bar lie outside it.
DRAWING_BOX = (60, 10, 1135, 1612)
LEGEND_BOX = (915, 10, 1135, 440)


@dataclass(frozen=True)
class PlanPhase:
    id: str
    name: str
    rgb: Tuple[int, int, int]      # the legend swatch on the plate
    start_bc: int
    end_bc: int
    colour: str                    # how the clients draw it


#: The legend, oldest first. The plate gives the order and the names; it gives
#: no dates. The period bounds are those of Clare (2024, Figs 26-28: PPNA
#: 9600-8700, EPPNB 8700-8200 cal BC); the MPPNB end and every split inside a
#: period are ASSUMPTIONS made only so the time slider has something to act on.
PHASES: List[PlanPhase] = [
    PlanPhase("PPNA", "PPNA", (7, 72, 167), 9600, 8700, "#0748a7"),
    PlanPhase("PPNA-EPPNB", "PPNA / EPPNB", (156, 222, 255), 8800, 8600, "#9cdeff"),
    PlanPhase("EPPNB1", "EPPNB 1", (238, 255, 13), 8700, 8450, "#eeff0d"),
    PlanPhase("EPPNB2", "EPPNB 2", (254, 160, 0), 8450, 8200, "#fea000"),
    PlanPhase("EPPNB-MPPNB", "EPPNB / MPPNB", (255, 67, 0), 8300, 8100, "#ff4300"),
    PlanPhase("MPPNB1", "MPPNB 1", (94, 255, 0), 8200, 7850, "#5eff00"),
    PlanPhase("MPPNB2", "MPPNB 2", (25, 154, 0), 7850, 7500, "#199a00"),
    PlanPhase("post-MPPNB", "after MPPNB", (192, 41, 254), 7500, 7000, "#c029fe"),
]

#: The four special buildings: centre of each on the plate (px), read from the
#: plate's own labels.
BUILDINGS: Dict[str, Tuple[float, float]] = {
    "Building A": (447.0, 1395.0),
    "Building B": (385.0, 1165.0),
    "Building C": (775.0, 1010.0),
    "Building D": (470.0, 760.0),
}


#: Openings cut through the walls so a building drawn as a closed ring can be
#: entered: ``name -> (bearing in degrees clockwise from north, width in m,
#: why)``. Every entry is an ASSUMPTION about a doorway the plate does not show.
ENTRANCES: Dict[str, Tuple[float, float, str]] = {
    # Open Archaeology 10.1515/opar-2022-0317, Fig. 6 draws a "U-stone" and a
    # passage running due south out of Building C; the phase plate shows the
    # ring closed there.
    "Building C": (180.0, 1.5, "south side, where a U-stone and entrance passage are "
                               "published (10.1515/opar-2022-0317, Fig. 6); its line "
                               "on this plate is estimated"),
}


def plan_path(data_dir: Optional[str] = None) -> str:
    from . import scenes

    return os.path.join(data_dir or scenes.DATA_DIR, PLAN_FILE)


def available(data_dir: Optional[str] = None) -> bool:
    return os.path.exists(plan_path(data_dir))


# ------------------------------------------------------------------ reading
#: How each phase looks *in the drawing*. The walls are tinted over a stone
#: texture, so they are lighter and less saturated than the legend swatches;
#: hue separates them reliably. ``(phase id, hue from, hue to, min saturation,
#: min value, max value)``, hue in degrees.
HUE_RULES = [
    ("EPPNB-MPPNB", 8, 29, 0.45, 150, 256),
    ("EPPNB2", 29, 50, 0.40, 150, 256),
    ("EPPNB1", 50, 79, 0.45, 150, 256),
    ("MPPNB1", 79, 112, 0.55, 200, 256),
    ("MPPNB2", 95, 150, 0.55, 60, 200),
    ("PPNA-EPPNB", 185, 212, 0.26, 215, 256),
    ("PPNA", 195, 225, 0.50, 90, 215),
    ("post-MPPNB", 265, 305, 0.40, 150, 256),
]


def classify(rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Phase index per pixel (-1 = none) and the pillar mask, for an RGB plate.

    A pixel belongs to a phase when its hue, saturation and brightness fall in
    that phase's row of :data:`HUE_RULES`. The pale reconstruction outlines on
    the plate are the same hues washed out toward white and fail the
    saturation test.
    """
    from scipy import ndimage

    img = rgb.astype(float)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    value = img.max(axis=2)
    low = img.min(axis=2)
    spread = value - low
    sat = np.where(value > 0, spread / np.maximum(value, 1.0), 0.0)
    safe = np.maximum(spread, 1e-9)
    hue = np.where(value == r, ((g - b) / safe) % 6.0,
                   np.where(value == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0)) * 60.0
    index = {p.id: k for k, p in enumerate(PHASES)}
    phase = np.full(value.shape, -1, dtype=int)
    for pid, h0, h1, s_min, v_min, v_max in HUE_RULES:
        hit = ((hue >= h0) & (hue < h1) & (sat >= s_min)
               & (value >= v_min) & (value < v_max) & (spread > 8))
        phase[hit & (phase == -1)] = index[pid]

    left, top, right, bottom = DRAWING_BOX
    outside = np.ones(phase.shape, dtype=bool)
    outside[top:bottom, left:right] = False
    l2, t2, r2, b2 = LEGEND_BOX
    outside[t2:b2, l2:r2] = True
    phase[outside] = -1

    # Pillars: solid black blocks at least ~0.3 m thick. Lettering, the dashed
    # trench outlines and the stone texture are thinner and do not survive.
    dark = (img.max(axis=2) < 70) & ~outside
    solid = ndimage.binary_opening(dark, structure=np.ones((6, 6), dtype=bool))
    labels, count = ndimage.label(solid)
    pillars = np.zeros(phase.shape, dtype=bool)
    if count:
        areas = ndimage.sum(solid, labels, index=np.arange(1, count + 1))
        for k, area in enumerate(areas, start=1):
            if 90 <= area <= 2500:
                pillars |= labels == k
    return phase, pillars


def to_cells(phase: np.ndarray, pillars: np.ndarray, cell_m: float,
             min_share: float = 0.22) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float, float, float]]:
    """Resample the pixel classes to square cells of ``cell_m`` metres.

    Returns ``(wall_phase, pillar)`` as ``[nx, ny]`` grids with y running north,
    and the scene bounds in metres east/north of the anchor. A cell is wall when
    at least ``min_share`` of it is coloured, and takes the phase that covers
    most of it; that keeps a thin wall continuous on a coarser grid.
    """
    h, w = phase.shape
    x_min = -ANCHOR_PX[0] / PX_PER_M
    y_max = ANCHOR_PX[1] / PX_PER_M
    width_m = w / PX_PER_M
    height_m = h / PX_PER_M
    nx = int(np.ceil(width_m / cell_m))
    ny = int(np.ceil(height_m / cell_m))
    cols = np.minimum((np.arange(w) / PX_PER_M / cell_m).astype(int), nx - 1)
    rows = np.minimum((np.arange(h) / PX_PER_M / cell_m).astype(int), ny - 1)
    cell = rows[:, None] * nx + cols[None, :]
    total = np.bincount(cell.ravel(), minlength=nx * ny).astype(float)
    counts = np.zeros((len(PHASES), nx * ny))
    for k in range(len(PHASES)):
        counts[k] = np.bincount(cell.ravel(), weights=(phase == k).ravel(), minlength=nx * ny)
    share = counts.sum(axis=0) / np.maximum(total, 1.0)
    wall = np.where(share >= min_share, counts.argmax(axis=0), -1)
    pil = np.bincount(cell.ravel(), weights=pillars.ravel(), minlength=nx * ny) \
        / np.maximum(total, 1.0) >= 0.3
    # image rows run south; grids are [x, y] with y north
    wall = wall.reshape(ny, nx)[::-1].T
    pil = pil.reshape(ny, nx)[::-1].T
    bounds = (x_min, y_max - ny * cell_m, x_min + nx * cell_m, y_max)
    return wall, pil, bounds


def local_xy(px: float, py: float) -> Tuple[float, float]:
    """Plate pixel -> metres east/north of the anchor."""
    return (px - ANCHOR_PX[0]) / PX_PER_M, (ANCHOR_PX[1] - py) / PX_PER_M


# -------------------------------------------------------------------- scene
def standing_ids(k: int) -> List[str]:
    """Phases in which a wall built in phase ``k`` stands.

    ASSUMPTION: once built, a wall stays. The plate records when walls were
    built, not when they went out of use, and the special buildings are known
    to have been altered and reduced over time, so this overstates what stood
    late on. Switch phases by hand to test other readings.
    """
    return [p.id for p in PHASES[k:]]


def plan_scene(data_dir: Optional[str] = None, cellsize: float = 0.5,
               num_agents: int = 120, seed: Optional[int] = 5, progress=None):
    """The southeast hollow as a :class:`~pedsim.simulation.Simulation`.

    Walls are blocking layers, one per building phase, which the phase
    switches and the time slider turn on and off. Places: the four special
    buildings and a gate in the middle of each side of the plate.
    """
    from PIL import Image

    from . import geo, scenes
    from .app import Scale
    from .layers import BLOCK, Layer
    from .od import OD
    from .phases import Phase
    from .simulation import Simulation
    from .topography import TerrainCost, Topography

    say = progress or (lambda _m: None)
    path = plan_path(data_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"plan image not found: {path}. Save Clare (2024) Fig. 4 there as an RGB image.")
    say("reading the Göbeklitepe phase plan")
    rgb = np.asarray(Image.open(path).convert("RGB"))
    phase, pillars = classify(rgb)
    wall, pil, bounds = to_cells(phase, pillars, cellsize)
    nx, ny = wall.shape

    frame = geo.LocalFrame(*ANCHOR_LATLON)
    data_dir = data_dir or scenes.DATA_DIR
    if scenes.data_available(data_dir):
        import glob

        tiles = sorted(glob.glob(os.path.join(data_dir, scenes.DEM_GLOB)))
        topo = geo.load_dem(tiles, frame, bounds, cellsize=cellsize)
    else:
        topo = Topography(np.zeros((nx, ny)), bounds[0] + cellsize / 2,
                          bounds[1] + cellsize / 2, cellsize)

    ods = []
    for name, (px, py) in BUILDINGS.items():
        x, y = local_xy(px, py)
        ods.append(OD(x, y, group=0, origin_weight=0.6, dest_weight=1.5,
                      name=name, kind="special"))
    min_x, min_y, max_x, max_y = bounds
    inset = 2.0
    mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    for i, (name, x, y) in enumerate((
            ("gate north", mid_x + 12.0, max_y - inset), ("gate east", max_x - 6.0, mid_y - 22.0),
            ("gate south", mid_x, min_y + 6.0), ("gate west", min_x + inset + 2.0, mid_y + 22.0))):
        ods.append(OD(x, y, group=1 + i % 2, origin_weight=1.0, dest_weight=0.6,
                      name=name, kind="gate"))

    sim = Simulation(
        bounds=bounds, ods=ods, gridsize=cellsize, topography=topo,
        terrain_cost=TerrainCost(slope_factor=scenes.VILLAGE_SLOPE_FACTOR),
        num_agents=num_agents, release_rate=8, speed=0.6, cone_vision=120,
        num_groups=3, seed=seed,
    )
    sim.respawn_at_origin = True
    sim.research.phases = [
        Phase(p.id, p.name, p.start_bc, p.end_bc, source=CITATION,
              confidence="assumption", colour=p.colour)
        for p in PHASES
    ]
    for k, p in enumerate(PHASES):
        mask = wall == k
        if not mask.any():
            continue
        layer = Layer(f"wall {p.name}", mask.astype(float), kind=BLOCK,
                      color=tuple(p.rgb), description=f"walls built in {p.name}")
        layer.phase_ids = standing_ids(k)
        sim.grid.layers.add(layer)
    if pil.any():
        layer = Layer("pillars", pil.astype(float), kind=BLOCK, color=(20, 20, 20),
                      description="T-pillars (solid black on the plate)")
        layer.phase_ids = []
        sim.grid.layers.add(layer)
    sim.entrance_notes = []
    for name, (bearing, width, why) in ENTRANCES.items():
        od = next(o for o in sim.ods if o.name == name)
        n = cut_entrance(sim, od.x, od.y, bearing, width)
        sim.entrance_notes.append(f"{name}: opening assumed on the {why} ({n} wall cells removed)")
    sim.apply_phase_filter()
    sim.frame = frame
    sim.scene_scale = Scale.SITE
    sim.position_quality = "plan anchored on the shelter roof, about ±10 m"
    say(f"Göbeklitepe plan: {nx}x{ny} cells at {cellsize:g} m, "
        f"{int((wall >= 0).sum())} wall cells, {int(pil.sum())} pillar cells")
    return sim


def cut_entrance(sim, x: float, y: float, bearing_deg: float, width_m: float,
                 clear_run_m: float = 4.0, max_m: float = 30.0) -> int:
    """Open a straight passage through the wall layers, outward from ``(x, y)``.

    Walks from the point along ``bearing_deg`` and clears every wall cell within
    ``width_m`` of that line, until ``clear_run_m`` of open ground follows the
    last wall met. Returns the number of wall cells cleared.
    """
    import math

    grid = sim.grid
    layers = [layer for layer in grid.layers if layer.kind == "block"]
    dx = math.sin(math.radians(bearing_deg))
    dy = math.cos(math.radians(bearing_deg))
    step = grid.gridsize / 2.0
    half = max(1, int(round(width_m / 2.0 / grid.gridsize)))
    cleared = 0
    met_wall = False
    free_run = 0.0
    dist = 0.0
    while dist < max_m:
        i = grid.cell_x(x + dx * dist)
        j = grid.cell_y(y + dy * dist)
        if not grid.in_bounds(i, j):
            break
        hit = False
        for di in range(-half, half + 1):
            for dj in range(-half, half + 1):
                a, b = i + di, j + dj
                if not grid.in_bounds(a, b):
                    continue
                for layer in layers:
                    if layer.data[a, b] > 0:
                        layer.data[a, b] = 0.0
                        cleared += 1
                        hit = True
        if hit:
            met_wall = True
            free_run = 0.0
        elif met_wall:
            free_run += step
            if free_run >= clear_run_m:
                break
        dist += step
    grid.layers.touch()
    return cleared


def reachability(sim) -> Dict[str, bool]:
    """Which places can be walked to from the first gate."""
    gates = [k for k, od in enumerate(sim.ods) if od is not None and od.kind == "gate"]
    if not gates:
        return {}
    start = sim.ods[gates[0]]
    i, j = sim.grid.cell_x(start.x), sim.grid.cell_y(start.y)
    out = {}
    for k, od in enumerate(sim.ods):
        if od is None:
            continue
        field = sim.grid.cost_field(k)
        out[od.name] = bool(field is not None and np.isfinite(field[i, j]))
    return out

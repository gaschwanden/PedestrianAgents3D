# pedsim — Python pedestrian simulation for ancient sites

`pedsim` is a Python re-implementation of the original Java **PedestrianAgents3D**
model, refocused on ancient cities and settlements (e.g. Göbekli Tepe). It keeps
the character of the original agents and adds two things needed for
archaeological work:

1. **Topography-aware routing** — pedestrians spend more effort walking uphill,
   so they prefer gentle, contour-following routes and avoid steep ground.
2. **Simple importers** — bring in archaeological site outlines (tagging
   structures as pedestrian *sources* and *sinks*) and terrain elevation models.

## How the model works

The simulation is grid-based, exactly like the original:

- The site is rasterised into a navigation grid. Cells inside the site boundary
  and outside any building/wall footprint are *walkable*.
- For every destination a **flood-fill cost field** is computed over the walkable
  cells. On flat ground this is the least-distance field; with topography it is a
  slope-weighted least-effort field (see below).
- **Agents do not follow a perfect shortest path.** Each tick an agent casts a
  ~180° **cone of vision** (straight sight-lines, `radius_divider` apart, up to
  `cone_vision` cells long) across the flood-fill. Each ray stops at the first
  wall, and every visible cell with a lower cost-to-destination becomes a
  candidate waypoint. A weighted random draw that **favours the longest clear
  line of sight** chooses the `far` waypoint the agent heads toward. If the scan
  finds nothing it falls back to a short local search, otherwise it gives up.
  This sight-line steering is what produces natural, slightly wandering crowds
  and realistic trodden corridors rather than everyone tracing one geodesic.
- Agents deposit an **occupancy** heat map (with decay) as they move, and are
  recycled to a new weighted origin→destination trip when they arrive.

### Topography and effort (Tobler's hiking function)

`Topography` is a georeferenced elevation raster. When one is attached, the cost
field is built with a **slope-weighted Dijkstra** search. The per-step cost uses
**Tobler's hiking function** for walking speed as a function of slope `s`
(rise/run):

```
speed = base_speed * exp(-slope_factor * |s + slope_offset|)
step_cost = horizontal_distance / speed
```

Because the cost reflects the direction actually walked, uphill steps are
expensive and steep slopes (above `impassable_slope`) are blocked entirely, so
agents contour around hills. `slope_factor` (default `3.5`, Tobler's value) tunes
how strongly hills are avoided; raise it to exaggerate the effect.

## Importers

### Archaeological site outlines (`load_site`)

A small JSON schema (or a GeoJSON `FeatureCollection`). Each feature is a polygon
with a `role`:

| role | meaning |
| --- | --- |
| `building`, `wall`, `obstacle`, `structure` | blocks movement |
| `source`, `entrance`, `gate` | pedestrians originate here (pure source) |
| `sink`, `destination` | pedestrians travel here (pure sink) |
| `source_sink`, `place`, `plaza` | both origin and destination |

Source/sink structures become OD (origin/destination) places at their centroid
(or an explicit `od` point) and, by default, are walkable so agents can reach
them. Optional `group`, `origin_weight`, `dest_weight` control trip mixing.

```json
{
  "boundary": [[-150,-150],[150,-150],[150,150],[-150,150]],
  "features": [
    {"name": "Enclosure D", "role": "sink",   "polygon": [[10,10],[30,10],[20,30]],
     "group": 0, "origin_weight": 0.2, "dest_weight": 1.0},
    {"name": "North gate",  "role": "source", "polygon": [[0,120],[6,120],[3,126]]},
    {"name": "Perimeter wall", "role": "wall", "polygon": [[..]]}
  ]
}
```

```python
from pedsim import load_site, Simulation
site = load_site("site.json")
sim = Simulation.from_site(site, gridsize=3.0)
```

### Terrain (`load_topography`)

Reads an elevation model from several formats:

- `.asc` — ESRI ASCII grid (fully georeferenced).
- `.xyz` / `.csv` — regular grid of `x y z` rows.
- `.npy` — a 2D array `[ix, iy]` (requires `bounds`).
- image heightmap (`.png`, `.tif`, ...) — grayscale (requires `bounds` and
  `z_min`/`z_max`).

```python
from pedsim import load_topography, TerrainCost, Simulation
topo = load_topography("dem.asc")
sim = Simulation.from_site(
    site, topography=topo,
    terrain_cost=TerrainCost(slope_factor=6.0),  # stronger hill avoidance
)
```

## Install & run

```bash
cd python
pip install -r requirements.txt

# Generate the synthetic Göbekli Tepe dataset and run the full demo:
python examples/build_dataset.py
python examples/run_demo.py out            # writes figures + animation to ./out

# Tests:
python tests/test_core.py                  # or: pytest tests
```

The demo produces: the scene over the terrain, the flood-fill cost field (flat
vs slope-aware), a route comparison showing agents contouring around the steep
ridge instead of climbing it, an occupancy heat map, and an mp4 animation of the
vision-driven crowd.

## Package layout

| Module | Purpose |
| --- | --- |
| `pedsim/geometry.py` | point-in-polygon, polygon rasterisation, centroids |
| `pedsim/topography.py` | elevation raster + Tobler slope-cost model |
| `pedsim/grid.py` | navigation grid, walkability, Dijkstra cost fields, occupancy |
| `pedsim/agent.py` | vision-cone steering, movement, occupancy, trip recycling |
| `pedsim/simulation.py` | scene/loop orchestration, agent pool, trip drawing |
| `pedsim/importers.py` | `load_site` (outlines) and `load_topography` (terrain) |
| `pedsim/viz.py` | matplotlib rendering, cost-field/occupancy plots, animation |
| `examples/` | synthetic dataset builder + end-to-end demo |
| `tests/` | sanity tests (routing, hill cost, importers) |

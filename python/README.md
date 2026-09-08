# pedsim — Python pedestrian simulation for ancient sites

`pedsim` is a full Python re-implementation of the Java **PedestrianAgents3D**
model, refocused on ancient cities and settlements (e.g. Göbekli Tepe). It
reproduces the original simulation feature-for-feature and adds
topography-aware routing, simple archaeological importers, and a 3D view.

## Feature parity with the Java edition

Every substantive capability of the original was ported. The table maps Java
features to their Python home.

| Java feature | Python | Notes |
| --- | --- | --- |
| Site boundary + walkability grid | `grid.NavGrid` | inside-site & outside-footprints; `openspace`/`permablocked`/`boundary`/`walkable` |
| Flood-fill distance field (BFS, random diagonal bias) | `NavGrid._bfs` | faithful, incl. the 70/30 orthogonal/diagonal bias |
| **Vision-cone steering** over the flood-fill | `agent.Agent.vision_scan` | ~180° ray fan, far-pixel weighted by longest line-of-sight, neighbour fallback |
| Agent movement / occupancy / target check / renew | `agent.Agent` | speed 0.5, arrival within 3 cells, weighted O/D redraw |
| Agent pool + gradual release | `Simulation.release_agents` | `NUM_AGENTS`, `release_rate` |
| Occupancy heat map + decay + blur | `NavGrid`, `Agent.mark_occupancy` | decay 0.99, blur 0.5 |
| Visibility / visibility-by-group fields | `NavGrid.visibility`, `visibility_o` | accumulated along sight-lines |
| OD points (weights, groups, max 50) | `od.OD` | `origin_weight`/`dest_weight`/`group` |
| Buildings (3D extruded, height, layer) | `building.Building` | |
| Obstacles (layers: LOW/HIGH/STREETS/WATERBODY/PARK) | `building.Building` | |
| Footprint gridded facade segments | `footprint.Footprint.gridded_segments` | |
| Landmarks (lines + footprints for isovist) | `landmark.Landmark` | |
| Modules (place / rotate+snap / snap-to-insertion) | `modules.ModulePrototype`, `PlacedModule` | |
| DXF import (LINE/POLYLINE/LWPOLYLINE/MESH→footprint) | `dxf.DXFHandler` | reads the shipped `text/*.dxf` |
| Analysis: path overlap | `ANALYSIS_PATHOVERLAP` + `viz.plot_occupancy` | |
| Analysis: facade visibility (+ by group) | `ANALYSIS_FACADE_VIS(_O)` + `viz.plot_facade_visibility` | |
| Analysis: traces (+ by group) | `ANALYSIS_TRACES(_O)` + `traces.Trace` + `viz.plot_traces` | |
| Isovist (2π ray clipping) | `isovist.Isovist` + `viz.plot_isovist` | |
| Edit ODs: add/move/delete/weight | `Simulation.add_od/move_od/delete_od/weight_od` | |
| Edit buildings/obstacles: add/move/delete/height/**split** | `Simulation.add_building/move_building/delete_building/set_building_height/split_building` | polygon split via line cut |
| Partial grid re-rasterisation after edits | `NavGrid.partial_update` | |
| Reset analysis | `Simulation.reset_analysis` | |
| Load/Save ODs (text) | `Simulation.load_ods/save_ods` | same `OD,x,y,z,ow,dw,group` format |
| 3D rendering (extruded buildings, camera) | `viz3d` | terrain surface + extrusions + spinning camera |
| Background thread orchestration | `Simulation.step` | flood-fill + release + traces + decay per tick |

### New beyond the original

- **Topography-aware routing** (`topography.Topography` + `TerrainCost`): a
  slope-weighted Dijkstra using **Tobler's hiking function**, so uphill costs
  effort and agents avoid/contour around hills.
- **Simple archaeological importer** (`load_site`): tag outlines as
  `source`/`sink`/`building`/`wall`.
- **Terrain relief in the 3D view** — the Java ground plane was flat.

## Is it 3D?

The Java *simulation* was always 2D on the ground plane (agents move in x/y
only); its *rendering* was 3D (extruded buildings in a tilt/rotate/zoom OpenGL
camera). `pedsim` keeps the faithful 2D simulation and provides the 3D **view**
via `pedsim.viz3d` (`render_3d_scene`, `animate_3d`): extruded buildings, ground
obstacles, ODs and agents over an optional terrain surface, with a rotating
camera animation.

## How the agents move (important)

Agents are **not** perfect shortest-path followers. Each tick an agent casts a
~180° cone of straight sight-lines across the flood-fill cost field; each ray
stops at the first wall, and every visible cell with a lower cost-to-target
becomes a candidate. A weighted random draw favouring the **longest clear line
of sight** picks the waypoint it heads for (local search fallback, else "lost").
This produces natural, wandering, sight-line-driven crowds.

## Topography (Tobler's hiking function)

With a `Topography` attached, per-step cost is `horizontal_distance / speed`
where `speed = base·exp(-slope_factor·|slope + slope_offset|)`. Steeper than
`impassable_slope` is blocked. Raise `slope_factor` to avoid hills more strongly.

## Install & run

```bash
cd python
pip install -r requirements.txt

# 1) Full feature showcase on the ORIGINAL DXF scene (text/*.dxf) + 3D:
python examples/run_features.py out
#   -> pedsim_dxf_3d.png, pedsim_dxf_3d_spin.mp4, pedsim_pathoverlap.png,
#      pedsim_facade_visibility[_group].png, pedsim_traces[_group].png,
#      pedsim_isovist.png, pedsim_edit_3d.png, pedsim_topo_3d.png

# 2) Göbekli Tepe topography demo (hill avoidance):
python examples/build_dataset.py
python examples/run_demo.py out

# Tests:
python tests/test_core.py
python tests/test_features.py     # or: pytest tests
```

### Load the original scene programmatically

```python
from pedsim import Simulation, ANALYSIS_PATHOVERLAP
sim = Simulation.from_dxf(
    "../text/GSite.dxf", "../text/GBuildings.dxf",
    "../text/GObstacles.dxf", "../text/GOD.txt",
    gridsize=4.0, analysis_mode=ANALYSIS_PATHOVERLAP,
)
sim.run(300)
```

### Archaeological site + terrain

```python
from pedsim import Simulation, load_site, load_topography, TerrainCost
site = load_site("site.json")
topo = load_topography("dem.asc")
sim = Simulation.from_site(site, topography=topo,
                           terrain_cost=TerrainCost(slope_factor=6.0))
sim.run(400)
```

## Package layout

| Module | Purpose |
| --- | --- |
| `pedsim/geometry.py` | point-in-polygon, rasterisation, area/winding, segment intersection, polygon split |
| `pedsim/dxf.py` | DXF importer (lines, polylines, meshes → footprints) |
| `pedsim/topography.py` | elevation raster + Tobler slope-cost model |
| `pedsim/grid.py` | navigation grid, BFS/Dijkstra cost fields, occupancy/visibility, partial update |
| `pedsim/footprint.py` / `building.py` | footprint (+ facade segments) and extruded building/obstacle |
| `pedsim/agent.py` | vision-cone steering, movement, occupancy, trips |
| `pedsim/traces.py` / `isovist.py` / `landmark.py` / `modules.py` | analysis + prefab features |
| `pedsim/simulation.py` | scene/loop, analysis modes, editing API, DXF/site loading, IO |
| `pedsim/viz.py` / `viz3d.py` | 2D analysis rendering + 3D rendering & animation |
| `examples/` | dataset builder, `run_demo.py` (topography), `run_features.py` (everything) |
| `tests/` | `test_core.py`, `test_features.py` |

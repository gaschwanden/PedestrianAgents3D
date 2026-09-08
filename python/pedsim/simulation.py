"""Top-level simulation: the Python counterpart of ``Scene`` + ``Grid_Thread``.

Owns the navigation grid, the origin/destination places, the buildings /
obstacles / landmarks / placed modules, the agent pool and the trace list, and
advances everything one tick at a time. It also exposes the full editing API
(add/move/delete/split buildings and obstacles, add/move/delete/weight ODs),
the analysis modes, isovist computation, and load/save.
"""
from __future__ import annotations

import json
import math
import os
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from .agent import Agent
from .building import Building
from .geometry import (
    Polygon,
    line_poly_intersections,
    polygon_bounds,
    split_polygon,
)
from .grid import NavGrid
from .isovist import Isovist
from .modules import ModulePrototype, PlacedModule
from .od import OD
from .topography import TerrainCost, Topography
from .weighted import weighted_draw

# Analysis modes (mirror Scene.display_*)
ANALYSIS_NONE = 0
ANALYSIS_PATHOVERLAP = 1
ANALYSIS_FACADE_VIS = 2
ANALYSIS_FACADE_VIS_O = 3
ANALYSIS_TRACES = 4
ANALYSIS_TRACES_O = 5

DXF_SCALER = 0.001


def _to_building(obj, kind: str, default_height: float = 15.0) -> Building:
    if isinstance(obj, Building):
        return obj
    return Building.from_polygon(obj, kind=kind, height=default_height)


class Simulation:
    def __init__(
        self,
        bounds: Tuple[float, float, float, float],
        ods: Sequence[OD],
        gridsize: float = 4.0,
        buildings: Optional[Sequence[Union[Building, Polygon]]] = None,
        obstacles: Optional[Sequence[Union[Building, Polygon]]] = None,
        site_polygon: Optional[Polygon] = None,
        topography: Optional[Topography] = None,
        terrain_cost: Optional[TerrainCost] = None,
        num_agents: int = 300,
        release_rate: int = 20,
        speed: float = 0.5,
        cone_vision: int = 100,
        radius_divider: float = math.pi / 10.0,
        blur_occupancy: bool = True,
        blur_decay: float = 0.5,
        trace_percent: float = 10.0,
        num_groups: int = 3,
        analysis_mode: int = ANALYSIS_PATHOVERLAP,
        seed: Optional[int] = None,
    ):
        self.ods: List[Optional[OD]] = list(ods)
        self.buildings: List[Building] = [_to_building(b, "building") for b in (buildings or [])]
        self.obstacles: List[Building] = [_to_building(o, "obstacle", 0.0) for o in (obstacles or [])]
        self.landmarks: list = []
        self.module_library: List[ModulePrototype] = []
        self.placed_modules: List[PlacedModule] = []
        self.insertion_points: List[Tuple[float, float]] = []
        self.site_polygon = list(site_polygon) if site_polygon else None

        self.num_agents = num_agents
        self.release_rate = release_rate
        self.speed = speed
        self.cone_vision = cone_vision
        self.radius_divider = radius_divider
        self.blur_occupancy = blur_occupancy
        self.blur_decay = blur_decay
        self.trace_percent = trace_percent
        self.num_groups = num_groups
        self.analysis_mode = analysis_mode
        self.rng = np.random.default_rng(seed)

        self.grid = NavGrid(
            bounds=bounds,
            gridsize=gridsize,
            buildings=self.buildings,
            obstacles=self.obstacles,
            site_polygon=self.site_polygon,
            topography=topography,
            terrain_cost=terrain_cost,
            num_groups=num_groups,
        )
        for b in self.buildings:
            b.footprint.gridded_segments(self.grid)

        self.agents: List[Agent] = [Agent(self) for _ in range(num_agents)]
        self.traces: list = []
        self.isovist: Optional[Isovist] = None
        self.ticks = 0
        self._build_cost_fields()

    # ------------------------------------------------- analysis-driven flags
    @property
    def record_traces(self) -> bool:
        return self.analysis_mode in (ANALYSIS_TRACES, ANALYSIS_TRACES_O)

    @property
    def accumulate_visibility(self) -> bool:
        return self.analysis_mode in (ANALYSIS_FACADE_VIS, ANALYSIS_FACADE_VIS_O)

    @property
    def agents_enabled(self) -> bool:
        return self.analysis_mode != ANALYSIS_NONE

    def set_analysis_mode(self, mode: int) -> None:
        self.analysis_mode = mode
        self.reset_analysis()

    def reset_analysis(self) -> None:
        self.grid.reset_analysis()
        self.traces = []
        for a in self.agents:
            a.die(0)

    # ---------------------------------------------------------------- factory
    @classmethod
    def from_site(cls, site, gridsize: float = 4.0, **kwargs) -> "Simulation":
        """Build from an :class:`~pedsim.importers.ArchaeologicalSite`."""
        return cls(
            bounds=site.bounds(),
            ods=site.build_ods(),
            gridsize=gridsize,
            buildings=[Building.from_polygon(p, "building") for p in site.building_polygons()],
            obstacles=[Building.from_polygon(p, "obstacle", height=0.0)
                       for p in site.obstacle_polygons()],
            site_polygon=site.boundary,
            **kwargs,
        )

    @classmethod
    def from_dxf(
        cls,
        site_path: str,
        buildings_path: Optional[str] = None,
        obstacles_path: Optional[str] = None,
        od_path: Optional[str] = None,
        gridsize: float = 4.0,
        topography: Optional[Topography] = None,
        terrain_cost: Optional[TerrainCost] = None,
        scaler: float = DXF_SCALER,
        **kwargs,
    ) -> "Simulation":
        """Load the original DXF scene (site + building meshes + obstacle
        polylines) exactly as the Java ``Scene`` did, then centre it on the
        origin and load ODs from a ``GOD.txt``-style file."""
        from .dxf import DXFHandler

        # --- site boundary -------------------------------------------------
        site_dxf = DXFHandler().import_dxf(site_path)
        site_poly: List[Tuple[float, float]] = []
        rings = site_dxf.lwpolys + site_dxf.polys
        if rings:
            ring = rings[0]
            ring.scale(scaler)
            site_poly = [(v[0], v[1]) for v in ring.vertices]
        min_x = min(p[0] for p in site_poly)
        min_y = min(p[1] for p in site_poly)
        max_x = max(p[0] for p in site_poly)
        max_y = max(p[1] for p in site_poly)

        # --- buildings (3D meshes -> footprints) ---------------------------
        buildings: List[Building] = []
        if buildings_path and os.path.exists(buildings_path):
            bdxf = DXFHandler().import_dxf(buildings_path)
            for m in bdxf.meshes:
                m.scale(scaler)
                m.set_min_max_z()
                m.build_footprint()
                if not m.footprint:
                    continue
                b = Building(kind="building", layer=m.layer, height=(m.maxz - m.minz))
                for v in m.footprint:
                    b.footprint.add_vertex(v[0], v[1], v[2])
                b.fix_vertex_order()
                buildings.append(b)

        # --- obstacles (polylines by layer) --------------------------------
        obstacles: List[Building] = []
        if obstacles_path and os.path.exists(obstacles_path):
            odxf = DXFHandler().import_dxf(obstacles_path)
            for poly in (odxf.lwpolys + odxf.polys):
                poly.scale(scaler)
                b = Building(kind="obstacle", layer=poly.layer, height=0.0)
                for v in poly.vertices:
                    b.footprint.add_vertex(v[0], v[1], v[2])
                b.fix_vertex_order()
                obstacles.append(b)

        # --- centre the scene on the origin --------------------------------
        xoffs = -(min_x + (max_x - min_x) / 2.0)
        yoffs = -(min_y + (max_y - min_y) / 2.0)
        site_poly = [(x + xoffs, y + yoffs) for x, y in site_poly]
        for b in buildings:
            b.move(xoffs, yoffs, 0)
        for b in obstacles:
            b.move(xoffs, yoffs, 0)
        bounds = (min_x + xoffs, min_y + yoffs, max_x + xoffs, max_y + yoffs)

        # --- ODs -----------------------------------------------------------
        # GOD.txt coordinates are already stored in centred scene space, so no
        # extra offset is applied here.
        ods: List[OD] = []
        if od_path and os.path.exists(od_path):
            ods = _load_ods_file(od_path, 0.0, 0.0)

        return cls(
            bounds=bounds, ods=ods, gridsize=gridsize,
            buildings=buildings, obstacles=obstacles, site_polygon=site_poly,
            topography=topography, terrain_cost=terrain_cost, **kwargs,
        )

    # ------------------------------------------------------------ cost fields
    def _active_ods(self) -> List[Tuple[int, OD]]:
        return [(k, od) for k, od in enumerate(self.ods) if od is not None]

    def _build_cost_fields(self) -> None:
        self.grid.clear_cost_fields()
        for k, od in self._active_ods():
            self.grid.compute_cost_field(k, od.x, od.y, self.rng)

    def recompute_cost_fields(self) -> None:
        self._build_cost_fields()

    def reachable_targets(self) -> int:
        return len(self._active_ods())

    # -------------------------------------------------------------- trip draw
    def draw_trip(self) -> Optional[Tuple[int, int]]:
        active = self._active_ods()
        if len(active) < 2:
            return None
        idxs = [k for k, _ in active]
        ow = [od.origin_weight for _, od in active]
        dw = [od.dest_weight for _, od in active]
        oo = weighted_draw(ow, self.rng)
        if oo == -1:
            return None
        dd = weighted_draw(dw, self.rng, ignore_index=oo)
        if dd == -1:
            return None
        return idxs[oo], idxs[dd]

    def weighted_index(self, weights: Sequence[float]) -> int:
        return weighted_draw(weights, self.rng)

    # ------------------------------------------------------------- agent pool
    def release_agents(self) -> int:
        if not self.agents_enabled or self.reachable_targets() < 2:
            return 0
        released = 0
        for a in self.agents:
            if not a.active:
                if a.renew():
                    released += 1
                if released >= self.release_rate:
                    break
        return released

    @property
    def active_agents(self) -> List[Agent]:
        return [a for a in self.agents if a.active]

    # -------------------------------------------------------------------- step
    def step(self) -> None:
        for a in self.agents:
            if a.active:
                a.vision_scan()
        for a in self.agents:
            if not a.active:
                continue
            a.set_dir_to_target()
            if not a.active:
                continue
            a.move()
            a.mark_occupancy()
            a.target_check()
        self.release_agents()
        # update + cull traces
        if self.traces:
            for t in list(self.traces):
                t.update(self)
                if not t.active and t.age > t.max_age:
                    self.traces.remove(t)
        self.grid.decay_fields()
        self.ticks += 1

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    # --------------------------------------------------------------- isovist
    def compute_isovist(self, x: float, y: float, **kwargs) -> Isovist:
        self.isovist = Isovist(self, x, y, **kwargs).make()
        return self.isovist

    # ================================================================= EDIT API
    # -- ODs -----------------------------------------------------------------
    def add_od(self, x: float, y: float, group: int = 0,
               origin_weight: float = 1.0, dest_weight: float = 1.0,
               name: str = "") -> int:
        od = OD(x=x, y=y, group=group, origin_weight=origin_weight,
                dest_weight=dest_weight, name=name)
        # reuse a free slot if one exists
        for i, existing in enumerate(self.ods):
            if existing is None:
                self.ods[i] = od
                self.grid.compute_cost_field(i, x, y, self.rng)
                return i
        self.ods.append(od)
        k = len(self.ods) - 1
        self.grid.compute_cost_field(k, x, y, self.rng)
        return k

    def delete_od(self, index: int) -> None:
        if 0 <= index < len(self.ods):
            self.ods[index] = None
            self.grid._cost_fields.pop(index, None)

    def move_od(self, index: int, x: float, y: float) -> None:
        od = self.ods[index]
        if od is None:
            return
        od.x, od.y = x, y
        self.grid.compute_cost_field(index, x, y, self.rng)

    def weight_od(self, index: int, origin_weight: Optional[float] = None,
                  dest_weight: Optional[float] = None) -> None:
        od = self.ods[index]
        if od is None:
            return
        if origin_weight is not None:
            od.origin_weight = min(max(origin_weight, 0.0), 1.0)
        if dest_weight is not None:
            od.dest_weight = min(max(dest_weight, 0.0), 1.0)

    # -- buildings / obstacles ----------------------------------------------
    def _register_edit(self, b: Building) -> None:
        self.grid.partial_update(b.bbox())
        b.footprint.gridded_segments(self.grid)
        self._build_cost_fields()

    def add_building(self, poly: Polygon, height: float = 10.0,
                     layer: str = "") -> Building:
        b = Building.from_polygon(poly, kind="building", layer=layer, height=height)
        self.buildings.append(b)
        self.grid.set_geometry(self.buildings, self.obstacles, self.site_polygon)
        b.footprint.gridded_segments(self.grid)
        self._build_cost_fields()
        return b

    def add_obstacle(self, poly: Polygon, layer: str = "OBSTACLES_LOW") -> Building:
        b = Building.from_polygon(poly, kind="obstacle", layer=layer, height=0.0)
        self.obstacles.append(b)
        self.grid.set_geometry(self.buildings, self.obstacles, self.site_polygon)
        self._build_cost_fields()
        return b

    def delete_building(self, b: Building) -> None:
        coll = self.buildings if b.kind == "building" else self.obstacles
        if b in coll:
            coll.remove(b)
            self.grid.set_geometry(self.buildings, self.obstacles, self.site_polygon)
            self._build_cost_fields()

    def move_building(self, b: Building, dx: float, dy: float) -> None:
        b.move(dx, dy, 0)
        self.grid.set_geometry(self.buildings, self.obstacles, self.site_polygon)
        b.footprint.gridded_segments(self.grid)
        self._build_cost_fields()

    def set_building_height(self, b: Building, height: float) -> None:
        b.height = max(0.0, height)

    def split_building(self, b: Building, x1: float, y1: float, x2: float, y2: float
                       ) -> Optional[Tuple[Building, Building]]:
        """Split ``b`` along the cut line (x1,y1)->(x2,y2) if it crosses exactly
        two edges (port of ``Scene.user_onPolySplit``)."""
        verts = b.footprint.as_xy()
        inters, edge_idx = line_poly_intersections(verts, x1, y1, x2, y2)
        if len(inters) != 2:
            return None
        foot1, foot2 = split_polygon(verts, inters, edge_idx)
        b1 = Building.from_polygon(foot1, kind=b.kind, layer=b.layer, height=b.height)
        b2 = Building.from_polygon(foot2, kind=b.kind, layer=b.layer, height=b.height)
        coll = self.buildings if b.kind == "building" else self.obstacles
        coll.remove(b)
        coll.append(b1)
        coll.append(b2)
        self.grid.set_geometry(self.buildings, self.obstacles, self.site_polygon)
        b1.footprint.gridded_segments(self.grid)
        b2.footprint.gridded_segments(self.grid)
        self._build_cost_fields()
        return b1, b2

    # -- modules -------------------------------------------------------------
    def add_module_prototype(self, proto: ModulePrototype) -> None:
        self.module_library.append(proto)

    def place_module(self, proto: ModulePrototype, x: float, y: float,
                     snap: bool = True) -> PlacedModule:
        pm = PlacedModule(proto, x, y)
        if snap and self.insertion_points:
            pm.snap(self.insertion_points)
        self.placed_modules.append(pm)
        return pm

    # ================================================================= IO
    def save_ods(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for od in self.ods:
                if od is not None:
                    fh.write(od.to_line() + "\n")

    def load_ods(self, path: str, xoffs: float = 0.0, yoffs: float = 0.0) -> None:
        self.ods = _load_ods_file(path, xoffs, yoffs)
        self._build_cost_fields()

    def save_geometry_json(self, path: str) -> None:
        data = {
            "site_polygon": self.site_polygon,
            "buildings": [
                {"polygon": b.footprint.as_xy(), "height": b.height, "layer": b.layer}
                for b in self.buildings
            ],
            "obstacles": [
                {"polygon": o.footprint.as_xy(), "layer": o.layer} for o in self.obstacles
            ],
            "ods": [od.to_line() for od in self.ods if od is not None],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # --------------------------------------------------------------- snapshot
    def agent_positions_world(self) -> np.ndarray:
        pts = [(self.grid.world_x(a.px), self.grid.world_y(a.py)) for a in self.active_agents]
        return np.array(pts, dtype=float) if pts else np.empty((0, 2))


def _load_ods_file(path: str, xoffs: float = 0.0, yoffs: float = 0.0) -> List[OD]:
    ods: List[OD] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            od = OD.from_line(line)
            if od is not None:
                od.x += xoffs
                od.y += yoffs
                ods.append(od)
    return ods

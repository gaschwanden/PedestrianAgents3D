"""Top-level simulation: the Python counterpart of ``Scene`` + ``Grid_Thread``.

Owns the navigation grid, the origin/destination places, the buildings /
obstacles / landmarks / placed modules, the agent pool and the trace list, and
advances everything one tick at a time. It also exposes the full editing API
(add/move/delete/split buildings and obstacles, add/move/delete/weight ODs),
the analysis modes, isovist computation, and load/save.
"""
from __future__ import annotations

import datetime as _dt
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
from .rivers import River, Season
from .rivers import build_layers as build_river_layers
from .rivers import summarise as river_summary
from .research import Research
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
        rivers: Optional[Sequence[River]] = None,
        season: Season = Season.NORMAL,
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
        cost_field_provider=None,
    ):
        #: Optional ``callable(sim) -> {od_index: cost array} | None``. When it
        #: returns fields they are installed instead of being solved, so a packed
        #: scene can start on a phone without running Dijkstra. Any OD it leaves
        #: out is solved as usual.
        self.cost_field_provider = cost_field_provider
        self.ods: List[Optional[OD]] = list(ods)
        self.buildings: List[Building] = [_to_building(b, "building") for b in (buildings or [])]
        self.obstacles: List[Building] = [_to_building(o, "obstacle", 0.0) for o in (obstacles or [])]
        self.rivers: List[River] = list(rivers or [])
        self.season: Season = Season(season)
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
        self.research = Research()
        self.population = None
        self.task_model = None
        self.tasks_enabled = False
        self.load_k = 0.2
        self.category_occupancy: dict = {}
        self.trip_log: list = []

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
        if self.rivers:
            self.rebuild_river_layers()   # also builds the cost fields
        else:
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
        ready = {}
        if self.cost_field_provider is not None:
            ready = self.cost_field_provider(self) or {}
        for k, od in self._active_ods():
            field = ready.get(k)
            if field is not None and field.shape == (self.grid.nx, self.grid.ny):
                self.grid._cost_fields[k] = field
            else:
                self.grid.compute_cost_field(k, od.x, od.y, self.rng)

    def recompute_cost_fields(self) -> None:
        self._build_cost_fields()

    # ----------------------------------------------------------------- layers
    @property
    def layers(self):
        """The grid's named landscape layers (rivers, slope, vegetation ...)."""
        return self.grid.layers

    def add_layer(self, layer):
        """Add/replace a landscape layer and rebuild routing."""
        self.grid.add_layer(layer)
        self._build_cost_fields()
        return layer

    def set_layer_weight(self, name: str, weight: float) -> None:
        """Set a layer's weight and rebuild routing if it actually changed."""
        self.grid.layers.set_weight(name, weight)
        self.refresh_layers()

    def refresh_layers(self, force: bool = False) -> bool:
        """Rebuild friction/walkability and cost fields after a weight change."""
        if self.grid.refresh_layers(force=force):
            self._build_cost_fields()
            return True
        return False

    def reachable_targets(self) -> int:
        return len(self._active_ods())

    def geometry_for_grid(self):
        """Buildings and obstacles that currently block movement.

        Backfilled and under-construction footprints do not block. An element
        whose phases are all off does not block. With no phase list loaded,
        every standing element blocks, as before.
        """
        def keep(item) -> bool:
            state = getattr(item, "state", "standing")
            if state in ("backfilled", "under_construction"):
                return False
            return self.research.phase_allows(getattr(item, "phase_ids", ()))

        return (
            [b for b in self.buildings if keep(b)],
            [o for o in self.obstacles if keep(o)],
        )

    def apply_phase_filter(self) -> None:
        """Rebuild walkability for the active phases and refresh cost fields."""
        buildings, obstacles = self.geometry_for_grid()
        self.grid.set_geometry(buildings, obstacles, self.site_polygon)
        boxes = []
        for item in list(self.buildings) + list(self.obstacles):
            if getattr(item, "phase_ids", None):
                boxes.append(item.bbox())
        if boxes:
            rect = (
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            )
            self.grid.partial_update(rect)
        self._sync_construction_layer()
        self._build_cost_fields()

    def _sync_construction_layer(self) -> None:
        """High friction on footprints marked under construction. No-op otherwise."""
        from .geometry import rasterize_polygons_mask
        from .layers import Layer

        polys = []
        for item in list(self.buildings) + list(self.obstacles):
            if getattr(item, "state", "standing") != "under_construction":
                continue
            if not self.research.phase_allows(getattr(item, "phase_ids", ())):
                continue
            polys.append(item.footprint.as_xy())
        had = self.grid.layers.get("construction") is not None
        if not polys and not had:
            return
        self.grid.layers.remove("construction")
        if polys:
            mask = rasterize_polygons_mask(polys, self.grid.xs, self.grid.ys)
            self.grid.layers.add(Layer(
                "construction", mask.astype(float), weight=4.0,
                description="under construction",
            ))
        self.grid.refresh_layers(force=True)

    def note_category(self, i: int, j: int, agent) -> None:
        """Split occupancy by task and by population class, on demand."""
        keys = []
        if getattr(agent, "task", ""):
            keys.append(f"task:{agent.task}")
        if getattr(agent, "pclass", ""):
            keys.append(f"class:{agent.pclass}")
        if not keys:
            return
        for key in keys:
            arr = self.category_occupancy.get(key)
            if arr is None:
                arr = np.zeros_like(self.grid.occupancy)
                self.category_occupancy[key] = arr
            arr[i, j] += 1.0

    def display_occupancy(self):
        """Occupancy to draw: the filtered task or class, or the whole field."""
        filt = self.research.density_filter
        if not filt:
            return self.grid.occupancy, self.grid.max_occupancy
        arr = self.category_occupancy.get(f"{filt[0]}:{filt[1]}")
        if arr is None:
            return np.zeros_like(self.grid.occupancy), 1.0
        return arr, float(arr.max() or 1.0)

    def population_count(self) -> float:
        from .phases import inhabitants
        return inhabitants(
            self.buildings, self.research.current_phase_ids(),
            rule=self.research.population_rule,
            persons_per_house=self.research.persons_per_house,
            persons_per_m2=self.research.persons_per_m2,
        )

    def population_label(self) -> str:
        if not any(getattr(b, "function", "") == "domestic" for b in self.buildings):
            return ""
        n = self.population_count()
        if self.research.population_rule == "per_m2":
            rule = f"{self.research.persons_per_m2:g}/m²"
        else:
            rule = f"{self.research.persons_per_house:g}/house"
        return f"Population: {n:g} (rule: {rule}, assumption)"

    # -------------------------------------------------------------- trip draw
    def draw_trip(self) -> Optional[Tuple[int, int]]:
        """Draw an origin and a destination.

        Weights pass through :class:`~pedsim.research.Research`, so chronology
        and phases can zero a place without deleting it. With no phases loaded
        and chronology left off, the weights are the OD weights themselves.
        """
        active = self._active_ods()
        if len(active) < 2:
            return None
        origins = [(k, od) for k, od in active if self.research.origin_weight(od) > 0]
        if len(origins) < 1:
            return None
        ow = [self.research.origin_weight(od) for _, od in origins]
        oo = weighted_draw(ow, self.rng)
        if oo == -1:
            return None
        origin_od = origins[oo][1]
        dests = []
        dw = []
        for k, od in active:
            if od is origin_od:
                continue
            weight = self.research.dest_weight(origin_od, od)
            if weight > 0:
                dests.append(k)
                dw.append(weight)
        if not dests:
            return None
        dd = weighted_draw(dw, self.rng)
        if dd == -1:
            return None
        return origins[oo][0], dests[dd]

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
    #: Scan every walker's vision cone with array operations. ``False`` runs
    #: the per-agent reference scan instead; both give the same result bit for
    #: bit (see :mod:`pedsim.vision`).
    batch_vision = True

    def step(self) -> None:
        if self.batch_vision:
            from .vision import scan_all
            scan_all(self)
        else:
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
        if self.category_occupancy:
            for arr in self.category_occupancy.values():
                arr *= self.grid.occupancy_decay
                arr[arr < 1e-3] = 0.0
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
               name: str = "", kind: str = "site", phase_ids: Optional[Sequence[str]] = None,
               site: str = "", capacity: Optional[float] = None,
               tags: Optional[Sequence[str]] = None) -> int:
        od = OD(x=x, y=y, group=group, origin_weight=origin_weight,
                dest_weight=dest_weight, name=name, kind=kind, site=site,
                phase_ids=list(phase_ids or []), capacity=capacity,
                tags=list(tags or []))
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

    def add_building(self, poly: Polygon, height: Optional[float] = None,
                     layer: str = "", function: str = "unknown",
                     phase_ids: Optional[Sequence[str]] = None,
                     inhabitants: Optional[float] = None,
                     state: str = "standing") -> Building:
        from .building import STANDARD_BUILDING_HEIGHT
        if height is None:
            height = STANDARD_BUILDING_HEIGHT
        b = Building.from_polygon(
            poly, kind="building", layer=layer, height=height,
            function=function, phase_ids=phase_ids,
            inhabitants=inhabitants, state=state,
        )
        self.buildings.append(b)
        self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
        b.footprint.gridded_segments(self.grid)
        self._build_cost_fields()
        return b

    def add_obstacle(self, poly: Polygon, layer: str = "OBSTACLES_LOW") -> Building:
        b = Building.from_polygon(poly, kind="obstacle", layer=layer, height=0.0)
        self.obstacles.append(b)
        self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
        self._build_cost_fields()
        return b

    # -- rivers & seasons ----------------------------------------------------
    def add_river(self, path, name: str = "", **kw) -> River:
        """Add a watercourse. Unlike an obstacle it is not a hard footprint: it
        rasterises into a cost layer that depends on the season."""
        if len(path) < 2:
            raise ValueError("a river needs at least two points")
        name = name or f"river {len(self.rivers) + 1}"
        r = River(name=name, path=[tuple(p) for p in path], **kw)
        self.rivers.append(r)
        self.rebuild_river_layers()
        return r

    def delete_river(self, r: River) -> None:
        if r in self.rivers:
            self.rivers.remove(r)
            self.rebuild_river_layers()

    def add_ford(self, r: River, x: float, y: float) -> None:
        r.fords.append((x, y))
        self.rebuild_river_layers()

    def set_season(self, season: Season) -> None:
        """Switch season, re-rasterising every river and re-routing."""
        self.season = Season(season)
        self.rebuild_river_layers()

    def advance_season(self) -> Season:
        self.set_season(self.season.next())
        return self.season

    def rebuild_river_layers(self) -> None:
        """Refresh the ``rivers``/``flood`` layers from the current season."""
        g = self.grid
        for name in ("rivers", "flood"):
            g.layers.remove(name)
        for lyr in build_river_layers(g.xs, g.ys, self.rivers, self.season):
            g.layers.add(lyr)
        g.refresh_layers(force=True)
        self._build_cost_fields()

    def season_summary(self) -> str:
        return river_summary(self.rivers, self.season)

    def delete_building(self, b: Building) -> None:
        coll = self.buildings if b.kind == "building" else self.obstacles
        if b in coll:
            coll.remove(b)
            self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
            self._build_cost_fields()

    def move_building(self, b: Building, dx: float, dy: float) -> None:
        b.move(dx, dy, 0)
        self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
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
        b.copy_phase_onto(b1)
        b.copy_phase_onto(b2)
        coll = self.buildings if b.kind == "building" else self.obstacles
        coll.remove(b)
        coll.append(b1)
        coll.append(b2)
        self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
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

    #: Bumped when the on-disk geometry format changes in a way readers care about.
    #: 3 adds phases, population, scenario_ref and the JSON OD record. The
    #: ``ods`` text lines are still written so the Java tool can read them.
    GEOMETRY_FORMAT = 3

    def geometry_dict(self) -> dict:
        r = self.research
        return {
            "format": self.GEOMETRY_FORMAT,
            "saved_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "season": self.season.value,
            "site_polygon": self.site_polygon,
            "scenario_ref": r.scenario_ref,
            "phases": [p.to_dict() for p in r.phases],
            "population": {
                "rule": r.population_rule,
                "persons_per_house": r.persons_per_house,
                "persons_per_m2": r.persons_per_m2,
                "agents_per_person": r.agents_per_person,
            },
            "phase_mode": r.phase_mode,
            "active_phases": r.current_phase_ids() or [],
            "buildings": [
                {
                    "polygon": b.footprint.as_xy(), "height": b.height, "layer": b.layer,
                    "phase_ids": list(b.phase_ids), "function": b.function,
                    "inhabitants": b.inhabitants, "state": b.state,
                }
                for b in self.buildings
            ],
            "obstacles": [
                {
                    "polygon": o.footprint.as_xy(), "layer": o.layer,
                    "phase_ids": list(getattr(o, "phase_ids", [])),
                    "state": getattr(o, "state", "standing"),
                }
                for o in self.obstacles
            ],
            "rivers": [rv.to_dict() for rv in self.rivers],
            "ods": [od.to_line() for od in self.ods if od is not None],
            "ods_meta": [od.to_dict() for od in self.ods if od is not None],
        }

    def save_geometry_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.geometry_dict(), fh, indent=2)

    def save_geometry_versioned(self, path: str, keep: int = 20) -> str:
        """Save, keeping the previous versions alongside.

        Edits to an archaeological reconstruction are interpretations, and the
        one you want back is usually the one you just overwrote. So ``path`` is
        always the current state, and every save first rolls the existing file
        into ``<stem>.vNNN<ext>`` next to it. Returns the path of the version
        that was archived, or ``""`` on the first save.

        ``keep`` caps how many archived versions are retained (oldest pruned).
        """
        archived = ""
        stem, ext = os.path.splitext(path)
        if os.path.exists(path):
            n = self.next_version_number(path)
            archived = f"{stem}.v{n:03d}{ext}"
            os.replace(path, archived)
        self.save_geometry_json(path)
        if keep > 0:
            versions = sorted(self.list_versions(path))
            for old in versions[:-keep]:
                try:
                    os.remove(old)
                except OSError:
                    pass
        return archived

    @staticmethod
    def list_versions(path: str) -> List[str]:
        """Archived versions of ``path``, oldest first."""
        stem, ext = os.path.splitext(path)
        directory = os.path.dirname(os.path.abspath(path)) or "."
        prefix = os.path.basename(stem) + ".v"
        out = []
        for name in os.listdir(directory) if os.path.isdir(directory) else []:
            if name.startswith(prefix) and name.endswith(ext):
                mid = name[len(prefix):len(name) - len(ext)]
                if mid.isdigit():
                    out.append(os.path.join(directory, name))
        return sorted(out)

    @classmethod
    def next_version_number(cls, path: str) -> int:
        versions = cls.list_versions(path)
        if not versions:
            return 1
        stem, ext = os.path.splitext(path)
        prefix = os.path.basename(stem) + ".v"
        nums = []
        for v in versions:
            name = os.path.basename(v)
            nums.append(int(name[len(prefix):len(name) - len(ext)]))
        return max(nums) + 1

    def load_geometry_json(self, path: str) -> None:
        """Replace buildings/obstacles/site (and ODs, if present) from a file
        written by :meth:`save_geometry_json`."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.load_geometry_dict(data)

    def load_geometry_dict(self, data: dict) -> None:
        """Apply a :meth:`geometry_dict` mapping (the field client keeps saves
        as dicts, not files)."""
        from .phases import Phase, migrate_geometry
        data = migrate_geometry(data)
        if data.get("site_polygon"):
            self.site_polygon = [tuple(p) for p in data["site_polygon"]]
        self.buildings = [
            Building.from_polygon(
                [tuple(p) for p in b["polygon"]], kind="building",
                layer=b.get("layer", ""), height=b.get("height", 10.0),
                phase_ids=b.get("phase_ids") or [], function=b.get("function", "unknown"),
                inhabitants=b.get("inhabitants"), state=b.get("state", "standing"),
            )
            for b in data.get("buildings", [])
        ]
        self.obstacles = [
            Building.from_polygon(
                [tuple(p) for p in o["polygon"]], kind="obstacle",
                layer=o.get("layer", "OBSTACLES_LOW"), height=0.0,
                phase_ids=o.get("phase_ids") or [], state=o.get("state", "standing"),
            )
            for o in data.get("obstacles", [])
        ]
        if data.get("ods_meta"):
            self.ods = [OD.from_dict(item) for item in data["ods_meta"]]
        elif data.get("ods"):
            ods: List[OD] = []
            for line in data["ods"]:
                od = OD.from_line(line)
                if od is not None:
                    ods.append(od)
            if ods:
                self.ods = ods
        self.rivers = [River.from_dict(r) for r in data.get("rivers", [])]
        self.research.phases = [Phase.from_dict(p) for p in data.get("phases", [])]
        pop = data.get("population") or {}
        if pop:
            self.research.population_rule = pop.get("rule", self.research.population_rule)
            self.research.persons_per_house = float(pop.get("persons_per_house", 5))
            self.research.persons_per_m2 = float(pop.get("persons_per_m2", 0.1))
            self.research.agents_per_person = pop.get("agents_per_person")
        if data.get("scenario_ref"):
            self.research.scenario_ref = data["scenario_ref"]
        if data.get("phase_mode"):
            self.research.phase_mode = data["phase_mode"]
        if data.get("active_phases") is not None and self.research.phases:
            self.research.manual_phase_ids = list(data["active_phases"])
        if data.get("season"):
            self.season = Season(data["season"])
        self.grid.set_geometry(*self.geometry_for_grid(), self.site_polygon)
        for b in (*self.buildings, *self.obstacles):
            b.footprint.gridded_segments(self.grid)
        self.rebuild_river_layers()   # also rebuilds the cost fields

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

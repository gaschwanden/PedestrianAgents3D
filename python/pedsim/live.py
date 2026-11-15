"""Live engine: one scene, stepped and edited through a small message API.

The desktop viewer drives :class:`~pedsim.simulation.Simulation` directly. A
phone or tablet cannot read GeoTIFF tiles or run ``pyproj``, so the field
client gets its scenes *packed*: everything the laptop resolved from raw
geodata (terrain on the grid, rivers, geometry, the georeference) is written
to a JSON description plus one binary file. :class:`LiveEngine` rebuilds the
very same ``Simulation`` from that pack using numpy only, and then steps and
edits it. In the browser the engine runs inside Pyodide; on the laptop the same
class backs the tests and the hub. There is no second agent model.

Two things are deliberately not recomputed on the device unless an edit forces
it:

* **cost fields** -- the pack carries the Dijkstra result for the default state
  (per season for scenes with rivers), installed through
  ``Simulation.cost_field_provider``;
* **the projection** -- a :class:`BilinearFrame` interpolates lon/lat between
  the four packed corners of the scene, which is within a few metres over the
  whole cluster and far below a cell at village scale.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .building import Building
from .chronology import Interval
from .od import OD
from .phases import Phase
from .rivers import River, Season
from .simulation import (
    ANALYSIS_FACADE_VIS,
    ANALYSIS_FACADE_VIS_O,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ANALYSIS_TRACES_O,
    Simulation,
)
from .topography import TerrainCost, Topography

PACK_FORMAT = 1

ANALYSIS_BY_NAME = {
    "path": ANALYSIS_PATHOVERLAP,
    "facade": ANALYSIS_FACADE_VIS,
    "facadeO": ANALYSIS_FACADE_VIS_O,
    "traces": ANALYSIS_TRACES,
    "tracesO": ANALYSIS_TRACES_O,
}

#: Month that stands for each river season when the client only offers a
#: season control (daylight and event weights come from that month).
SEASON_MONTH = {"dry": 8, "normal": 5, "spring floods": 3}

#: Largest side of the density image sent to the client.
MAX_FIELD_SIDE = 640


# ---------------------------------------------------------------- georeference
class BilinearFrame:
    """Local metres <-> lon/lat by bilinear interpolation on a control mesh.

    ``bounds`` is ``(min_x, min_y, max_x, max_y)`` in local metres. ``mesh`` is
    ``{"lon": rows, "lat": rows}`` where row ``j`` runs west to east at the
    ``j``-th northing, south first. A 2x2 mesh is the four corners; the cluster
    uses a finer one because UTM against lon/lat bends by ~90 m over 80 km.
    """

    def __init__(self, bounds: Sequence[float], mesh: dict):
        self.min_x, self.min_y, self.max_x, self.max_y = (float(v) for v in bounds)
        self.lon = np.asarray(mesh["lon"], dtype=float)
        self.lat = np.asarray(mesh["lat"], dtype=float)
        if self.lon.shape != self.lat.shape or min(self.lon.shape) < 2:
            raise ValueError("georeference mesh needs matching lon/lat grids of at least 2x2")

    def _interp(self, table: np.ndarray, u, v):
        rows, cols = table.shape
        fu = np.clip(u, 0.0, 1.0) * (cols - 1)
        fv = np.clip(v, 0.0, 1.0) * (rows - 1)
        i = np.minimum(fu.astype(int), cols - 2)
        j = np.minimum(fv.astype(int), rows - 2)
        # outside the mesh, extend the edge patch linearly
        a = u * (cols - 1) - i
        b = v * (rows - 1) - j
        south = table[j, i] + (table[j, i + 1] - table[j, i]) * a
        north = table[j + 1, i] + (table[j + 1, i + 1] - table[j + 1, i]) * a
        return south + (north - south) * b

    def to_lonlat(self, x, y):
        u = (np.asarray(x, dtype=float) - self.min_x) / (self.max_x - self.min_x)
        v = (np.asarray(y, dtype=float) - self.min_y) / (self.max_y - self.min_y)
        return self._interp(self.lon, u, v), self._interp(self.lat, u, v)

    def to_local(self, lon, lat):
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        # The map is almost affine, so start from the affine guess and correct
        # the residual a few times with the mean scale.
        dlon = float((self.lon[:, -1] - self.lon[:, 0]).mean())
        dlat = float((self.lat[-1, :] - self.lat[0, :]).mean())
        u = (lon - self.lon[0, 0]) / dlon
        v = (lat - self.lat[0, 0]) / dlat
        w = self.max_x - self.min_x
        h = self.max_y - self.min_y
        for _ in range(6):
            glon, glat = self.to_lonlat(self.min_x + u * w, self.min_y + v * h)
            u = u + (lon - glon) / dlon
            v = v + (lat - glat) / dlat
        return self.min_x + u * w, self.min_y + v * h

    def corners_lonlat(self) -> List[List[float]]:
        """``[nw, ne, se, sw]``, the order a map image source wants."""
        pick = lambda j, i: [float(self.lon[j, i]), float(self.lat[j, i])]
        return [pick(-1, 0), pick(-1, -1), pick(0, -1), pick(0, 0)]

    def to_dict(self) -> dict:
        return {
            "bounds": [self.min_x, self.min_y, self.max_x, self.max_y],
            "mesh": {"lon": self.lon.tolist(), "lat": self.lat.tolist()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BilinearFrame":
        return cls(data["bounds"], data["mesh"])

    @classmethod
    def from_frame(cls, frame, bounds: Sequence[float], nodes: int = 2) -> "BilinearFrame":
        """From a :class:`pedsim.geo.LocalFrame` (laptop side, needs pyproj)."""
        min_x, min_y, max_x, max_y = bounds
        X, Y = np.meshgrid(np.linspace(min_x, max_x, nodes),
                           np.linspace(min_y, max_y, nodes))
        lat, lon = frame.to_latlon(X, Y)
        return cls(bounds, {"lon": np.asarray(lon), "lat": np.asarray(lat)})

    @classmethod
    def flat(cls, bounds: Sequence[float], lat0: float, lon0: float,
             x0: float = 0.0, y0: float = 0.0) -> "BilinearFrame":
        """Equirectangular frame with local ``(x0, y0)`` at ``(lat0, lon0)``."""
        min_x, min_y, max_x, max_y = bounds
        k = 111320.0
        c = k * math.cos(math.radians(lat0))
        lon = [[lon0 + (x - x0) / c for x in (min_x, max_x)] for _ in (0, 1)]
        lat = [[lat0 + (y - y0) / k] * 2 for y in (min_y, max_y)]
        return cls(bounds, {"lon": lon, "lat": lat})


# ----------------------------------------------------------------------- pack
class _Blob:
    """Concatenated little-endian arrays with an index for the JSON side."""

    def __init__(self) -> None:
        self.parts: List[bytes] = []
        self.index: Dict[str, dict] = {}
        self.size = 0

    def add(self, name: str, arr: np.ndarray, dtype: str = "<f8") -> None:
        data = np.ascontiguousarray(arr, dtype=dtype).tobytes()
        self.index[name] = {"offset": self.size, "shape": list(arr.shape), "dtype": dtype}
        self.parts.append(data)
        self.size += len(data)

    def bytes(self) -> bytes:
        return b"".join(self.parts)


def _read(blob, entry: dict) -> np.ndarray:
    dtype = np.dtype(entry["dtype"])
    count = int(np.prod(entry["shape"])) if entry["shape"] else 1
    arr = np.frombuffer(blob, dtype=dtype, count=count, offset=int(entry["offset"]))
    return arr.reshape(entry["shape"]).astype(float)


#: Layers the simulation rebuilds itself and that are therefore not packed.
DERIVED_LAYERS = ("rivers", "flood", "construction")


def packed_layers(sim: Simulation) -> list:
    return [layer for layer in sim.grid.layers if layer.name not in DERIVED_LAYERS]


def phase_key(sim: Simulation) -> str:
    """Identifies the walkable geometry: the active phases if any geometry is phased."""
    phased = any(getattr(item, "phase_ids", None)
                 for item in list(sim.buildings) + list(sim.obstacles)
                 + packed_layers(sim))
    if not phased:
        return "*"
    return ",".join(sorted(sim.research.current_phase_ids() or []))


def cost_key(sim: Simulation) -> str:
    return f"{sim.season.value}|{phase_key(sim)}"


def pack_scene(sim: Simulation, scene_id: str, name: str, scale: str,
               frame: BilinearFrame, site: str = "", zoom: float = 16.0,
               sites: Optional[List[dict]] = None,
               cost_seasons: Optional[Sequence[Season]] = None,
               note: str = "", cost_dtype: str = "<f8") -> Tuple[dict, bytes]:
    """Describe ``sim`` so :class:`LiveEngine` can rebuild it without geodata.

    Returns ``(meta, blob)``. ``cost_seasons`` lists the seasons whose cost
    fields are solved now and shipped; the simulation is left in the season it
    came in with. ``cost_dtype`` ``"<f4"`` halves the size of the packed routes;
    the scene then no longer replays bit for bit like its source, because a
    walker choosing between two nearly equal routes may tip the other way.
    """
    grid = sim.grid
    blob = _Blob()
    if grid.elevation is not None:
        blob.add("elevation", grid.elevation)

    layers = []
    for n, layer in enumerate(packed_layers(sim)):
        entry = f"layer/{n}"
        blob.add(entry, layer.data)
        layers.append({
            "name": layer.name, "kind": layer.kind, "weight": layer.weight,
            "color": list(layer.color), "description": layer.description,
            "phase_ids": list(layer.phase_ids), "array": entry,
        })

    costs: Dict[str, Dict[str, str]] = {}
    home = sim.season
    seasons = [home] + [s for s in (cost_seasons or []) if s != home]
    if not sim.rivers:
        seasons = [home]          # without rivers the season does not touch cost
    for season in seasons:
        if season != sim.season:
            sim.set_season(season)
        key = cost_key(sim)
        costs[key] = {}
        levels = [grid] + [p.grid for p in sim.patches]
        for k, od in sim._active_ods():
            if any(g.cost_field(k) is None for g in levels):
                continue
            names = []
            for n, g in enumerate(levels):
                entry = f"cost/{key}/{k}" + (f"/{n}" if n else "")
                blob.add(entry, g.cost_field(k), dtype=cost_dtype)
                names.append(entry)
            # one array for a single grid, a list (coarse first) for a nested scene
            costs[key][str(k)] = names if sim.nested is not None else names[0]
    if sim.season != home:
        sim.set_season(home)

    r = sim.research
    meta = {
        "pack_format": PACK_FORMAT,
        "id": scene_id,
        "name": name,
        "scale": scale,
        "site": site,
        "zoom": zoom,
        "note": note,
        "engine": "pedsim live",
        "georef": frame.to_dict(),
        "grid": {
            "bounds": [grid.min_x, grid.min_y, grid.max_x, grid.max_y],
            "gridsize": grid.gridsize, "nx": grid.nx, "ny": grid.ny,
        },
        "terrain_cost": asdict(grid.terrain_cost),
        "params": {
            "num_agents": sim.num_agents, "release_rate": sim.release_rate,
            "speed": sim.speed, "cone_vision": sim.cone_vision,
            "radius_divider": sim.radius_divider,
            "blur_occupancy": sim.blur_occupancy, "blur_decay": sim.blur_decay,
            "respawn_at_origin": bool(sim.respawn_at_origin),
            "trace_percent": sim.trace_percent, "num_groups": sim.num_groups,
            "seed": getattr(sim, "pack_seed", None),
        },
        "research": {
            "respect_chronology": r.respect_chronology,
            "window": [r.window.end_bc, r.window.start_bc],
            "tau": r.tau, "undated_policy": r.undated_policy,
        },
        "geometry": sim.geometry_dict(),
        "nested": None if sim.nested is None else {
            "fine": sim.nested.fine, "tile": sim.nested.tile, "margin": sim.nested.margin,
            "rivers": sim.nested.rivers, "max_fine_cells": sim.nested.max_fine_cells,
            "marked": [list(r) for r in sim.nested.marked],
        },
        "layers": layers,
        "sites": sites or [],
        "arrays": blob.index,
        "costs": costs,
    }
    return meta, blob.bytes()


def build_simulation(meta: dict, blob=None, use_packed_costs: bool = True,
                     num_agents: Optional[int] = None) -> Tuple[Simulation, dict]:
    """Rebuild the packed ``Simulation``. Returns it with the packed cost store."""
    g = meta["grid"]
    geo = meta["geometry"]
    params = dict(meta["params"])
    seed = params.pop("seed", None)
    respawn = bool(params.pop("respawn_at_origin", False))
    if num_agents is not None:
        params["num_agents"] = int(num_agents)
    arrays = meta.get("arrays", {})

    topo = None
    if "elevation" in arrays and blob is not None:
        elev = _read(blob, arrays["elevation"])
        topo = Topography(elev, g["bounds"][0] + g["gridsize"] / 2.0,
                          g["bounds"][1] + g["gridsize"] / 2.0, g["gridsize"])

    store: Dict[str, Dict[int, np.ndarray]] = {}
    if use_packed_costs and blob is not None:
        for key, entries in meta.get("costs", {}).items():
            store[key] = {
                int(k): ([_read(blob, arrays[n]) for n in name] if isinstance(name, list)
                         else _read(blob, arrays[name]))
                for k, name in entries.items()
            }

    state = {"store": store, "valid": set(), "pristine": True, "ready": False,
             "default": next(iter(store), None)}
    for fields in store.values():
        state["valid"].update(fields.keys())

    def provider(sim: Simulation):
        if not state["pristine"]:
            return None
        if sim.terrain_weight != 1.0 or sim.river_weight != 1.0:
            return None            # packed routes are for the scene as built
        # Until the research settings are attached the simulation cannot name
        # its own state; it is being built in the packed default state.
        key = cost_key(sim) if state["ready"] else state["default"]
        fields = state["store"].get(key)
        if not fields:
            return None
        return {k: v for k, v in fields.items() if k in state["valid"]}

    phases = [Phase.from_dict(p) for p in geo.get("phases", [])]
    buildings = [
        Building.from_polygon(
            [tuple(p) for p in b["polygon"]], kind="building",
            layer=b.get("layer", ""), height=b.get("height", 3.0),
            phase_ids=b.get("phase_ids") or [], function=b.get("function", "unknown"),
            inhabitants=b.get("inhabitants"), state=b.get("state", "standing"),
        )
        for b in geo.get("buildings", [])
    ]
    for built, b in zip(buildings, geo.get("buildings", [])):
        built.wall_m = b.get("wall_m")
        built.door = tuple(b["door"]) if b.get("door") else None
        built.door_width_m = float(b.get("door_width_m", 1.2))
    obstacles = [
        Building.from_polygon(
            [tuple(p) for p in o["polygon"]], kind="obstacle",
            layer=o.get("layer", "OBSTACLES_LOW"), height=0.0,
            phase_ids=o.get("phase_ids") or [], state=o.get("state", "standing"),
        )
        for o in geo.get("obstacles", [])
    ]
    ods = [OD.from_dict(item) for item in geo.get("ods_meta", [])]
    rivers = [River.from_dict(item) for item in geo.get("rivers", [])]
    site_polygon = geo.get("site_polygon")
    if site_polygon:
        site_polygon = [tuple(p) for p in site_polygon]

    sim = Simulation(
        bounds=tuple(g["bounds"]), ods=ods, gridsize=g["gridsize"],
        buildings=buildings, obstacles=obstacles, site_polygon=site_polygon,
        rivers=rivers, season=Season(geo.get("season", "normal")),
        topography=topo, terrain_cost=TerrainCost(**meta.get("terrain_cost", {})),
        seed=seed, cost_field_provider=provider, **params,
    )
    if meta.get("layers") and blob is not None:
        from .layers import Layer

        for item in meta["layers"]:
            layer = Layer(item["name"], _read(blob, arrays[item["array"]]),
                          weight=float(item.get("weight", 1.0)), kind=item["kind"],
                          color=tuple(item.get("color", (120, 120, 120))),
                          description=item.get("description", ""))
            layer.phase_ids = list(item.get("phase_ids") or [])
            sim.grid.layers.add(layer)
        # walls change what is walkable; the routes still come from the pack
        sim.grid.refresh_layers(force=True)
        sim._build_cost_fields()
    if meta.get("nested"):
        from .nested import NestedConfig

        cfg = dict(meta["nested"])
        cfg["marked"] = [tuple(r) for r in cfg.get("marked", [])]
        sim.nested = NestedConfig(**cfg)
        sim._build_cost_fields()        # patches rebuilt here; routes from the pack
    sim.pack_seed = seed
    sim.respawn_at_origin = respawn
    sim._packed_research = (phases, geo, meta.get("research", {}))
    return sim, state


def _apply_research(sim: Simulation) -> None:
    phases, geo, research = sim._packed_research
    r = sim.research
    r.phases = list(phases)
    pop = geo.get("population") or {}
    if pop:
        r.population_rule = pop.get("rule", r.population_rule)
        r.persons_per_house = float(pop.get("persons_per_house", 5))
        r.persons_per_m2 = float(pop.get("persons_per_m2", 0.1))
        r.agents_per_person = pop.get("agents_per_person")
    r.phase_mode = geo.get("phase_mode", r.phase_mode)
    if geo.get("active_phases") is not None and r.phases:
        r.manual_phase_ids = list(geo["active_phases"])
    r.scenario_ref = geo.get("scenario_ref", "") or ""
    r.respect_chronology = bool(research.get("respect_chronology", False))
    window = research.get("window")
    if window:
        r.window = Interval(int(window[0]), int(window[1]))
    r.tau = int(research.get("tau", 0))
    r.undated_policy = research.get("undated_policy", r.undated_policy)


def _nearest_on_ring(pts, point) -> Tuple[float, float]:
    """Closest point to ``point`` on the closed polygon ``pts``."""
    best, best_d = point, float("inf")
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 <= 0 else min(1.0, max(
            0.0, ((point[0] - x0) * dx + (point[1] - y0) * dy) / length2))
        q = (x0 + t * dx, y0 + t * dy)
        d = math.hypot(point[0] - q[0], point[1] - q[1])
        if d < best_d:
            best, best_d = q, d
    return best


# --------------------------------------------------------------------- engine
class LiveEngine:
    """One loaded scene and the operations a thin client may ask for."""

    def __init__(self) -> None:
        self.meta: Optional[dict] = None
        self.blob = None
        self.sim: Optional[Simulation] = None
        self.frame: Optional[BilinearFrame] = None
        self.analysis = "path"
        self.version = 0
        self._sent_version = -1
        self._costs: dict = {}
        self._isovist: Optional[List[List[float]]] = None
        self._toggles: dict = {}

    # ------------------------------------------------------------------ load
    def load(self, meta: dict, blob=None, num_agents: Optional[int] = None) -> dict:
        self.meta = meta
        self.blob = blob
        self.frame = BilinearFrame.from_dict(meta["georef"])
        sim, state = build_simulation(meta, blob, num_agents=num_agents)
        self.sim = sim
        self._costs = state
        _apply_research(sim)
        state["ready"] = True
        if phase_key(sim) != "*":
            # geometry was rasterised with every phase on; narrow it now
            sim.apply_phase_filter()
        self.analysis = "path"
        self._isovist = None
        self._toggles = {}
        self._touch()
        return self.describe()

    def reset(self) -> dict:
        """Back to the scene as packed, dropping every edit."""
        if self.meta is None:
            raise RuntimeError("no scene loaded")
        agents = self.sim.num_agents if self.sim else None
        toggles = dict(self._toggles)
        out = self.load(self.meta, self.blob, num_agents=agents)
        if toggles:
            self.set_toggles(toggles)
            out = self.describe()
        return out

    def _touch(self) -> None:
        self.version += 1

    def _routing_edited(self) -> None:
        """Walls, rivers or layers changed: packed cost fields no longer apply."""
        self._costs["pristine"] = False

    def _od_edited(self, index: int) -> None:
        self._costs["valid"].discard(index)

    # ----------------------------------------------------------------- state
    def describe(self) -> dict:
        """Everything the client draws that is not per-step."""
        sim = self.sim
        r = sim.research
        active = r.current_phase_ids()
        ods = []
        for k, od in enumerate(sim.ods):
            if od is None:
                continue
            lon, lat = self.frame.to_lonlat(od.x, od.y)
            site_name = od.site or od.name
            ods.append({
                "index": k, "name": od.name, "kind": od.kind or "site",
                "site": od.site, "group": od.group,
                "phase_ids": list(od.phase_ids),
                "coordinates": [float(lon), float(lat)],
                "origin_weight": od.origin_weight, "dest_weight": od.dest_weight,
                "active": bool(r.phase_allows(od.phase_ids) and r.site_is_active(site_name)),
            })
        buildings = []
        for k, b in enumerate(sim.buildings):
            buildings.append({
                "index": k, "name": b.function, "function": b.function,
                "height": b.height, "state": b.state,
                "phase_ids": list(b.phase_ids),
                "active": bool(r.phase_allows(b.phase_ids)),
                "ring": self._ring(b.footprint.as_xy()),
                "inner": self._inner_ring(b),
                "door": self._lonlat(b.door) if b.door else None,
            })
        obstacles = [
            {"index": k, "layer": o.layer, "phase_ids": list(getattr(o, "phase_ids", [])),
             "ring": self._ring(o.footprint.as_xy())}
            for k, o in enumerate(sim.obstacles)
        ]
        rivers = []
        for rv in sim.rivers:
            xs = [p[0] for p in rv.path]
            ys = [p[1] for p in rv.path]
            lon, lat = self.frame.to_lonlat(xs, ys)
            rivers.append({
                "name": rv.name, "perennial": rv.perennial,
                "coordinates": [[float(a), float(b)] for a, b in zip(lon, lat)],
            })
        sites = []
        for s in self.meta.get("sites", []):
            item = dict(s)
            item["active"] = bool(r.site_is_active(s["name"]))
            item["flagged"] = bool(r.site_is_flagged(s["name"]))
            item["walking"], item["reason"] = self._site_state(s)
            sites.append(item)
        corners = self.frame.corners_lonlat()
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        clon, clat = self.frame.to_lonlat(
            (self.frame.min_x + self.frame.max_x) / 2.0,
            (self.frame.min_y + self.frame.max_y) / 2.0)
        return {
            "id": self.meta["id"], "name": self.meta["name"],
            "scale": self.meta["scale"], "site": self.meta.get("site", ""),
            "note": self.meta.get("note", ""),
            "engine": "pedsim live",
            "version": self.version,
            "corners": corners,
            "bounds": {"west": min(lons), "east": max(lons),
                       "south": min(lats), "north": max(lats)},
            "center": [float(clon), float(clat)],
            "zoom": self.meta.get("zoom", 16),
            "grid": {"nx": sim.grid.nx, "ny": sim.grid.ny, "gridsize": sim.grid.gridsize},
            "nested": None if sim.nested is None else {
                "fine": sim.nested.fine, "patches": len(sim.patches),
                "fine_cells": int(sum(p.grid.nx * p.grid.ny for p in sim.patches)),
                "notes": list(sim.nested_notes),
                "rings": [self._ring([(p.bounds[0], p.bounds[1]), (p.bounds[2], p.bounds[1]),
                                      (p.bounds[2], p.bounds[3]), (p.bounds[0], p.bounds[3])])
                          for p in sim.patches],
            },
            "phases": [
                {"id": p.id, "name": p.name, "start_bc": p.start_bc, "end_bc": p.end_bc,
                 "colour": p.colour, "confidence": p.confidence,
                 "active": active is None or p.id in active}
                for p in r.phases
            ],
            "active": list(active or []),
            "ods": ods, "buildings": buildings, "obstacles": obstacles,
            "rivers": rivers, "sites": sites,
            "season": sim.season.value,
            "num_agents": sim.num_agents,
            "population": sim.population_label(),
            "hud": r.hud_lines(sim.population_label()),
            "edited": not self._costs.get("pristine", True),
            "terrain_weight": sim.terrain_weight,
            "river_weight": sim.river_weight,
            "undated": r.undated_policy,
            "tau": r.tau,
        }

    def _site_state(self, site: dict) -> Tuple[bool, str]:
        """Does this site send walkers now, and if not, why not."""
        sim = self.sim
        r = sim.research
        od = next((o for o in sim.ods if o is not None
                   and (o.site or o.name) == site["name"]), None)
        if not site.get("usable", True) or od is None:
            return False, "no usable coordinate"
        if not r.site_is_active(site["name"]):
            if site.get("start_bc") is None or site.get("end_bc") is None:
                return False, "undated, and undated sites are excluded"
            return False, (f"occupied {site['start_bc']}–{site['end_bc']} BC, "
                           "outside the time window")
        if r.origin_weight(od) <= 0:
            return False, "switched off"
        partners = any(o is not None and o is not od and r.dest_weight(od, o) > 0
                       for o in sim.ods)
        if not partners:
            return False, "no other site is occupied at the same time in this window"
        return True, ""

    def _lonlat(self, point) -> List[float]:
        lon, lat = self.frame.to_lonlat(point[0], point[1])
        return [float(lon), float(lat)]

    def _inner_ring(self, b) -> Optional[List[List[float]]]:
        """Inside face of a hollow building's wall, for drawing it at its true
        thickness. ``None`` for a solid footprint."""
        if b.wall_m is None:
            return None
        pts = b.footprint.as_xy()
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        # the apothem: distance from the centre to the nearest wall line
        from .rivers import distance_field
        closed = [(p[0], p[1]) for p in pts] + [(pts[0][0], pts[0][1])]
        apothem = float(distance_field(np.array([cx]), np.array([cy]), closed)[0, 0])
        if apothem <= b.wall_m:
            return None
        k = 1.0 - b.wall_m / apothem
        return self._ring([(cx + (p[0] - cx) * k, cy + (p[1] - cy) * k) for p in pts])

    def _ring(self, pts) -> List[List[float]]:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lon, lat = self.frame.to_lonlat(xs, ys)
        ring = [[float(a), float(b)] for a, b in zip(lon, lat)]
        if ring and ring[0] != ring[-1]:
            ring.append(list(ring[0]))
        return ring

    # ------------------------------------------------------------------ step
    def step(self, n: int = 1) -> None:
        for _ in range(max(1, int(n))):
            self.sim.step()

    def snapshot(self) -> dict:
        """The per-step picture. Arrays are ``bytes`` so a worker can transfer them."""
        sim = self.sim
        grid = sim.grid
        act = sim.active_agents
        if act:
            # each walker is on its own grid (a nested scene has several)
            wx = np.fromiter((a.grid.sx + a.px * a.grid.gridsize for a in act),
                             dtype=float, count=len(act))
            wy = np.fromiter((a.grid.sy + a.py * a.grid.gridsize for a in act),
                             dtype=float, count=len(act))
            lon, lat = self.frame.to_lonlat(wx, wy)
            agents = np.column_stack([lon, lat]).astype("<f8")
            groups = np.fromiter((a.group for a in act), dtype="<u1", count=len(act))
            slot = {id(a): k for k, a in enumerate(sim.agents)}
            ids = np.fromiter((slot[id(a)] for a in act), dtype="<u2", count=len(act))
            ages = np.fromiter((min(a.age, 65535) for a in act), dtype="<u2", count=len(act))
        else:
            agents = np.zeros((0, 2), dtype="<f8")
            groups = np.zeros((0,), dtype="<u1")
            ids = np.zeros((0,), dtype="<u2")
            ages = np.zeros((0,), dtype="<u2")

        field = self._grid_field(grid)
        if self.analysis not in ("facade", "facadeO"):
            field = sim.display_occupancy()[0][None]
        channels = field.shape[0]
        image = self._image(field)
        patches = []
        peak = float(image.max()) if image.size else 0.0
        if sim.patches:
            g = grid
            width = g.nx * g.gridsize
            height = g.ny * g.gridsize
            for patch in sim.patches:
                # a fine walker marks ``ratio`` cells a tick where a coarse one
                # marks one: scale so both read as walkers per tick
                picture = np.transpose(self._grid_field(patch.grid) / sim.nested_ratio,
                                       (0, 2, 1))[:, ::-1, :]
                peak = max(peak, float(picture.max()) if picture.size else 0.0)
                b = patch.bounds
                patches.append({
                    # where it sits in the scene picture, as fractions from the top left
                    "x0": (b[0] - g.min_x) / width, "x1": (b[2] - g.min_x) / width,
                    "y0": 1.0 - (b[3] - g.min_y) / height, "y1": 1.0 - (b[1] - g.min_y) / height,
                    "nx": int(picture.shape[2]), "ny": int(picture.shape[1]),
                    "field": np.ascontiguousarray(picture).astype("<f4").tobytes(),
                })
        out = {
            "type": "frame",
            "scene": self.meta["id"],
            "step": sim.ticks,
            "analysis": self.analysis,
            "n_agents": int(len(act)),
            "agents": agents.tobytes(),
            "groups": groups.tobytes(),
            # slot of each walker, so a client can tween the same one between frames
            "ids": ids.tobytes(),
            # ticks since each walker set out: a small age means it just respawned
            "ages": ages.tobytes(),
            "channels": channels,
            "nx": int(image.shape[2]), "ny": int(image.shape[1]),
            "field": image.astype("<f4").tobytes(),
            "max": peak,
            "season": sim.season.value,
            "daylight": round(float(sim.research.daylight_minutes), 1),
            "version": self.version,
        }
        if patches:
            out["patches"] = patches
        if self.analysis in ("traces", "tracesO"):
            out["traces"] = self._traces()
        if self._isovist is not None:
            out["isovist"] = self._isovist
        if self.version != self._sent_version:
            out["describe"] = self.describe()
            walls = self._wall_image()
            if walls is not None:
                out["walls"] = walls.tobytes()
                out["walls_nx"] = int(walls.shape[1])
                out["walls_ny"] = int(walls.shape[0])
            self._sent_version = self.version
        return out

    def _grid_field(self, grid) -> np.ndarray:
        """``(c, nx, ny)`` of what the current analysis mode shows on one grid."""
        if self.analysis == "facade":
            return np.where(grid.boundary, grid.visibility, 0.0)[None]
        if self.analysis == "facadeO":
            vis = np.where(grid.boundary[:, :, None], grid.visibility_o, 0.0)
            return np.moveaxis(vis, 2, 0)[:3]
        return grid.occupancy[None]

    def _image(self, field: np.ndarray) -> np.ndarray:
        """``(c, nx, ny)`` grid arrays -> ``(c, rows, cols)`` with north on top."""
        c, nx, ny = field.shape
        stride = max(1, int(math.ceil(max(nx, ny) / MAX_FIELD_SIDE)))
        if stride > 1:
            px = (-nx) % stride
            py = (-ny) % stride
            padded = np.pad(field, ((0, 0), (0, px), (0, py)))
            field = padded.reshape(c, (nx + px) // stride, stride,
                                   (ny + py) // stride, stride).max(axis=(2, 4))
        return np.transpose(field, (0, 2, 1))[:, ::-1, :]

    def _wall_image(self) -> Optional[np.ndarray]:
        """RGBA picture of the blocking layers that are on, north at the top,
        one pixel per cell: walls read from a plan, in their phase colours."""
        grid = self.sim.grid
        layers = [layer for layer in packed_layers(self.sim)
                  if layer.kind == "block" and layer.enabled]
        if not layers:
            return None if not packed_layers(self.sim) else np.zeros((1, 1, 4), dtype="u1")
        image = np.zeros((grid.nx, grid.ny, 4), dtype="u1")
        for layer in layers:
            mask = layer.data > 0
            image[mask, :3] = layer.color
            image[mask, 3] = 255
        return np.ascontiguousarray(np.transpose(image, (1, 0, 2))[::-1])

    def _traces(self) -> List[dict]:
        lines = []
        for tr in self.sim.traces:
            if not tr.draw_me or len(tr.points) < 2:
                continue
            xs = [p[0] for p in tr.points]
            ys = [p[1] for p in tr.points]
            lon, lat = self.frame.to_lonlat(xs, ys)
            lines.append({
                "group": int(tr.start_group),
                "coordinates": [[round(float(a), 7), round(float(b), 7)]
                                for a, b in zip(lon, lat)],
            })
        return lines

    # --------------------------------------------------------------- toggles
    def set_toggles(self, toggles: dict) -> None:
        """Chronology window, phases, season, analysis mode, agent count."""
        sim = self.sim
        r = sim.research
        self._toggles.update(toggles)
        before_phase = phase_key(sim)

        if "chronology" in toggles:
            r.respect_chronology = bool(toggles["chronology"])
            if r.phases:
                r.phase_mode = "by_time" if r.respect_chronology else "manual"
        if "startBc" in toggles or "endBc" in toggles:
            start = int(toggles.get("startBc", r.window.start_bc))
            end = int(toggles.get("endBc", r.window.end_bc))
            if start < end:
                start, end = end, start
            r.window = Interval(end, start)
        if "tau" in toggles:
            r.tau = max(0, int(toggles["tau"]))
        if "undated" in toggles:
            r.undated_policy = str(toggles["undated"])
        if "overrides" in toggles:
            r.phase_overrides = {
                k: ("on" if v else "off") for k, v in (toggles["overrides"] or {}).items()
            }
        if "phases" in toggles and r.phases and r.phase_mode == "manual":
            chosen = toggles["phases"] or {}
            r.manual_phase_ids = [p.id for p in r.phases if chosen.get(p.id, True)]
        if phase_key(sim) != before_phase:
            sim.apply_phase_filter()

        if "season" in toggles and toggles["season"]:
            season = Season(toggles["season"])
            if season != sim.season:
                if sim.rivers:
                    sim.set_season(season)
                else:
                    sim.season = season
            month = SEASON_MONTH.get(season.value)
            cal = r.calendar()
            if month and cal is not None:
                info = cal.month(month)
                r.month = info.number
                r.daylight_minutes = info.daylight_minutes
                r.task_weights = dict(info.task_weights)
        if "terrainWeight" in toggles:
            w = float(toggles["terrainWeight"])
            if abs(w - sim.terrain_weight) > 1e-9:
                sim.set_terrain_weight(w)
        if "riverWeight" in toggles:
            w = float(toggles["riverWeight"])
            if abs(w - sim.river_weight) > 1e-9:
                if sim.rivers:
                    sim.set_river_weight(w)
                else:
                    sim.river_weight = w
        if ("analysis" in toggles and toggles["analysis"] in ANALYSIS_BY_NAME
                and toggles["analysis"] != self.analysis):
            # switching mode clears the analysis fields, so only on a real change
            self.analysis = toggles["analysis"]
            sim.set_analysis_mode(ANALYSIS_BY_NAME[self.analysis])
        if "agents" in toggles:
            self.set_agents(int(toggles["agents"]))
        if "isovist" in toggles and not toggles["isovist"]:
            self._isovist = None
        self._touch()

    def set_agents(self, n: int) -> None:
        from .agent import Agent

        sim = self.sim
        n = max(1, min(int(n), 2000))
        if n > len(sim.agents):
            sim.agents.extend(Agent(sim) for _ in range(n - len(sim.agents)))
        else:
            for a in sim.agents[n:]:
                a.active = False
            del sim.agents[n:]
        sim.num_agents = n

    # ----------------------------------------------------------------- edits
    def _local(self, lon: float, lat: float) -> Tuple[float, float]:
        x, y = self.frame.to_local(lon, lat)
        return float(x), float(y)

    def _nearest_od(self, lon: float, lat: float, limit_cells: float = 12.0) -> int:
        x, y = self._local(lon, lat)
        best, best_d = -1, float("inf")
        for k, od in enumerate(self.sim.ods):
            if od is None:
                continue
            d = math.hypot(od.x - x, od.y - y)
            if d < best_d:
                best, best_d = k, d
        if best_d > limit_cells * self.sim.grid.gridsize:
            return -1
        return best

    def add_od(self, lon: float, lat: float, weight: float = 1.0,
               kind: str = "destination", name: str = "",
               phase_ids: Optional[Sequence[str]] = None) -> int:
        x, y = self._local(lon, lat)
        grid = self.sim.grid
        if not (grid.min_x <= x <= grid.max_x and grid.min_y <= y <= grid.max_y):
            return -1
        w = min(max(float(weight), 0.0), 1.0)
        n = sum(1 for o in self.sim.ods if o is not None)
        k = self.sim.add_od(x, y, origin_weight=w, dest_weight=w, kind=kind,
                            name=name or f"OD {n + 1}", phase_ids=phase_ids)
        self._od_edited(k)
        self._touch()
        return k

    def delete_od(self, lon: float, lat: float) -> int:
        k = self._nearest_od(lon, lat)
        if k < 0:
            return -1
        for a in self.sim.agents:
            if a.home == k:
                a.home = -1
            if a.active and (a.target == k or a.origin == k):
                a.active = False
        self.sim.delete_od(k)
        self._od_edited(k)
        self._touch()
        return k

    def weight_od(self, lon: float, lat: float, step: float = 0.25) -> int:
        k = self._nearest_od(lon, lat)
        if k < 0:
            return -1
        od = self.sim.ods[k]
        w = od.dest_weight + step
        if w > 1.0 + 1e-9:
            w = step
        self.sim.weight_od(k, origin_weight=w, dest_weight=w)
        self._touch()
        return k

    def move_od(self, index: int, lon: float, lat: float) -> None:
        x, y = self._local(lon, lat)
        self.sim.move_od(int(index), x, y)
        self._od_edited(int(index))
        self._touch()

    def add_building(self, ring: Sequence[Sequence[float]], door=None,
                     function: str = "domestic", height: float = 3.0,
                     phase_ids: Optional[Sequence[str]] = None,
                     wall_m: Optional[float] = 0.4) -> int:
        """Add a building from a lon/lat ring.

        By default it is hollow: a ``wall_m`` thick wall around a room, open at
        ``door`` (a lon/lat point on the wall). The household's place goes in
        the room, or just outside the door when the room is too small to hold a
        cell. ``wall_m=None`` gives a solid footprint with its place outside.
        """
        sim = self.sim
        pts = [self._local(p[0], p[1]) for p in ring]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        gate = self._local(door[0], door[1]) if door is not None else None
        if gate is not None:
            # put the opening on the wall line itself, wherever the tap landed
            gate = _nearest_on_ring(pts, gate)
        self._routing_edited()
        # the building and its place are one edit: solve the routes once, after both
        sim.hold_routes()
        sim.add_building(pts, height=height, function=function, phase_ids=phase_ids,
                         wall_m=wall_m, door=gate if wall_m is not None else None)
        if sim.nested is not None:
            from . import nested as _nested
            _nested.rebuild(sim)            # so "is the room walkable" asks the fine grid
        name = f"house {len(sim.buildings)}"
        grid = sim.grid
        if sim.patches:
            from .nested import level_at
            level = level_at(sim, cx, cy)
            if level:
                grid = sim.patches[level - 1].grid
        inside = grid.is_walkable(grid.cell_x(cx), grid.cell_y(cy)) and wall_m is not None
        if inside:
            spot = (cx, cy)
        elif gate is not None:
            # step out from the wall, away from the centre
            dx, dy = gate[0] - cx, gate[1] - cy
            norm = math.hypot(dx, dy) or 1.0
            out = 2.0 * grid.gridsize
            spot = (gate[0] + dx / norm * out, gate[1] + dy / norm * out)
        else:
            spot = None
        if spot is not None:
            k = sim.add_od(spot[0], spot[1], origin_weight=1.0, dest_weight=1.0,
                           kind="house", name=name, phase_ids=phase_ids)
            self._od_edited(k)
        sim.release_routes()
        self._touch()
        return len(sim.buildings) - 1

    def delete_building(self, lon: float, lat: float) -> int:
        from .geometry import point_in_polygon

        x, y = self._local(lon, lat)
        for k, b in enumerate(self.sim.buildings):
            if point_in_polygon(x, y, b.footprint.as_xy()):
                self._routing_edited()
                self.sim.delete_building(b)
                self._touch()
                return k
        return -1

    def isovist(self, lon: float, lat: float) -> List[List[float]]:
        x, y = self._local(lon, lat)
        iso = self.sim.compute_isovist(x, y)
        self._isovist = self._ring(iso.polygon())
        return self._isovist

    def reset_analysis(self) -> None:
        self.sim.reset_analysis()

    def restart(self) -> None:
        """Start the run again: clear the heat, traces and walkers, keep every
        edit. The walkers set out afresh from newly drawn places."""
        sim = self.sim
        sim.reset_analysis()
        for a in sim.agents:
            a.active = False
            a.home = -1
        sim.traces.clear()
        sim.category_occupancy.clear()
        sim.ticks = 0
        self._isovist = None
        self._touch()

    # ------------------------------------------------------------ save / load
    def export_geometry(self) -> dict:
        """The desktop save format, plus where it belongs."""
        data = self.sim.geometry_dict()
        data["scene"] = {"id": self.meta["id"], "name": self.meta["name"],
                         "site": self.meta.get("site", ""),
                         "georef": self.frame.to_dict()}
        return data

    def apply_geometry(self, data: dict) -> dict:
        """Load a save made here or by the desktop viewer for the same scene."""
        self._routing_edited()
        self._costs["valid"].clear()
        self.sim.load_geometry_dict(data)
        for a in self.sim.agents:
            a.active = False
        self._touch()
        return self.describe()

    # --------------------------------------------------------------- commands
    def command(self, name: str, payload: Optional[dict] = None) -> dict:
        """One client request by name; always answers with a :meth:`snapshot`.

        This is the whole protocol between a thin client and the model, so the
        browser worker and the laptop hub cannot drift apart.
        """
        p = payload or {}
        if name == "step":
            self.step(int(p.get("n", 1)))
        elif name == "toggles":
            self.set_toggles(p)
        elif name == "reset":
            self.reset()
        elif name == "resetAnalysis":
            self.reset_analysis()
        elif name == "restart":
            self.restart()
        elif name == "addOd":
            self.add_od(p["lon"], p["lat"], p.get("weight", 1.0),
                        p.get("kind", "destination"), p.get("name", ""))
        elif name == "deleteOd":
            self.delete_od(p["lon"], p["lat"])
        elif name == "weightOd":
            self.weight_od(p["lon"], p["lat"])
        elif name == "addBuilding":
            self.add_building(p["ring"], p.get("door"), p.get("function", "domestic"),
                              float(p.get("height", 3.0)), p.get("phase_ids"),
                              p.get("wall_m", 0.4))
        elif name == "deleteBuilding":
            self.delete_building(p["lon"], p["lat"])
        elif name == "isovist":
            self.isovist(p["lon"], p["lat"])
        elif name == "applyGeometry":
            self.apply_geometry(p["geometry"])
        elif name != "snapshot":
            raise ValueError(f"unknown command {name!r}")
        return self.snapshot()

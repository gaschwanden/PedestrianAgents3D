"""Interactive real-time viewer (pygame).

A top-down, live viewer for a :class:`~pedsim.simulation.Simulation` -- the
interactive counterpart of the original OpenGL sketch. It runs the simulation in
real time and lets you pan/zoom the camera, switch analysis modes, edit the
scene by clicking, and drop an isovist viewpoint.

Controls
--------
Simulation:   SPACE play/pause   .  single step   [ / ] slower/faster
Camera:       arrow keys / right-drag pan    mouse wheel or +/- zoom    F fit view
Analysis:     0 none  1 path-overlap  2 facade-vis  3 facade-vis(by group)
              4 traces  5 traces(by group)    C reset analysis
Layers:       L cycle the displayed landscape layer (Shift+L backwards); over the
              control pane the wheel picks a layer, Shift+wheel re-weights it (and
              re-routes), Ctrl+wheel changes the overlay opacity
Tools:        O add source-OD   K add sink-OD   X delete (OD/building)
              B draw building (click vertices, ENTER to close, ESC to cancel)
              I isovist follows the mouse (toggle)   V none/pan tool
Misc:         H toggle help    Q / ESC quit

The class also exposes methods (``set_analysis_mode``, ``add_source`` ...) so a
script can drive it headlessly for recording (see ``examples/run_viewer.py``).
"""
from __future__ import annotations

import math
import os
from typing import Callable, List, Optional, Tuple

import numpy as np

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from .simulation import (  # noqa: E402
    ANALYSIS_FACADE_VIS,
    ANALYSIS_FACADE_VIS_O,
    ANALYSIS_NONE,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ANALYSIS_TRACES_O,
    Simulation,
)

_GROUP_COLORS = [(255, 150, 0), (57, 211, 83), (74, 163, 255), (255, 93, 93), (199, 125, 255)]
_LAYER_COLORS = {
    "WATERBODY": (39, 75, 107),
    "STREETS": (58, 63, 71),
    "OBSTACLES_LOW": (57, 65, 43),
    "OBSTACLES_HIGH": (74, 63, 43),
    "PARK": (43, 74, 43),
}
_MODE_NAME = {
    ANALYSIS_NONE: "none",
    ANALYSIS_PATHOVERLAP: "path-overlap",
    ANALYSIS_FACADE_VIS: "facade-visibility",
    ANALYSIS_FACADE_VIS_O: "facade-visibility (group)",
    ANALYSIS_TRACES: "traces",
    ANALYSIS_TRACES_O: "traces (group)",
}


def _terrain_rgb(elev: np.ndarray) -> np.ndarray:
    """Map an elevation array to an RGB uint8 array using matplotlib's terrain."""
    import matplotlib as mpl

    lo, hi = float(np.nanmin(elev)), float(np.nanmax(elev))
    norm = (elev - lo) / (hi - lo) if hi > lo else np.zeros_like(elev)
    rgba = mpl.colormaps["terrain"](norm)
    return (rgba[..., :3] * 255).astype(np.uint8)


class Viewer:
    def __init__(self, sim: Simulation, site=None, width: int = 1280, height: int = 800,
                 steps_per_frame: int = 1, fps: int = 30, title: str = "pedsim viewer",
                 app=None):
        import pygame

        self.pygame = pygame
        self.sim = sim
        self.site = site
        self.W = width
        self.H = height
        self.steps_per_frame = steps_per_frame
        self.fps = fps

        pygame.init()
        pygame.display.set_caption(title)
        self.screen = pygame.display.set_mode((width, height))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 20)
        self.bigfont = pygame.font.Font(None, 26)

        # state
        self.playing = True
        self.tool = "pan"
        self.draft_poly: List[Tuple[float, float]] = []
        self.close_radius_px = 12          # click within this of the 1st vertex closes
        self._last_click_ms = 0            # for double-click-to-close detection
        self._last_click_pos = (0, 0)
        self.show_help = True
        self.isovist_follow = False
        self.running = True
        self.frame = 0

        # bottom control pane (port of the Java top-left button toolbar)
        self.save_dir = os.getcwd()
        self.status_msg = ""
        self.status_ttl = 0
        self._carry = None          # (building, kind) currently being moved
        self._carry_anchor = (0.0, 0.0)
        self.panel_h = 0
        self.buttons: List[dict] = []
        self._row_labels: List[Tuple[int, int, str]] = []
        self.tab_rects: List[Tuple[str, object]] = []
        self.top_buttons: List[Tuple[str, object]] = []
        self.prompt_buttons: List[Tuple[Optional[bool], object]] = []
        self.active_tab = self.TABS[0]
        self.od_kind = "water"
        self.selected_buildings: List = []
        self._lasso_anchor = None
        # circle / rectangle wizard: (shape, step, point_a, point_b)
        # steps: centre|corner → rim|opposite → door
        self._template = None

        # landscape layers: which one is drawn, and the cached button layout
        self.layer_views: List[dict] = []
        self.active_layer = -1      # index into layer_views; -1 = none displayed
        self.layer_alpha = 0.55     # keep the map underneath readable
        self._controls_sig = None

        # two-scale navigation, edit state and the modal question
        self.app = app
        if app is not None:
            self.save_dir = app.save_dir
        self.selected_site = ""     # settlement picked in the cluster view
        self.dirty = False
        self.prompt: Optional[dict] = None
        self._site_markers: List[Tuple[str, int, int]] = []

        # shaded relief, built per scene and shown only when its layer is on
        self._terrain_surf = None
        self._build_terrain_surface()
        self._build_controls()

        # camera (vertical extent excludes the top bar and the control pane)
        self.scale = 1.0
        self.cx = 0.0
        self.cy = 0.0
        self.angle = 0.0            # yaw about the vertical axis (radians)
        self.pitch = 0.0            # camera tilt (0 = top-down)
        self.fit_view()

    #: Height of the scale/season bar across the top.
    TOP_H = 32

    def _build_terrain_surface(self) -> None:
        """(Re)build the shaded-relief raster for the current scene."""
        pygame = self.pygame
        self._terrain_surf = None
        if self.sim.grid.elevation is not None:
            rgb = _terrain_rgb(self.sim.grid.elevation)      # [ix, iy, 3]
            surf = pygame.surfarray.make_surface(rgb)
            self._terrain_surf = pygame.transform.flip(surf, False, True)

    def set_simulation(self, sim: Simulation) -> None:
        """Swap in another scene, resetting everything tied to the old one.

        Used by the two-scale navigation: the cluster and each village are
        separate simulations, and the camera, layer selection and draft geometry
        all belong to whichever is on screen.
        """
        self.sim = sim
        self.draft_poly = []
        self._carry = None
        self.selected_site = ""
        self.active_layer = -1
        self.layer_views = []
        self._build_terrain_surface()
        self._build_controls()
        self.fit_view()

    # ------------------------------------------------------------ transforms
    @property
    def view_h(self) -> int:
        """Height of the map viewport (screen minus the top bar and the pane)."""
        return self.H - self.panel_h - self.TOP_H

    @property
    def view_cy(self) -> float:
        """Vertical screen centre of the map viewport."""
        return self.TOP_H + self.view_h / 2.0

    MAX_PITCH = math.radians(80)

    def fit_view(self) -> None:
        g = self.sim.grid
        dx = max(g.max_x - g.min_x, 1e-6)
        dy = max(g.max_y - g.min_y, 1e-6)
        self.scale = 0.9 * min(self.W / dx, self.view_h / dy)
        self.cx = (g.min_x + g.max_x) / 2.0
        self.cy = (g.min_y + g.max_y) / 2.0
        self.angle = 0.0            # yaw (about the vertical axis)
        self.pitch = 0.0            # tilt (0 = top-down)

    def rotate_by(self, delta: float) -> None:
        """Yaw the scene about the vertical axis by ``delta`` radians."""
        self.angle = (self.angle + delta) % (2 * math.pi)

    def tilt_by(self, delta: float) -> None:
        """Tilt (pitch) the camera by ``delta`` radians, clamped to [0, 80deg]."""
        self.pitch = min(max(self.pitch + delta, 0.0), self.MAX_PITCH)

    def _yaw_depth(self, wx: float, wy: float) -> float:
        """Yaw-rotated depth (screen 'into the distance' axis) of a world point."""
        dx, dy = wx - self.cx, wy - self.cy
        return dx * math.sin(self.angle) + dy * math.cos(self.angle)

    def to_screen(self, wx: float, wy: float, wz: float = 0.0) -> Tuple[int, int]:
        """Axonometric projection: yaw in-plane, then pitch foreshortens depth and
        lifts height ``wz`` toward the top of the screen."""
        dx, dy = wx - self.cx, wy - self.cy
        if self.angle:
            c, s = math.cos(self.angle), math.sin(self.angle)
            dx, dy = dx * c - dy * s, dx * s + dy * c
        sp = math.sin(self.pitch)
        cp = math.cos(self.pitch)
        sx = self.W / 2 + dx * self.scale
        sy = self.view_cy - dy * cp * self.scale - wz * sp * self.scale
        return int(sx), int(sy)

    def to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        """Inverse projection onto the ground plane (z = 0)."""
        cp = math.cos(self.pitch) or 1e-6
        dx = (sx - self.W / 2) / self.scale
        dy = (self.view_cy - sy) / (self.scale * cp)
        if self.angle:
            c, s = math.cos(-self.angle), math.sin(-self.angle)
            dx, dy = dx * c - dy * s, dx * s + dy * c
        return self.cx + dx, self.cy + dy

    # ----------------------------------------------------------- control pane
    # Panel metrics. Every button is the same width, so the pane reads as a grid
    # instead of a ragged row of differently-sized boxes.
    PAD = 10
    BTN_W = 116
    BTN_H = 24
    GAP = 6
    TAB_H = 24
    BTN_ROWS = 2          # fixed, so the panel height never jumps between tabs

    TABS = ("Analysis", "Edit", "Water", "Layers", "View", "Data", "Research")

    def _tab_specs(self, tab: str) -> List[Tuple]:
        """Buttons for one tab, as ``(kind, label, payload[, widest_label])``."""
        if tab == "Analysis":
            return [
                ("mode", "none", ANALYSIS_NONE),
                ("mode", "path overlap", ANALYSIS_PATHOVERLAP),
                ("mode", "facade vis", ANALYSIS_FACADE_VIS),
                ("mode", "facade group", ANALYSIS_FACADE_VIS_O),
                ("mode", "traces", ANALYSIS_TRACES),
                ("mode", "traces group", ANALYSIS_TRACES_O),
                ("action", "reset analysis", "reset_analysis"),
                ("action", "reset all", "reset_all"),
            ]
        if tab == "Edit":
            return [
                ("tool", "source OD", "od_source"),
                ("tool", "sink OD", "od_sink"),
                ("tool", "OD weight", "od_weight"),
                ("tool", "delete OD", "od_delete"),
                ("tool", "add building", "bd_add"),
                ("tool", "B circle", "bd_circle"),
                ("tool", "B rect", "bd_rect"),
                ("tool", "move building", "bd_move"),
                ("tool", "height", "bd_height"),
                ("tool", "delete building", "bd_delete"),
                ("tool", "add obstacle", "ob_add"),
                ("tool", "move obstacle", "ob_move"),
                ("tool", "delete obstacle", "ob_delete"),
                ("tool", "pan / select", "pan"),
                ("tool", "lasso", "lasso"),
                ("action", "OD kind", "od_kind"),
            ]
        if tab == "Water":
            return [
                ("tool", "add river", "rv_add"),
                ("tool", "add ford", "rv_ford"),
                ("tool", "delete river", "rv_delete"),
                ("tool", "toggle flow", "rv_perennial"),
                ("action", "season >", "season_next", "season: spring floods"),
                ("action", "dry", "season_dry"),
                ("action", "normal", "season_normal"),
                ("action", "spring floods", "season_flood"),
            ]
        if tab == "Layers":
            specs = []
            for i, v in enumerate(self.layer_views):
                # reserve room for the weight readout adjustable layers show
                widest = v["name"] + (" x0.00" if v["layer"] is not None else "")
                specs.append(("layer", v["name"], i, widest))
            specs.append(("layer", "off", -1))
            return specs
        if tab == "View":
            return [
                ("action", "fit view", "fit"),
                ("toggle", "isovist", "isovist"),
                ("action", "top-down", "view_top"),
                ("action", "3/4 view", "view_iso"),
                ("action", "rotate left", "yaw_left"),
                ("action", "rotate right", "yaw_right"),
                ("toggle", "help", "help"),
            ]
        if tab == "Data":
            return [
                ("action", "save scene", "save_geom"),
                ("action", "load scene", "load_geom"),
                ("action", "versions", "versions"),
                ("action", "save ODs", "save_ods"),
                ("action", "load ODs", "load_ods"),
            ]
        if tab == "Research":
            specs = [
                ("action", "chrono", "chrono_toggle"),
                ("action", "start -", "win_start_dec"),
                ("action", "start +", "win_start_inc"),
                ("action", "end -", "win_end_dec"),
                ("action", "end +", "win_end_inc"),
                ("action", "undated", "undated_cycle"),
                ("action", "month >", "month_next"),
                ("action", "by time", "phase_by_time"),
                ("action", "task filt", "task_filter"),
                ("action", "assign ph", "assign_phase"),
            ]
            research = getattr(self.sim, "research", None)
            for phase in (research.phases if research is not None else []):
                specs.append(("action", phase.id, "phase:" + phase.id))
            return specs
        return []

    def _build_controls(self) -> None:
        """Lay out the bottom control pane: a tab strip over a uniform button grid."""
        pygame = self.pygame
        # the layer list drives both the Layers tab and the wheel chooser, so it
        # is refreshed whichever tab happens to be showing
        self._refresh_layer_views()
        pad, bw, bh, gap = self.PAD, self.BTN_W, self.BTN_H, self.GAP
        self.panel_h = pad * 3 + self.TAB_H + self.BTN_ROWS * (bh + gap) - gap
        panel_top = self.H - self.panel_h

        self.tab_rects = []
        tab_w = max(self.font.size(t)[0] for t in self.TABS) + 24
        x = pad
        for t in self.TABS:
            self.tab_rects.append((t, pygame.Rect(x, panel_top + pad, tab_w, self.TAB_H)))
            x += tab_w + 2

        self.buttons = []
        self._row_labels = []
        specs = self._tab_specs(self.active_tab)
        per_row = max(1, (self.W - 2 * pad + gap) // (bw + gap))
        y0 = panel_top + pad * 2 + self.TAB_H
        for i, spec in enumerate(specs):
            row, col = divmod(i, per_row)
            if row >= self.BTN_ROWS:
                break          # a tab should never need more than two rows
            rect = pygame.Rect(pad + col * (bw + gap), y0 + row * (bh + gap), bw, bh)
            self.buttons.append({
                "kind": spec[0], "label": spec[1], "payload": spec[2],
                "rect": rect, "row": self.active_tab,
            })
        self._controls_sig = self._controls_signature()

    # -------------------------------------------------------------- layers UI
    def _controls_signature(self):
        """Cheap identity of everything the toolbar layout depends on, so it is
        only rebuilt when the *set* of buttons changes (not on every weight
        tweak or tab hover)."""
        g = self.sim.grid
        # identity as well as name: adding a layer under an existing name swaps
        # the object, and the buttons hold direct references to it
        phases = tuple(p.id for p in self.sim.research.phases) if hasattr(self.sim, "research") else ()
        return (self.active_tab,
                tuple((lyr.name, id(lyr)) for lyr in g.layers),
                g.elevation is not None, g.friction is not None,
                self._terrain_surf is not None, phases,
                getattr(getattr(self.sim, "research", None), "month", None))

    def _refresh_layer_views(self) -> List[dict]:
        """Every viewable landscape layer: the grid's weighted stack first, then
        read-only views of the arrays the solvers actually consume."""
        g = self.sim.grid
        views: List[dict] = []
        # The shaded relief map is a layer like any other, and off by default --
        # a coloured background competes with every analysis drawn over it.
        if self._terrain_surf is not None:
            views.append({"name": "terrain map", "color": (200, 200, 200),
                          "layer": None, "derived": "terrain"})
        if getattr(self, "_basemap_surf", None) is not None or getattr(self.sim, "basemap", None) is not None:
            views.append({"name": "basemap", "color": (180, 180, 180),
                          "layer": None, "derived": "basemap"})
        views += [
            {"name": lyr.name, "color": lyr.color, "layer": lyr, "derived": None}
            for lyr in g.layers
        ]
        if g.elevation is not None:
            views.append({"name": "elevation", "color": (255, 214, 140),
                          "layer": None, "derived": "elevation"})
        if g.friction is not None:
            views.append({"name": "friction", "color": (120, 220, 180),
                          "layer": None, "derived": "friction"})
        views.append({"name": "blocked", "color": (240, 90, 90),
                      "layer": None, "derived": "blocked"})
        views.append({"name": "cost", "color": (150, 170, 255),
                      "layer": None, "derived": "cost"})
        self.layer_views = views
        if self.active_layer >= len(views):
            self.active_layer = -1
        return views

    def _layer_label(self, index: int) -> str:
        if index < 0 or index >= len(self.layer_views):
            return "off"
        v = self.layer_views[index]
        if v["layer"] is None:
            return v["name"]
        return f"{v['name']} x{v['layer'].weight:g}"

    def _layer_array(self, view: dict) -> Optional[np.ndarray]:
        """0..1 array for display."""
        g = self.sim.grid
        d = view["derived"]
        if d is None:
            return view["layer"].display_norm()
        if d == "terrain":
            return None          # drawn as a full-colour raster, not a ramp
        if d == "elevation":
            arr = g.elevation
        elif d == "friction":
            arr = g.friction
        elif d == "blocked":
            return (~g.walkable).astype(float)
        else:  # "cost" -- the first live cost field, i.e. what agents follow
            arr = next((c for c in g._cost_fields.values() if c is not None), None)
        if arr is None:
            return None
        arr = np.asarray(arr, dtype=float)
        finite = np.isfinite(arr)
        if not finite.any():
            return None
        lo, hi = float(arr[finite].min()), float(arr[finite].max())
        out = np.zeros_like(arr) if hi <= lo else (arr - lo) / (hi - lo)
        return np.where(finite, out, 1.0)

    def select_layer(self, index: int) -> None:
        self.active_layer = index if 0 <= index < len(self.layer_views) else -1
        self._status(f"layer: {self._layer_label(self.active_layer)}")

    def cycle_layer(self, step: int) -> None:
        """Wheel over the control pane: choose which layer is displayed.
        The cycle includes 'off' so you can always get back to a clean map."""
        n = len(self.layer_views)
        if n == 0:
            return
        nxt = self.active_layer + step
        if nxt >= n or nxt < -1:
            nxt = -1 if nxt >= n else n - 1
        self.select_layer(nxt)

    def adjust_layer_weight(self, steps: int) -> None:
        """Shift+wheel: re-weight the selected layer and re-route on the result."""
        if not (0 <= self.active_layer < len(self.layer_views)):
            self._status("no layer selected")
            return
        v = self.layer_views[self.active_layer]
        lyr = v["layer"]
        if lyr is None:
            self._status(f"{v['name']} is a derived view -- no weight")
            return
        lyr.adjust_weight(steps)
        self.sim.grid.layers.touch()
        self.sim.refresh_layers()
        self._status(f"{lyr.name} weight {lyr.weight:g} (routes rebuilt)")

    def adjust_layer_alpha(self, steps: int) -> None:
        """Ctrl+wheel: how strongly the displayed layer covers the map."""
        self.layer_alpha = min(max(self.layer_alpha + 0.05 * steps, 0.05), 1.0)
        self._status(f"layer opacity {self.layer_alpha:.0%}")

    def _in_panel(self, pos) -> bool:
        return pos[1] >= self.H - self.panel_h or pos[1] < self.TOP_H

    def _btn_active(self, b) -> bool:
        k, p = b["kind"], b["payload"]
        if k == "mode":
            return self.sim.analysis_mode == p
        if k == "tool":
            return self.tool == p
        if k == "toggle":
            return self.isovist_follow
        if k == "layer":
            return self.active_layer == p
        return False

    def _status(self, msg: str, ttl: int = 90) -> None:
        self.status_msg = msg
        self.status_ttl = ttl

    def _path(self, name: str) -> str:
        return os.path.join(self.save_dir, name)

    def _panel_click(self, pos) -> None:
        for name, rect in self.top_buttons:
            if rect.collidepoint(pos):
                self._do_action(name)
                return
        for name, rect in self.tab_rects:
            if rect.collidepoint(pos):
                self.select_tab(name)
                return
        for b in self.buttons:
            if b["rect"].collidepoint(pos):
                self._activate_button(b)
                return

    def select_tab(self, name: str) -> None:
        if name in self.TABS and name != self.active_tab:
            self.active_tab = name
            self._build_controls()

    def cycle_tab(self, step: int) -> None:
        i = (self.TABS.index(self.active_tab) + step) % len(self.TABS)
        self.select_tab(self.TABS[i])

    def _activate_button(self, b) -> None:
        k, p = b["kind"], b["payload"]
        if k == "mode":
            self.set_analysis_mode(ANALYSIS_NONE if self.sim.analysis_mode == p else p)
        elif k == "tool":
            self.tool = "pan" if self.tool == p else p
            self.draft_poly = []
            self._carry = None
            self._template = None
            if self.tool in ("bd_add", "ob_add"):
                self._status("click vertices; click start / double-click / ENTER to close",
                             ttl=180)
            elif self.tool == "bd_circle":
                self._status("circle: click centre, then rim, then door", ttl=240)
            elif self.tool == "bd_rect":
                self._status("rectangle: click one corner, opposite corner, then door",
                             ttl=240)
        elif k == "layer":
            self.select_layer(-1 if self.active_layer == p else p)
        elif k == "toggle":
            if p == "isovist":
                self.isovist_follow = not self.isovist_follow
                if not self.isovist_follow:
                    self.sim.isovist = None
            elif p == "help":
                self.show_help = not self.show_help
        elif k == "action":
            self._do_action(p)

    def _do_action(self, name: str) -> None:
        from .rivers import Season

        try:
            if name == "reset_analysis":
                self.sim.reset_analysis()
                self._status("analysis reset")
            elif name == "reset_all":
                self.sim.reset_analysis()
                for a in self.sim.agents:
                    a.die(0)
                self._carry = None
                self.draft_poly = []
                self._status("everything reset")
            elif name == "fit":
                self.fit_view()
            elif name == "view_top":
                self.pitch = 0.0
                self.angle = 0.0
            elif name == "view_iso":
                self.pitch = math.radians(45)
                self.angle = math.radians(30)
            elif name == "yaw_left":
                self.rotate_by(-math.radians(15))
            elif name == "yaw_right":
                self.rotate_by(math.radians(15))
            # -- seasons --------------------------------------------------
            elif name == "season_next":
                self._status(f"season: {self.sim.advance_season().label}"
                             f" - {self.sim.season_summary()}")
            elif name in ("season_dry", "season_normal", "season_flood"):
                season = {"season_dry": Season.DRY, "season_normal": Season.NORMAL,
                          "season_flood": Season.SPRING_FLOOD}[name]
                self.sim.set_season(season)
                self._status(f"season: {season.label} - {self.sim.season_summary()}")
            # -- navigation -----------------------------------------------
            elif name == "back_to_cluster":
                self._leave_scene(self._go_cluster)
            elif name == "open_site":
                self._open_selected_site()
            # -- data -----------------------------------------------------
            elif name == "save_ods":
                self.sim.save_ods(self._path("ods.txt"))
                self._status("saved ods.txt")
            elif name == "load_ods":
                self.sim.load_ods(self._path("ods.txt"))
                self._status("loaded ods.txt")
            elif name == "save_geom":
                self._status(self._save_scene())
            elif name == "load_geom":
                if self.app is not None:
                    self._status(self.app.load_current())
                else:
                    self.sim.load_geometry_json(self._path("geometry.json"))
                    self._status("loaded geometry.json")
            elif name == "od_kind":
                kinds = ["water", "house", "gate", "special", "quarry:chert",
                         "quarry:limestone", "resource:plants", "resource:wood",
                         "resource:hunt", "site"]
                i = kinds.index(self.od_kind) if self.od_kind in kinds else -1
                self.od_kind = kinds[(i + 1) % len(kinds)]
                self._status(f"OD kind: {self.od_kind}")
            elif name == "chrono_toggle":
                self.sim.research.respect_chronology = not self.sim.research.respect_chronology
                state = "on" if self.sim.research.respect_chronology else "off"
                self._status(f"chronology {state}")
            elif name in ("win_start_dec", "win_start_inc", "win_end_dec", "win_end_inc"):
                self._nudge_window(name)
            elif name == "undated_cycle":
                order = ["exclude", "include", "include_flagged"]
                cur = self.sim.research.undated_policy
                self.sim.research.undated_policy = order[(order.index(cur) + 1) % len(order)]
                self._status(f"undated: {self.sim.research.undated_policy}")
            elif name == "month_next":
                from .calendar import apply_month
                current = self.sim.research.month or 0
                apply_month(self.sim, 1 if current >= 12 else current + 1)
                self._status(f"month {self.sim.research.month}")
            elif name == "phase_by_time":
                self.sim.research.phase_mode = (
                    "manual" if self.sim.research.phase_mode == "by_time" else "by_time"
                )
                self.sim.apply_phase_filter()
                self._status(f"phases {self.sim.research.phase_mode}")
            elif name == "task_filter":
                self._cycle_task_filter()
            elif name == "assign_phase":
                self._assign_selected_phase()
            elif name.startswith("phase:"):
                self._toggle_phase(name.split(":", 1)[1])
            elif name == "back_to_region":
                self._leave_scene(self._go_up)
            elif name == "versions":
                if self.app is not None:
                    vs = self.app.versions_of_current()
                    self._status(f"{len(vs)} archived version(s)"
                                 + (f", newest {os.path.basename(vs[-1])}" if vs else ""))
                else:
                    vs = self.sim.list_versions(self._path("geometry.json"))
                    self._status(f"{len(vs)} archived version(s)")
        except Exception as exc:  # noqa: BLE001 - surface any IO error in the HUD
            self._status(f"{name} failed: {exc}")

    # -------------------------------------------------------- scale & saving
    def _save_scene(self) -> str:
        if self.app is not None:
            return self.app.save_current()
        self.sim.save_geometry_versioned(self._path("geometry.json"))
        self.dirty = False
        return "saved geometry.json (previous version kept)"

    def _request_quit(self) -> None:
        """Quit, but never silently throw away edits."""
        def quit_now() -> None:
            self.running = False

        self._leave_scene(quit_now)

    def mark_dirty(self) -> None:
        """Record that the scene has unsaved edits."""
        self.dirty = True
        if self.app is not None:
            self.app.mark_dirty(True)

    @property
    def has_unsaved(self) -> bool:
        return self.app.dirty if self.app is not None else self.dirty

    def _leave_scene(self, then: Callable[[], None]) -> None:
        """Run ``then``, but offer to save first if there are edits."""
        if not self.has_unsaved:
            then()
            return
        self.ask("Save your edits before leaving this scene?",
                 on_yes=lambda: (self._status(self._save_scene()), then()),
                 on_no=then)

    def _go_cluster(self) -> None:
        if self.app is None or self.app.at_cluster:
            return
        self.set_simulation(self.app.back_to_cluster())
        self._status("back to the settlement cluster")

    def _go_up(self) -> None:
        if self.app is None or self.app.at_root:
            return
        self.set_simulation(self.app.up())
        self._status("up one scale")

    def _nudge_window(self, name: str) -> None:
        from .chronology import Interval

        window = self.sim.research.window
        start, end = int(window.start_bc), int(window.end_bc)
        step = 50
        if name == "win_start_inc":
            start += step
        elif name == "win_start_dec":
            start -= step
        elif name == "win_end_inc":
            end += step
        elif name == "win_end_dec":
            end -= step
        if start < end:
            self._status("window would be empty")
            return
        self.sim.research.window = Interval(end, start)
        if self.sim.research.phase_mode == "by_time":
            self.sim.apply_phase_filter()
        self._status(self.sim.research.window.label())

    def _toggle_phase(self, phase_id: str) -> None:
        research = self.sim.research
        current = set(research.current_phase_ids() or [])
        if phase_id in current:
            current.discard(phase_id)
        else:
            current.add(phase_id)
        research.set_manual_phases(sorted(current))
        self.sim.apply_phase_filter()
        self._status("phases: " + (", ".join(sorted(current)) or "none"))

    def _cycle_task_filter(self) -> None:
        keys = sorted(k for k in self.sim.category_occupancy if k.startswith("task:"))
        options = [None, *keys]
        current = self.sim.research.density_filter
        current_key = None if not current else f"{current[0]}:{current[1]}"
        index = options.index(current_key) if current_key in options else 0
        nxt = options[(index + 1) % len(options)]
        if nxt is None:
            self.sim.research.density_filter = None
            self._status("density: all")
        else:
            kind, name = nxt.split(":", 1)
            self.sim.research.density_filter = (kind, name)
            self._status(f"density: {name}")

    def select_buildings_in(self, x0: float, y0: float, x1: float, y1: float) -> List:
        """Buildings whose centre lies in the box. This is the lasso result."""
        minx, maxx = min(x0, x1), max(x0, x1)
        miny, maxy = min(y0, y1), max(y0, y1)
        picked = []
        for building in self.sim.buildings:
            cx = (building.footprint.min_x + building.footprint.max_x) / 2.0
            cy = (building.footprint.min_y + building.footprint.max_y) / 2.0
            if minx <= cx <= maxx and miny <= cy <= maxy:
                picked.append(building)
        self.selected_buildings = picked
        return picked

    def _assign_selected_phase(self) -> None:
        phases = self.sim.research.phases
        if not phases or not self.selected_buildings:
            self._status("select buildings with the lasso, and load a phase")
            return
        phase_id = phases[0].id
        for building in self.selected_buildings:
            if phase_id not in building.phase_ids:
                building.phase_ids.append(phase_id)
        self.mark_dirty()
        self._status(f"assigned {phase_id} to {len(self.selected_buildings)}")

    def _open_selected_site(self) -> None:
        name = self.selected_site
        if self.app is None or not name:
            self._status("click a settlement first")
            return
        if not self.app.has_detail(name):
            self._status(f"no detailed map for {name} yet")
            return
        self._leave_scene(lambda: self._enter_site(name))

    def _enter_site(self, name: str) -> None:
        self.set_simulation(self.app.enter_detail(name))
        self.selected_site = ""
        self._status(f"{name}: village scale")

    # ------------------------------------------------------------- modal ask
    def ask(self, message: str, on_yes: Callable[[], None],
            on_no: Optional[Callable[[], None]] = None) -> None:
        """Put up a yes/no/cancel prompt. Blocks nothing -- the loop keeps
        running and the prompt is drawn over the scene until answered."""
        self.prompt = {"message": message, "yes": on_yes, "no": on_no}

    def _answer(self, yes: Optional[bool]) -> None:
        p, self.prompt = self.prompt, None
        if p is None or yes is None:
            return            # cancelled
        fn = p["yes"] if yes else p["no"]
        if fn is not None:
            fn()

    # Colours, kept in one place so the pane stays visually consistent.
    C_PANEL = (22, 24, 28, 238)
    C_EDGE = (58, 62, 70)
    C_BTN = (40, 44, 52)
    C_BTN_HOVER = (60, 66, 78)
    C_BTN_ON = (52, 120, 200)
    C_TEXT = (212, 216, 224)
    C_TEXT_ON = (255, 255, 255)
    C_MUTED = (138, 148, 164)
    C_WARN = (255, 190, 90)

    def _button(self, rect, label: str, active: bool, hover: bool,
                accent=None, align: str = "center") -> None:
        pygame = self.pygame
        bg = accent if (accent and active) else (
            self.C_BTN_ON if active else self.C_BTN_HOVER if hover else self.C_BTN)
        pygame.draw.rect(self.screen, bg, rect, border_radius=5)
        pygame.draw.rect(self.screen, self.C_EDGE, rect, 1, border_radius=5)
        label = self._fit_label(label, rect.width - 12)
        surf = self.font.render(label, True, self.C_TEXT_ON if active else self.C_TEXT)
        x = rect.x + 9 if align == "left" else rect.centerx - surf.get_width() // 2
        self.screen.blit(surf, (x, rect.centery - surf.get_height() // 2))

    def _fit_label(self, label: str, width: int) -> str:
        """Shorten a label with an ellipsis so it never spills out of its button.

        Layer names come from the data -- an imported plan is called whatever its
        source called it -- so they cannot be assumed to fit."""
        if self.font.size(label)[0] <= width:
            return label
        while label and self.font.size(label + "\u2026")[0] > width:
            label = label[:-1]
        return label + "\u2026"

    def _draw_top_bar(self) -> None:
        """Scale breadcrumb, season, and the unsaved-edits marker."""
        pygame = self.pygame
        bar = pygame.Surface((self.W, self.TOP_H), pygame.SRCALPHA)
        bar.fill(self.C_PANEL)
        self.screen.blit(bar, (0, 0))
        pygame.draw.line(self.screen, self.C_EDGE, (0, self.TOP_H), (self.W, self.TOP_H), 1)

        mx, my = pygame.mouse.get_pos()
        self.top_buttons = []
        x = self.PAD

        # Back to the cluster, only when there is somewhere to go back to
        if self.app is not None and not self.app.at_root:
            if self.app.current.scale.value == "site":
                label, action = "< cluster", "back_to_cluster"
            else:
                label, action = "< region", "back_to_region"
            r = pygame.Rect(x, 5, 108, self.TOP_H - 10)
            self._button(r, label, False, r.collidepoint(mx, my))
            self.top_buttons.append((action, r))
            x += r.width + self.GAP

        crumb = self.app.breadcrumb() if self.app is not None else "single scene"
        surf = self.bigfont.render(crumb, True, (235, 238, 245))
        self.screen.blit(surf, (x, self.TOP_H // 2 - surf.get_height() // 2))
        x += surf.get_width() + 16

        # Open the selected settlement (cluster scale only)
        if self.app is not None and self.app.at_cluster and self.selected_site:
            has = self.app.has_detail(self.selected_site)
            label = f"open {self.selected_site}" if has else f"{self.selected_site}: no map"
            r = pygame.Rect(x, 5, max(150, self.font.size(label)[0] + 20), self.TOP_H - 10)
            self._button(r, label, has, r.collidepoint(mx, my),
                         accent=(46, 140, 90))
            if has:
                self.top_buttons.append(("open_site", r))

        # right side: season, then the dirty marker
        rx = self.W - self.PAD
        if self.has_unsaved:
            s = self.font.render("unsaved edits", True, self.C_WARN)
            rx -= s.get_width()
            self.screen.blit(s, (rx, self.TOP_H // 2 - s.get_height() // 2))
            rx -= 14
        label = f"season: {self.sim.season.label}"
        r = pygame.Rect(0, 5, self.font.size("season: spring floods")[0] + 20,
                        self.TOP_H - 10)
        r.right = rx
        self._button(r, label, False, r.collidepoint(mx, my))
        self.top_buttons.append(("season_next", r))

    def _draw_controls(self) -> None:
        pygame = self.pygame
        panel_top = self.H - self.panel_h
        panel = pygame.Surface((self.W, self.panel_h), pygame.SRCALPHA)
        panel.fill(self.C_PANEL)
        self.screen.blit(panel, (0, panel_top))
        pygame.draw.line(self.screen, self.C_EDGE, (0, panel_top), (self.W, panel_top), 1)

        mx, my = pygame.mouse.get_pos()
        for name, rect in self.tab_rects:
            on = name == self.active_tab
            hover = rect.collidepoint(mx, my)
            if on:
                pygame.draw.rect(self.screen, (34, 38, 46), rect,
                                 border_top_left_radius=5, border_top_right_radius=5)
                pygame.draw.line(self.screen, self.C_BTN_ON,
                                 (rect.x + 3, rect.bottom - 2),
                                 (rect.right - 3, rect.bottom - 2), 2)
            col = self.C_TEXT_ON if on else (self.C_TEXT if hover else self.C_MUTED)
            surf = self.font.render(name, True, col)
            self.screen.blit(surf, (rect.centerx - surf.get_width() // 2,
                                    rect.centery - surf.get_height() // 2))

        for b in self.buttons:
            label = self._layer_label(b["payload"]) if b["kind"] == "layer" else b["label"]
            self._button(b["rect"], label, self._btn_active(b),
                         b["rect"].collidepoint(mx, my))

        if self.status_ttl > 0:
            s = self.bigfont.render(self.status_msg, True, self.C_WARN)
            self.screen.blit(s, (self.W - s.get_width() - 10, panel_top - 26))
            self.status_ttl -= 1

    def _draw_prompt(self) -> None:
        """The save-before-leaving question, drawn over the scene."""
        if self.prompt is None:
            return
        pygame = self.pygame
        veil = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        veil.fill((8, 9, 12, 170))
        self.screen.blit(veil, (0, 0))

        msg = self.prompt["message"]
        w = max(420, self.bigfont.size(msg)[0] + 60)
        box = pygame.Rect(0, 0, w, 130)
        box.center = (self.W // 2, self.view_h // 2)
        pygame.draw.rect(self.screen, (28, 31, 37), box, border_radius=8)
        pygame.draw.rect(self.screen, (90, 100, 120), box, 1, border_radius=8)

        s = self.bigfont.render(msg, True, (240, 243, 250))
        self.screen.blit(s, (box.centerx - s.get_width() // 2, box.y + 22))

        mx, my = pygame.mouse.get_pos()
        self.prompt_buttons = []
        labels = [("save", True), ("discard", False), ("cancel", None)]
        bw, gap = 112, 10
        x = box.centerx - (len(labels) * bw + (len(labels) - 1) * gap) // 2
        for label, answer in labels:
            r = pygame.Rect(x, box.bottom - 44, bw, 28)
            self._button(r, label, answer is True, r.collidepoint(mx, my))
            self.prompt_buttons.append((answer, r))
            x += bw + gap

        hint = self.font.render("Y save    N discard    ESC cancel", True, self.C_MUTED)
        self.screen.blit(hint, (box.centerx - hint.get_width() // 2, box.bottom + 8))

    # ------------------------------------------------------------- rendering
    def _blit_world_surface(self, surf) -> None:
        pygame = self.pygame
        g = self.sim.grid
        w = max(1, int((g.max_x - g.min_x) * self.scale))
        h = max(1, int((g.max_y - g.min_y) * self.scale))
        img = pygame.transform.smoothscale(surf, (w, h))
        # Ground-plane raster transform matches the vector projection:
        # yaw-rotate the image, then foreshorten vertically by cos(pitch).
        if self.angle:
            img = pygame.transform.rotate(img, math.degrees(self.angle))
        cp = math.cos(self.pitch)
        if cp < 0.999:
            iw, ih = img.get_size()
            img = pygame.transform.smoothscale(img, (iw, max(1, int(ih * cp))))
        wcx, wcy = (g.min_x + g.max_x) / 2.0, (g.min_y + g.max_y) / 2.0
        rect = img.get_rect(center=self.to_screen(wcx, wcy, 0.0))
        self.screen.blit(img, rect.topleft)

    def _draw_poly(self, poly, color, width=1, fill=False) -> None:
        if len(poly) < 2:
            return
        pts = [self.to_screen(x, y) for x, y in poly]
        if fill and len(pts) >= 3:
            self.pygame.draw.polygon(self.screen, color, pts)
        else:
            self.pygame.draw.polygon(self.screen, color, pts, width)

    def _draw_buildings(self) -> None:
        """Draw buildings as flat footprints (top-down) or extruded prisms when
        the camera is tilted, painted far-to-near so nearer walls occlude."""
        pygame = self.pygame
        sim = self.sim
        facade = sim.analysis_mode in (ANALYSIS_FACADE_VIS, ANALYSIS_FACADE_VIS_O)
        extrude = self.pitch > 0.02

        def centroid_depth(b):
            xy = b.footprint.as_xy()
            mx = sum(p[0] for p in xy) / len(xy)
            my = sum(p[1] for p in xy) / len(xy)
            return self._yaw_depth(mx, my)

        # farther (larger depth = higher on screen) first
        for b in sorted(sim.buildings, key=centroid_depth, reverse=True):
            xy = b.footprint.as_xy()
            if not extrude or b.height <= 0:
                self._draw_poly(xy, (107, 114, 128), fill=True)
                self._draw_poly(xy, (203, 213, 225), width=1)
                if facade:
                    self._draw_facade(b)
                continue
            from .building import STANDARD_BUILDING_HEIGHT
            wall_h = STANDARD_BUILDING_HEIGHT
            base = [self.to_screen(x, y, 0.0) for x, y in xy]
            top = [self.to_screen(x, y, wall_h) for x, y in xy]
            n = len(xy)
            # Side walls only — no roof until storeys are modelled.
            walls = []
            for i in range(n):
                j = (i + 1) % n
                mx = (xy[i][0] + xy[j][0]) / 2.0
                my = (xy[i][1] + xy[j][1]) / 2.0
                walls.append((self._yaw_depth(mx, my), [base[i], base[j], top[j], top[i]]))
            for d, quad in sorted(walls, key=lambda w: w[0], reverse=True):
                shade = 70 + int(40 * (0.5 - min(max(d / 400.0, -0.5), 0.5)))
                pygame.draw.polygon(self.screen, (shade, shade + 6, shade + 16), quad)
                pygame.draw.polygon(self.screen, (48, 52, 60), quad, 1)
            if facade:
                self._draw_facade(b)

    def _overlay_field(self, field: np.ndarray, maxv: float, rgb: Tuple[int, int, int],
                       alpha: float = 0.82) -> None:
        if maxv <= 0:
            return
        pygame = self.pygame
        norm = np.clip(field / maxv, 0.0, 1.0)
        # Per-pixel alpha so the background map stays visible: fully transparent
        # where there is no occupancy, opaque where it is high.
        surf = pygame.Surface((field.shape[0], field.shape[1]), pygame.SRCALPHA)
        rgb3 = pygame.surfarray.pixels3d(surf)
        rgb3[..., 0], rgb3[..., 1], rgb3[..., 2] = rgb
        del rgb3
        peak = 255 * min(max(alpha, 0.0), 1.0)
        a = pygame.surfarray.pixels_alpha(surf)
        a[:] = (norm * peak).astype(np.uint8)
        del a
        surf = pygame.transform.flip(surf, False, True)
        self._blit_world_surface(surf)

    def render(self) -> None:
        pygame = self.pygame
        sim = self.sim
        g = sim.grid
        self.screen.fill((13, 13, 15))

        # a layer added/removed since the last frame needs a toolbar relayout
        if self._controls_signature() != self._controls_sig:
            self._build_controls()

        # The selected layer is the only background. The relief map is one of
        # the choices rather than an always-on backdrop, so analysis drawn over
        # it is never fighting a coloured raster the user cannot turn off.
        if 0 <= self.active_layer < len(self.layer_views):
            view = self.layer_views[self.active_layer]
            if view["derived"] == "terrain":
                if self._terrain_surf is not None:
                    self._blit_world_surface(self._terrain_surf)
            elif view["derived"] == "basemap":
                surf = getattr(self, "_basemap_surf", None)
                if surf is not None:
                    self._blit_world_surface(surf)
            else:
                arr = self._layer_array(view)
                if arr is not None:
                    self._overlay_field(arr, 1.0, view["color"], alpha=self.layer_alpha)

        if sim.site_polygon:
            self._draw_poly(sim.site_polygon, (150, 160, 170), width=2)

        self._draw_rivers()

        for o in sim.obstacles:
            self._draw_poly(o.footprint.as_xy(), _LAYER_COLORS.get(o.layer, (60, 60, 70)),
                            fill=True)

        if sim.analysis_mode == ANALYSIS_PATHOVERLAP:
            field, scale = sim.display_occupancy() if hasattr(sim, "display_occupancy") else (
                g.occupancy, g.max_occupancy)
            self._overlay_field(field, scale, (255, 60, 60))

        if sim.analysis_mode in (ANALYSIS_TRACES, ANALYSIS_TRACES_O):
            by_group = sim.analysis_mode == ANALYSIS_TRACES_O
            for t in sim.traces:
                if not t.draw_me or len(t.points) < 3:
                    continue
                col = t.color(by_group)
                pts = [self.to_screen(p[0], p[1]) for p in t.points]
                rgb = (int(col[0] * 255), int(col[1] * 255), int(col[2] * 255))
                pygame.draw.lines(self.screen, rgb, False, pts, 1)

        # ODs
        for od in sim.ods:
            if od is None:
                continue
            sx, sy = self.to_screen(od.x, od.y)
            col = _GROUP_COLORS[od.group % len(_GROUP_COLORS)]
            if od.is_source and od.is_sink:
                pygame.draw.polygon(self.screen, col, [(sx, sy - 7), (sx + 7, sy),
                                                       (sx, sy + 7), (sx - 7, sy)])
            elif od.is_source:
                pygame.draw.circle(self.screen, col, (sx, sy), 6)
            else:
                pygame.draw.rect(self.screen, col, (sx - 5, sy - 5, 10, 10))
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), 7, 1)

        # agents
        for a in sim.active_agents:
            wx, wy = g.world_x(a.px), g.world_y(a.py)
            sx, sy = self.to_screen(wx, wy)
            pygame.draw.circle(self.screen, _GROUP_COLORS[a.group % len(_GROUP_COLORS)],
                               (sx, sy), 2)

        # Buildings last, so they occlude the pedestrians and ODs behind them --
        # you cannot see through a wall, and the extrusions are the near geometry.
        self._draw_buildings()

        # settlement labels sit above the buildings, being annotation not scene
        self._draw_site_markers()

        # isovist
        if sim.isovist is not None and self.isovist_follow:
            poly = [self.to_screen(x, y) for x, y in sim.isovist.polygon()]
            if len(poly) >= 3:
                iso_surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                pygame.draw.polygon(iso_surf, (255, 228, 94, 90), poly)
                self.screen.blit(iso_surf, (0, 0))

        # building / obstacle draft
        if self.tool in ("building", "bd_add", "ob_add") and self.draft_poly:
            pts = [self.to_screen(x, y) for x, y in self.draft_poly]
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, (255, 220, 0), False, pts, 2)
            for px, py in pts:
                pygame.draw.circle(self.screen, (255, 220, 0), (px, py), 3)
            # closing target: ring around the first vertex once a polygon exists
            if len(pts) >= 3:
                mx, my = pygame.mouse.get_pos()
                near = math.hypot(mx - pts[0][0], my - pts[0][1]) <= self.close_radius_px
                ring = (80, 255, 120) if near else (255, 140, 0)
                pygame.draw.circle(self.screen, ring, pts[0], self.close_radius_px, 2)
                # rubber-band line back to the start when hovering the target
                if near:
                    pygame.draw.line(self.screen, ring, pts[-1], pts[0], 1)
        self._draw_template_draft()

        self._draw_hud()
        self._draw_top_bar()
        self._draw_controls()
        self._draw_prompt()
        pygame.display.flip()

    def _draw_rivers(self) -> None:
        """Channel, banks and fords. Colour says what the season is doing to it."""
        pygame = self.pygame
        for r in self.sim.rivers:
            if len(r.path) < 2:
                continue
            mult, blocks = r.effect(self.sim.season)
            # width is the true channel width; the season shows in the colour --
            # in flood it should be unmistakable, because that is the state that
            # turns the river from a toll into a wall
            if blocks:
                col, edge, halo = (70, 170, 255), (225, 245, 255), True
            elif mult <= 0.0:
                col, edge, halo = (96, 88, 72), (140, 130, 108), False  # dry bed
            else:
                col, edge, halo = (38, 84, 152), (110, 165, 225), False
            pts = [self.to_screen(x, y) for x, y in r.path]
            if len(pts) < 2:
                continue
            px = max(2, int(r.width * self.scale))
            if halo:
                over = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                pygame.draw.lines(over, (80, 170, 255, 70), False, pts, px * 2)
                self.screen.blit(over, (0, 0))
            pygame.draw.lines(self.screen, col, False, pts, px)
            pygame.draw.lines(self.screen, edge, False, pts, 2 if blocks else 1)
            for fx, fy in r.fords:
                sx, sy = self.to_screen(fx, fy)
                ring = (110, 110, 118) if blocks else (255, 214, 120)
                pygame.draw.circle(self.screen, ring, (sx, sy), 6, 2)

    def _draw_site_markers(self) -> None:
        """Label the settlements at cluster scale and show which is selected.

        Confidence is drawn, not hidden: a site whose coordinate is approximate
        or contested gets a dashed ring, so nobody reads a cluster-scale result
        as sharper than the underlying survey data.
        """
        self._site_markers = []
        if self.app is None or not self.app.at_cluster:
            return
        pygame = self.pygame
        for od in self.sim.ods:
            if od is None or not od.name:
                continue
            sx, sy = self.to_screen(od.x, od.y)
            if not (0 <= sx < self.W and self.TOP_H <= sy < self.TOP_H + self.view_h):
                continue
            self._site_markers.append((od.name, sx, sy))
            selected = od.name == self.selected_site
            has_detail = self.app.has_detail(od.name)
            col = (255, 226, 120) if selected else (
                (150, 235, 180) if has_detail else (200, 206, 218))
            pygame.draw.circle(self.screen, col, (sx, sy), 7 if selected else 5, 2)
            if has_detail:
                pygame.draw.circle(self.screen, col, (sx, sy), 2)
            label = self.font.render(od.name, True, col)
            self.screen.blit(label, (sx + 10, sy - 7))

    def _site_at(self, pos) -> str:
        """Name of the settlement marker under the cursor, if any."""
        best, best_d = "", 18.0
        for name, sx, sy in self._site_markers:
            d = math.hypot(pos[0] - sx, pos[1] - sy)
            if d < best_d:
                best, best_d = name, d
        return best

    def _draw_facade(self, b) -> None:
        g = self.sim.grid
        by_group = self.sim.analysis_mode == ANALYSIS_FACADE_VIS_O
        maxv = max(g.max_boundary_visibility, 1e-6)
        fp = b.footprint
        for i, seg in enumerate(fp.seg_points):
            refs = fp.seg_pixrefs[i] if i < len(fp.seg_pixrefs) else []
            for j in range(len(seg) - 1):
                if j >= len(refs):
                    break
                px, py = refs[j]
                if not g.in_bounds(px, py):
                    continue
                if by_group:
                    vals = g.visibility_o[px, py]
                    r = int(255 * min(1.0, vals[0] / maxv)) if g.num_groups > 0 else 0
                    gg = int(255 * min(1.0, vals[1] / maxv)) if g.num_groups > 1 else 0
                    bb = int(255 * min(1.0, vals[2] / maxv)) if g.num_groups > 2 else 0
                    color = (r, gg, bb)
                else:
                    v = min(1.0, g.visibility[px, py] / maxv)
                    color = (255, int(255 * (1 - v)), int(255 * (1 - v)))
                p0 = self.to_screen(*seg[j])
                p1 = self.to_screen(*seg[j + 1])
                self.pygame.draw.line(self.screen, color, p0, p1, 3)

    def _draw_hud(self) -> None:
        sim = self.sim
        lines = [
            f"mode: {_MODE_NAME.get(sim.analysis_mode)}   tool: {self.tool}"
            f"   {'PLAYING' if self.playing else 'PAUSED'}"
            f"   layer: {self._layer_label(self.active_layer)}",
            f"agents: {len(sim.active_agents)}   ticks: {sim.ticks}   "
            f"ODs: {sim.reachable_targets()}   yaw: {math.degrees(self.angle):.0f}\u00b0"
            f"  tilt: {math.degrees(self.pitch):.0f}\u00b0   fps: {self.clock.get_fps():.0f}",
        ]
        if len(sim.grid.layers):
            lines.append(f"layers: {sim.grid.layers.summary()}")
        if sim.rivers:
            lines.append(sim.season_summary())
        if hasattr(sim, "research"):
            lines.extend(sim.research.hud_lines(sim.population_label()))
        y = self.TOP_H + 6
        for ln in lines:
            surf = self.font.render(ln, True, (228, 232, 240))
            self.screen.blit(surf, (8, y))
            y += 19
        if self.show_help:
            help_lines = [
                "SPACE play/pause  . step  [ ] speed   arrows/right-drag pan  wheel/+- zoom  F fit",
                "3D: middle-drag or Shift+arrows (yaw + tilt)    TAB next tab    N next season",
                "layers: wheel over the pane picks one (L cycles)  shift+wheel weight  ctrl+wheel opacity",
                "cluster: click a settlement to select, double-click to open its village scale",
                "ctrl+S save (keeps the previous version)    H help    Q quit",
            ]
            y = self.TOP_H + self.view_h - 19 * len(help_lines) - 6
            for ln in help_lines:
                surf = self.font.render(ln, True, (166, 186, 208))
                self.screen.blit(surf, (8, y))
                y += 19

    # ------------------------------------------------------------- scene ops
    def set_analysis_mode(self, mode: int) -> None:
        self.sim.set_analysis_mode(mode)

    def add_source(self, wx: float, wy: float, group: int = 1) -> None:
        self.sim.add_od(wx, wy, group=group, origin_weight=1.0, dest_weight=0.0,
                        kind=self.od_kind)

    def add_sink(self, wx: float, wy: float, group: int = 0) -> None:
        self.sim.add_od(wx, wy, group=group, origin_weight=0.2, dest_weight=1.0,
                        kind=self.od_kind)

    def delete_at(self, wx: float, wy: float) -> None:
        # nearest OD within tolerance, else a building containing the point
        tol = 12 / self.scale
        best_i, best_d = -1, tol
        for i, od in enumerate(self.sim.ods):
            if od is None:
                continue
            d = math.hypot(od.x - wx, od.y - wy)
            if d < best_d:
                best_d, best_i = d, i
        if best_i != -1:
            self.sim.delete_od(best_i)
            return
        for b in list(self.sim.buildings):
            if b.contains(wx, wy):
                self.sim.delete_building(b)
                return

    def finish_draft(self) -> None:
        """Close whatever is being drawn: a building, an obstacle, or a river.

        A river is a polyline rather than a ring, so two points are enough and
        the ends are not joined.
        """
        pts = list(self.draft_poly)
        self.draft_poly = []
        if self.tool == "rv_add":
            if len(pts) >= 2:
                r = self.sim.add_river(pts)
                self.mark_dirty()
                self._status(f"{r.name} added ({r.length() / 1000:.1f} km, "
                             f"{r.kind}) - add fords to make it crossable")
            return
        if len(pts) < 3:
            return
        if self.tool == "ob_add":
            self.sim.add_obstacle(pts)
            self._status("obstacle added")
        else:
            self.sim.add_building(pts)
            self._status("building added")
        self.mark_dirty()

    # kept as the old name for scripts and tests that drive the viewer
    finish_building = finish_draft

    def _nearest_river(self, wx: float, wy: float):
        """River whose centreline passes nearest ``(wx, wy)``, within a screen
        tolerance, or ``None``."""
        tol = max(30.0 / max(self.scale, 1e-6), 0.0)
        best, best_d = None, float("inf")
        for r in self.sim.rivers:
            for (x0, y0), (x1, y1) in zip(r.path, r.path[1:]):
                dx, dy = x1 - x0, y1 - y0
                L2 = dx * dx + dy * dy
                t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((wx - x0) * dx + (wy - y0) * dy) / L2))
                d = math.hypot(wx - (x0 + t * dx), wy - (y0 + t * dy))
                if d < best_d:
                    best, best_d = r, d
        if best is not None and best_d <= max(tol, best.width):
            return best
        return None

    # -- OD helpers ----------------------------------------------------------
    def _nearest_od(self, wx: float, wy: float) -> int:
        tol = 12 / self.scale
        best_i, best_d = -1, tol
        for i, od in enumerate(self.sim.ods):
            if od is None:
                continue
            d = math.hypot(od.x - wx, od.y - wy)
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _delete_od_at(self, wx: float, wy: float) -> None:
        i = self._nearest_od(wx, wy)
        if i != -1:
            self.sim.delete_od(i)
            self._status("OD deleted")

    def _weight_od_at(self, wx: float, wy: float) -> None:
        i = self._nearest_od(wx, wy)
        if i == -1:
            return
        od = self.sim.ods[i]
        # cycle destination weight 0.25 -> 0.5 -> 0.75 -> 1.0 -> 0.25
        w = round((od.dest_weight % 1.0) + 0.25, 2)
        self.sim.weight_od(i, dest_weight=w)
        self._status(f"OD weight -> {w:.2f}")

    # -- building/obstacle helpers ------------------------------------------
    def _template_click(self, wx: float, wy: float) -> None:
        """Wizard: place centre/corner → size → door, then stamp the building."""
        shape = "circle" if self.tool == "bd_circle" else "rect"
        if self._template is None or self._template.get("shape") != shape:
            self._template = {"shape": shape, "a": (wx, wy), "b": None}
            tip = "click the rim" if shape == "circle" else "click the opposite corner"
            self._status(tip, ttl=240)
            return
        if self._template.get("b") is None:
            self._template["b"] = (wx, wy)
            self._status("click the door on the facade", ttl=240)
            return
        from .templates import place_templated_building
        try:
            _building, od = place_templated_building(
                self.sim, shape,
                self._template["a"], self._template["b"], (wx, wy),
                function="domestic",
            )
        except ValueError as exc:
            self._status(str(exc), ttl=180)
            self._template = None
            return
        self._template = None
        self.mark_dirty()
        self._status(
            f"{shape} building + entrance OD ({od.name}) — tool stays on for the next one",
            ttl=240,
        )

    def _draw_template_draft(self) -> None:
        if self._template is None or self.tool not in ("bd_circle", "bd_rect"):
            return
        pygame = self.pygame
        a = self._template.get("a")
        b = self._template.get("b")
        mx, my = pygame.mouse.get_pos()
        wx, wy = self.to_world(mx, my)
        colour = (255, 220, 0)
        if a is not None:
            ax, ay = self.to_screen(*a)
            pygame.draw.circle(self.screen, colour, (ax, ay), 4)
        end = b if b is not None else (wx, wy)
        if a is None or end is None:
            return
        try:
            from .templates import circle_polygon, rect_polygon
            if self._template["shape"] == "circle":
                r = math.hypot(end[0] - a[0], end[1] - a[1])
                if r <= 0:
                    return
                poly = circle_polygon(a[0], a[1], r)
            else:
                poly = rect_polygon(a[0], a[1], end[0], end[1])
        except ValueError:
            return
        pts = [self.to_screen(x, y) for x, y in poly]
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, colour, True, pts, 2)
        if b is not None:
            # door rubber-band from cursor to the nearest facade preview
            pygame.draw.circle(self.screen, (80, 255, 120), (mx, my), 5, 1)

    def _building_at(self, wx: float, wy: float, kind: str):
        coll = self.sim.buildings if kind == "building" else self.sim.obstacles
        for b in list(coll):
            if b.contains(wx, wy):
                return b
        return None

    def _delete_building_at(self, wx: float, wy: float, kind: str) -> None:
        b = self._building_at(wx, wy, kind)
        if b is not None:
            self.sim.delete_building(b)
            self._status(f"{kind} deleted")

    def _cycle_height_at(self, wx: float, wy: float) -> None:
        b = self._building_at(wx, wy, "building")
        if b is None:
            return
        h = b.height + 4.0
        if h > 40.0:
            h = 4.0
        self.sim.set_building_height(b, h)
        self._status(f"height -> {h:.0f}")

    def _move_click(self, wx: float, wy: float, tool: str) -> None:
        kind = "building" if tool == "bd_move" else "obstacle"
        if self._carry is None:
            b = self._building_at(wx, wy, kind)
            if b is not None:
                self._carry = (b, kind)
                self._carry_anchor = (wx, wy)
                self._status(f"{kind} grabbed - click destination")
        else:
            b, _ = self._carry
            dx, dy = wx - self._carry_anchor[0], wy - self._carry_anchor[1]
            self.sim.move_building(b, dx, dy)
            self._carry = None
            self._status(f"{kind} moved")

    def isovist_at(self, wx: float, wy: float) -> None:
        try:
            self.sim.compute_isovist(wx, wy, ray_length=3000.0)
        except Exception:
            pass

    # ---------------------------------------------------------------- events
    def _handle_event(self, ev) -> None:
        pygame = self.pygame
        if ev.type == pygame.QUIT:
            self._request_quit()
            return
        # A modal question swallows everything until it is answered.
        if self.prompt is not None:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_y, pygame.K_RETURN):
                    self._answer(True)
                elif ev.key == pygame.K_n:
                    self._answer(False)
                elif ev.key == pygame.K_ESCAPE:
                    self._answer(None)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for answer, rect in self.prompt_buttons:
                    if rect.collidepoint(ev.pos):
                        self._answer(answer)
                        return
            return
        if ev.type == pygame.KEYDOWN:
            self._handle_key(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                if self._in_panel(ev.pos):
                    self._panel_click(ev.pos)
                else:
                    now = pygame.time.get_ticks()
                    dbl = (now - self._last_click_ms <= 350
                           and abs(ev.pos[0] - self._last_click_pos[0]) <= 6
                           and abs(ev.pos[1] - self._last_click_pos[1]) <= 6)
                    self._last_click_ms = now
                    self._last_click_pos = ev.pos
                    site = self._site_at(ev.pos)
                    if site and self.tool in ("pan", ""):
                        # cluster scale: click selects a settlement, double-click
                        # walks straight into its detailed scene
                        self.selected_site = site
                        if dbl:
                            self._open_selected_site()
                        else:
                            detail = (self.app is not None
                                      and self.app.has_detail(site))
                            self._status(f"{site}" + ("  (double-click to open)"
                                                      if detail else "  - no detailed map"))
                    elif (dbl and self.tool in ("building", "bd_add", "ob_add", "rv_add")
                            and len(self.draft_poly) >= (2 if self.tool == "rv_add" else 3)):
                        # double-click closes; the first click already placed the
                        # final vertex, so just finish (no duplicate point).
                        self.finish_draft()
                    else:
                        self._handle_click(ev.pos)
            elif ev.button in (4, 5):
                step = 1 if ev.button == 4 else -1
                if self._in_panel(ev.pos):
                    # over the control pane the wheel drives the layer chooser:
                    # plain picks the layer, shift re-weights it, ctrl fades it
                    mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_SHIFT:
                        self.adjust_layer_weight(step)
                    elif mods & (pygame.KMOD_CTRL | pygame.KMOD_META):
                        self.adjust_layer_alpha(step)
                    else:
                        self.cycle_layer(step)
                else:
                    self._zoom(1.15 if step > 0 else 1 / 1.15, ev.pos)
        elif ev.type == pygame.MOUSEMOTION:
            if ev.buttons[1] and not self._in_panel(ev.pos):  # middle-drag orbit
                self.rotate_by(ev.rel[0] * 0.01)     # horizontal -> yaw
                self.tilt_by(-ev.rel[1] * 0.01)      # vertical   -> tilt (up = more 3D)
            elif ev.buttons[2] and not self._in_panel(ev.pos):  # right-drag pan
                # Drag-to-pan: keep the ground point under the cursor fixed, so it
                # tracks the mouse correctly at any yaw/tilt.
                px, py = ev.pos
                ox, oy = px - ev.rel[0], py - ev.rel[1]
                wx0, wy0 = self.to_world(ox, oy)
                wx1, wy1 = self.to_world(px, py)
                self.cx -= wx1 - wx0
                self.cy -= wy1 - wy0
            if self.isovist_follow and not self._in_panel(ev.pos):
                self.isovist_at(*self.to_world(*ev.pos))

    def _handle_key(self, key) -> None:
        pygame = self.pygame
        k = key
        drawing = self.tool in ("building", "bd_add", "ob_add", "rv_add")
        if k in (pygame.K_q, pygame.K_ESCAPE):
            if drawing and self.draft_poly:
                self.draft_poly = []
            elif k == pygame.K_ESCAPE and self.app is not None and not self.app.at_root:
                self._leave_scene(self._go_up)
            else:
                self._request_quit()
        elif k == pygame.K_SPACE:
            self.playing = not self.playing
        elif k == pygame.K_PERIOD and not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
            self.sim.step()
        elif k == pygame.K_LEFTBRACKET:
            self.steps_per_frame = max(1, self.steps_per_frame - 1)
        elif k == pygame.K_RIGHTBRACKET:
            self.steps_per_frame += 1
        elif k in (pygame.K_PLUS, pygame.K_EQUALS):
            self._zoom(1.15, (self.W // 2, self.H // 2))
        elif k == pygame.K_MINUS:
            self._zoom(1 / 1.15, (self.W // 2, self.H // 2))
        elif k == pygame.K_f:
            self.fit_view()
        elif k == pygame.K_h:
            self.show_help = not self.show_help
        elif k == pygame.K_c:
            self.sim.reset_analysis()
        elif k == pygame.K_0:
            self.set_analysis_mode(ANALYSIS_NONE)
        elif k == pygame.K_1:
            self.set_analysis_mode(ANALYSIS_PATHOVERLAP)
        elif k == pygame.K_2:
            self.set_analysis_mode(ANALYSIS_FACADE_VIS)
        elif k == pygame.K_3:
            self.set_analysis_mode(ANALYSIS_FACADE_VIS_O)
        elif k == pygame.K_4:
            self.set_analysis_mode(ANALYSIS_TRACES)
        elif k == pygame.K_5:
            self.set_analysis_mode(ANALYSIS_TRACES_O)
        elif k == pygame.K_o:
            self.tool = "od_source"
        elif k == pygame.K_k:
            self.tool = "od_sink"
        elif k == pygame.K_x:
            self.tool = "delete"
        elif k == pygame.K_b:
            self.tool = "building"
            self.draft_poly = []
        elif k == pygame.K_v:
            self.tool = "pan"
        elif k == pygame.K_l:
            self.cycle_layer(-1 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1)
        elif k == pygame.K_TAB:
            self.cycle_tab(-1 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1)
        elif k == pygame.K_n:   # next season
            self._do_action("season_next")
        elif k == pygame.K_s and (pygame.key.get_mods()
                                  & (pygame.KMOD_CTRL | pygame.KMOD_META)):
            self._status(self._save_scene())
        elif k == pygame.K_i:
            self.isovist_follow = not self.isovist_follow
            if not self.isovist_follow:
                self.sim.isovist = None
        elif k == pygame.K_RETURN and drawing:
            self.finish_draft()
        elif k in (pygame.K_COMMA, pygame.K_PERIOD) and (
                pygame.key.get_mods() & pygame.KMOD_SHIFT):
            # < and > rotate the scene
            self.rotate_by(math.radians(10) * (1 if k == pygame.K_PERIOD else -1))
        elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if shift:  # Shift+arrows orbit: left/right yaw, up/down tilt
                if k == pygame.K_LEFT:
                    self.rotate_by(-math.radians(10))
                elif k == pygame.K_RIGHT:
                    self.rotate_by(math.radians(10))
                elif k == pygame.K_UP:
                    self.tilt_by(math.radians(10))
                elif k == pygame.K_DOWN:
                    self.tilt_by(-math.radians(10))
                return
            step = 40 / self.scale
            if k == pygame.K_LEFT:
                self.cx -= step
            elif k == pygame.K_RIGHT:
                self.cx += step
            elif k == pygame.K_UP:
                self.cy += step
            elif k == pygame.K_DOWN:
                self.cy -= step

    def _handle_click(self, pos) -> None:
        wx, wy = self.to_world(*pos)
        t = self.tool
        if t == "lasso":
            if self._lasso_anchor is None:
                self._lasso_anchor = (wx, wy)
                self._status("click the opposite corner")
            else:
                x0, y0 = self._lasso_anchor
                picked = self.select_buildings_in(x0, y0, wx, wy)
                self._lasso_anchor = None
                self._status(f"selected {len(picked)} building(s)")
        elif t == "od_source":
            self.add_source(wx, wy)
            self.mark_dirty()
        elif t == "od_sink":
            self.add_sink(wx, wy)
            self.mark_dirty()
        elif t == "od_delete":
            self._delete_od_at(wx, wy)
            self.mark_dirty()
        elif t == "od_weight":
            self._weight_od_at(wx, wy)
            self.mark_dirty()
        elif t in ("building", "bd_add", "ob_add"):
            # click near the first vertex closes the polygon
            if len(self.draft_poly) >= 3:
                fx, fy = self.to_screen(*self.draft_poly[0])
                if math.hypot(pos[0] - fx, pos[1] - fy) <= self.close_radius_px:
                    self.finish_draft()
                    return
            self.draft_poly.append((wx, wy))
        elif t in ("bd_circle", "bd_rect"):
            self._template_click(wx, wy)
        elif t == "rv_add":
            self.draft_poly.append((wx, wy))
        elif t == "rv_ford":
            r = self._nearest_river(wx, wy)
            if r is None:
                self._status("click on a river to place a ford")
            else:
                self.sim.add_ford(r, wx, wy)
                self.mark_dirty()
                self._status(f"ford on {r.name} ({len(r.fords)} total)")
        elif t == "rv_delete":
            r = self._nearest_river(wx, wy)
            if r is not None:
                self.sim.delete_river(r)
                self.mark_dirty()
                self._status(f"{r.name} removed")
        elif t == "rv_perennial":
            r = self._nearest_river(wx, wy)
            if r is not None:
                r.perennial = not r.perennial
                self.sim.rebuild_river_layers()
                self.mark_dirty()
                self._status(f"{r.name} is now {r.kind}")
        elif t == "bd_delete":
            self._delete_building_at(wx, wy, "building")
            self.mark_dirty()
        elif t == "ob_delete":
            self._delete_building_at(wx, wy, "obstacle")
            self.mark_dirty()
        elif t == "bd_height":
            self._cycle_height_at(wx, wy)
            self.mark_dirty()
        elif t in ("bd_move", "ob_move"):
            self._move_click(wx, wy, t)
            self.mark_dirty()
        elif t == "delete":  # legacy keyboard tool
            self.delete_at(wx, wy)
            self.mark_dirty()

    def _zoom(self, factor: float, pos) -> None:
        wx, wy = self.to_world(*pos)
        self.scale *= factor
        # keep the point under the cursor fixed
        nx, ny = self.to_world(*pos)
        self.cx += wx - nx
        self.cy += wy - ny

    # ------------------------------------------------------------------ loop
    def run(self, duration: Optional[float] = None, max_frames: Optional[int] = None,
            script: Optional[List[Tuple[float, Callable[["Viewer"], None]]]] = None,
            record_dir: Optional[str] = None, record_fps: int = 25) -> None:
        """Main loop.

        ``script`` is an optional list of ``(t_seconds, fn)`` used to drive the
        viewer programmatically. ``duration`` auto-quits after that many seconds.

        Interactive/live mode paces to ``self.fps`` with an explicit sleep. If
        ``record_dir`` is given, the loop instead runs on a *virtual* clock and
        writes one PNG per frame (``record_fps`` frames/second of the script
        timeline) -- a deterministic, headless-friendly way to capture a session
        that a user drives with the same keys/mouse.
        """
        import time

        script = sorted(script or [], key=lambda s: s[0])

        if record_dir is not None:
            self._run_recorded(duration or 20.0, script, record_dir, record_fps)
            return

        si = 0
        target_dt = 1.0 / self.fps
        start = time.perf_counter()
        next_t = start
        while self.running:
            for ev in self.pygame.event.get():
                self._handle_event(ev)
            elapsed = time.perf_counter() - start
            while si < len(script) and script[si][0] <= elapsed:
                script[si][1](self)
                si += 1
            if self.playing:
                for _ in range(self.steps_per_frame):
                    self.sim.step()
            self.render()
            self.frame += 1
            next_t += target_dt
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.perf_counter()
            if duration is not None and elapsed >= duration:
                self.running = False
            if max_frames is not None and self.frame >= max_frames:
                self.running = False
        self.pygame.quit()

    def _run_recorded(self, duration: float, script, record_dir: str, record_fps: int) -> None:
        os.makedirs(record_dir, exist_ok=True)
        script = sorted(script or [], key=lambda s: s[0])
        si = 0
        total = int(duration * record_fps)
        for f in range(total):
            elapsed = f / record_fps
            while si < len(script) and script[si][0] <= elapsed:
                script[si][1](self)
                si += 1
            if self.playing:
                for _ in range(self.steps_per_frame):
                    self.sim.step()
            self.render()
            self.pygame.image.save(self.screen, os.path.join(record_dir, f"{f:05d}.png"))
            self.frame += 1
        self.pygame.quit()

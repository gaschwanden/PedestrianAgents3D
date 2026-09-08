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
    import matplotlib.cm as cm

    lo, hi = float(np.nanmin(elev)), float(np.nanmax(elev))
    norm = (elev - lo) / (hi - lo) if hi > lo else np.zeros_like(elev)
    rgba = cm.get_cmap("terrain")(norm)
    return (rgba[..., :3] * 255).astype(np.uint8)


class Viewer:
    def __init__(self, sim: Simulation, site=None, width: int = 1280, height: int = 800,
                 steps_per_frame: int = 1, fps: int = 30, title: str = "pedsim viewer"):
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

        # camera
        self.scale = 1.0
        self.cx = 0.0
        self.cy = 0.0
        self.fit_view()

        # state
        self.playing = True
        self.tool = "pan"
        self.draft_poly: List[Tuple[float, float]] = []
        self.show_help = True
        self.isovist_follow = False
        self.running = True
        self.frame = 0

        # precompute terrain surface
        self._terrain_surf = None
        if sim.grid.elevation is not None:
            rgb = _terrain_rgb(sim.grid.elevation)  # [ix, iy, 3]
            surf = pygame.surfarray.make_surface(rgb)
            self._terrain_surf = pygame.transform.flip(surf, False, True)

    # ------------------------------------------------------------ transforms
    def fit_view(self) -> None:
        g = self.sim.grid
        dx = max(g.max_x - g.min_x, 1e-6)
        dy = max(g.max_y - g.min_y, 1e-6)
        self.scale = 0.9 * min(self.W / dx, self.H / dy)
        self.cx = (g.min_x + g.max_x) / 2.0
        self.cy = (g.min_y + g.max_y) / 2.0

    def to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        sx = self.W / 2 + (wx - self.cx) * self.scale
        sy = self.H / 2 - (wy - self.cy) * self.scale
        return int(sx), int(sy)

    def to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        wx = self.cx + (sx - self.W / 2) / self.scale
        wy = self.cy - (sy - self.H / 2) / self.scale
        return wx, wy

    # ------------------------------------------------------------- rendering
    def _blit_world_surface(self, surf) -> None:
        g = self.sim.grid
        tlx, tly = self.to_screen(g.min_x, g.max_y)
        w = max(1, int((g.max_x - g.min_x) * self.scale))
        h = max(1, int((g.max_y - g.min_y) * self.scale))
        scaled = self.pygame.transform.smoothscale(surf, (w, h))
        self.screen.blit(scaled, (tlx, tly))

    def _draw_poly(self, poly, color, width=1, fill=False) -> None:
        if len(poly) < 2:
            return
        pts = [self.to_screen(x, y) for x, y in poly]
        if fill and len(pts) >= 3:
            self.pygame.draw.polygon(self.screen, color, pts)
        else:
            self.pygame.draw.polygon(self.screen, color, pts, width)

    def _overlay_field(self, field: np.ndarray, maxv: float, rgb: Tuple[int, int, int]) -> None:
        if maxv <= 0:
            return
        norm = np.clip(field / maxv, 0, 1)
        arr = np.zeros((field.shape[0], field.shape[1], 3), dtype=np.uint8)
        arr[..., 0] = (rgb[0] * norm).astype(np.uint8)
        arr[..., 1] = (rgb[1] * norm).astype(np.uint8)
        arr[..., 2] = (rgb[2] * norm).astype(np.uint8)
        surf = self.pygame.surfarray.make_surface(arr)
        surf = self.pygame.transform.flip(surf, False, True)
        surf.set_colorkey((0, 0, 0))
        surf.set_alpha(200)
        self._blit_world_surface(surf)

    def render(self) -> None:
        pygame = self.pygame
        sim = self.sim
        g = sim.grid
        self.screen.fill((13, 13, 15))

        if self._terrain_surf is not None:
            self._blit_world_surface(self._terrain_surf)

        if sim.site_polygon:
            self._draw_poly(sim.site_polygon, (150, 160, 170), width=2)

        for o in sim.obstacles:
            self._draw_poly(o.footprint.as_xy(), _LAYER_COLORS.get(o.layer, (60, 60, 70)),
                            fill=True)

        facade = sim.analysis_mode in (ANALYSIS_FACADE_VIS, ANALYSIS_FACADE_VIS_O)
        for b in sim.buildings:
            self._draw_poly(b.footprint.as_xy(), (107, 114, 128), fill=True)
            self._draw_poly(b.footprint.as_xy(), (203, 213, 225), width=1)
            if facade:
                self._draw_facade(b)

        if sim.analysis_mode == ANALYSIS_PATHOVERLAP:
            self._overlay_field(g.occupancy, g.max_occupancy, (255, 60, 60))

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

        # isovist
        if sim.isovist is not None and self.isovist_follow:
            poly = [self.to_screen(x, y) for x, y in sim.isovist.polygon()]
            if len(poly) >= 3:
                iso_surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                pygame.draw.polygon(iso_surf, (255, 228, 94, 90), poly)
                self.screen.blit(iso_surf, (0, 0))

        # building draft
        if self.tool == "building" and self.draft_poly:
            pts = [self.to_screen(x, y) for x, y in self.draft_poly]
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, (255, 220, 0), False, pts, 2)
            for px, py in pts:
                pygame.draw.circle(self.screen, (255, 220, 0), (px, py), 3)

        self._draw_hud()
        pygame.display.flip()

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
            f"   {'PLAYING' if self.playing else 'PAUSED'}",
            f"agents: {len(sim.active_agents)}   ticks: {sim.ticks}   "
            f"ODs: {sim.reachable_targets()}   fps: {self.clock.get_fps():.0f}",
        ]
        y = 6
        for ln in lines:
            surf = self.font.render(ln, True, (230, 230, 230))
            self.screen.blit(surf, (8, y))
            y += 20
        if self.show_help:
            help_lines = [
                "SPACE play/pause  . step  [ ] speed   arrows/right-drag pan  wheel/+- zoom  F fit",
                "0-5 analysis modes  C reset analysis   O source  K sink  X delete  B building  I isovist  V pan",
                "H help   Q/ESC quit",
            ]
            y = self.H - 20 * len(help_lines) - 6
            for ln in help_lines:
                surf = self.font.render(ln, True, (170, 190, 210))
                self.screen.blit(surf, (8, y))
                y += 20

    # ------------------------------------------------------------- scene ops
    def set_analysis_mode(self, mode: int) -> None:
        self.sim.set_analysis_mode(mode)

    def add_source(self, wx: float, wy: float, group: int = 1) -> None:
        self.sim.add_od(wx, wy, group=group, origin_weight=1.0, dest_weight=0.0)

    def add_sink(self, wx: float, wy: float, group: int = 0) -> None:
        self.sim.add_od(wx, wy, group=group, origin_weight=0.2, dest_weight=1.0)

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

    def finish_building(self) -> None:
        if len(self.draft_poly) >= 3:
            self.sim.add_building(list(self.draft_poly), height=12)
        self.draft_poly = []

    def isovist_at(self, wx: float, wy: float) -> None:
        try:
            self.sim.compute_isovist(wx, wy, ray_length=3000.0)
        except Exception:
            pass

    # ---------------------------------------------------------------- events
    def _handle_event(self, ev) -> None:
        pygame = self.pygame
        if ev.type == pygame.QUIT:
            self.running = False
        elif ev.type == pygame.KEYDOWN:
            self._handle_key(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                self._handle_click(ev.pos)
            elif ev.button == 4:
                self._zoom(1.15, ev.pos)
            elif ev.button == 5:
                self._zoom(1 / 1.15, ev.pos)
        elif ev.type == pygame.MOUSEMOTION:
            if ev.buttons[2]:  # right-drag pan
                dx, dy = ev.rel
                self.cx -= dx / self.scale
                self.cy += dy / self.scale
            if self.isovist_follow:
                self.isovist_at(*self.to_world(*ev.pos))

    def _handle_key(self, key) -> None:
        pygame = self.pygame
        k = key
        if k in (pygame.K_q, pygame.K_ESCAPE):
            if self.tool == "building" and self.draft_poly:
                self.draft_poly = []
            else:
                self.running = False
        elif k == pygame.K_SPACE:
            self.playing = not self.playing
        elif k == pygame.K_PERIOD:
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
        elif k == pygame.K_i:
            self.isovist_follow = not self.isovist_follow
            if not self.isovist_follow:
                self.sim.isovist = None
        elif k == pygame.K_RETURN and self.tool == "building":
            self.finish_building()
        elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
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
        if self.tool == "od_source":
            self.add_source(wx, wy)
        elif self.tool == "od_sink":
            self.add_sink(wx, wy)
        elif self.tool == "delete":
            self.delete_at(wx, wy)
        elif self.tool == "building":
            self.draft_poly.append((wx, wy))

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

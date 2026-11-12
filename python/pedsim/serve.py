"""Serve the field client, and a small API, on the local network.

A laptop running this is the hub: tablets on the same hotspot load the app
from it and can ask it to run a short ensemble. Online basemap tiles are
proxied here so MapLibre can paint Google / Esri imagery (those hosts do not
send CORS headers that WebGL needs). Proxied tiles are not written into the
PWA cache.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def web_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))


_TILE_SOURCES = {
    "google": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "google-hybrid": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "satellite": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
    "streets": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

_TILE_RE = re.compile(r"^/tiles/([a-z0-9-]+)/(\d+)/(\d+)/(\d+)(?:\.\w+)?$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=web_root(), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        match = _TILE_RE.match(self.path.split("?", 1)[0])
        if match:
            self._proxy_tile(*match.groups())
            return
        super().do_GET()

    def _proxy_tile(self, kind: str, z: str, x: str, y: str) -> None:
        template = _TILE_SOURCES.get(kind)
        if template is None:
            self.send_error(404, "unknown basemap")
            return
        url = template.format(z=z, x=x, y=y)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "pedsim-field/0.3 (local hub tile proxy)",
                "Accept": "image/*,*/*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "image/jpeg")
        except (urllib.error.URLError, TimeoutError, ValueError):
            self.send_error(502, "tile upstream failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        from .ensemble import run_ensemble
        from .scenario import synthetic_scene

        def factory(seed: int):
            scenario = {
                "scene": "synthetic", "seed": seed,
                "num_agents": int(body.get("agents", 12)),
                "steps": int(body.get("steps", 8)),
                "gridsize": 20, "extent_m": 200,
                "population": "", "tasks": "", "respect_chronology": False,
            }
            from .scenario import normalise
            return synthetic_scene(normalise(scenario))

        summary = run_ensemble(factory, n=int(body.get("seeds", 4)),
                               steps=int(body.get("steps", 8)))
        payload = json.dumps({
            "shape": list(summary["mean"].shape),
            "mean_max": float(summary["mean"].max()),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"pedsim field client on http://{host}:{port}")
    server.serve_forever()

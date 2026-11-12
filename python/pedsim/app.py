"""Two-scale navigation: the settlement cluster and the individual village.

The research question runs at two scales that need different data and produce
different answers:

* **Cluster** -- the whole Taş Tepeler group across ~80 km. Rivers and relief
  drive movement; settlements are points you travel between.
* **Village** -- one site. Walls and buildings are the obstacles, from a plan or
  a georeferenced figure, and the relief is nearly flat by comparison.

This module owns the navigation between them: start at the cluster, pick a
settlement, drop into its detailed scene if one exists, and come back. Scenes
are built lazily and cached, so returning to the cluster does not throw away
the simulation you were watching, and edits survive a round trip.

Edits are tracked per scene so the viewer can ask before discarding them, and
saves go through :meth:`~pedsim.simulation.Simulation.save_geometry_versioned`
-- a reconstruction is an interpretation, and you usually want the previous one
back.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from .simulation import Simulation


class Scale(str, Enum):
    REGIONAL = "regional"
    CLUSTER = "cluster"
    SITE = "site"


def slug(name: str) -> str:
    """Filesystem-safe stem for a scene name (Turkish characters included)."""
    table = str.maketrans({"ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "ı": "i",
                           "İ": "I", "ö": "o", "Ö": "O", "ü": "u", "Ü": "U",
                           "ç": "c", "Ç": "C"})
    out = name.translate(table).lower()
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")
    return out or "scene"


@dataclass
class Scene:
    """One navigable scene, built on first use.

    ``builder`` is called at most once; the resulting simulation is cached so
    navigating away and back preserves both the edits and the analysis.
    """

    name: str
    scale: Scale
    builder: Callable[[], Simulation]
    description: str = ""
    site_name: str = ""            # catalogue entry this detail scene belongs to
    dirty: bool = False
    _sim: Optional[Simulation] = field(default=None, repr=False)

    @property
    def built(self) -> bool:
        return self._sim is not None

    def sim(self) -> Simulation:
        if self._sim is None:
            self._sim = self.builder()
        return self._sim

    def save_path(self, save_dir: str) -> str:
        return os.path.join(save_dir, f"{slug(self.name)}.geometry.json")


class TwoScaleApp:
    """Holds the cluster scene plus the detail scenes, and the current one.

    Parameters
    ----------
    cluster:
        The settlement-cluster scene. This is where the user starts.
    details:
        Detail scenes keyed by the catalogue site name they belong to. A site
        with no entry here has no detailed map, and :meth:`has_detail` says so
        rather than opening an empty scene.
    save_dir:
        Where versioned geometry saves go.
    """

    def __init__(self, cluster: Scene, details: Optional[Dict[str, Scene]] = None,
                 save_dir: str = ".", regional: Optional[Scene] = None):
        if cluster.scale is not Scale.CLUSTER:
            raise ValueError("the root scene must be the cluster scale")
        if regional is not None and regional.scale is not Scale.REGIONAL:
            raise ValueError("the regional scene must use Scale.REGIONAL")
        self.cluster = cluster
        self.regional = regional
        self.details: Dict[str, Scene] = dict(details or {})
        self.save_dir = save_dir
        if regional is not None:
            self.current = regional
            self.history = [regional.name]
        else:
            self.current = cluster
            self.history = [cluster.name]

    # ------------------------------------------------------------ navigation
    @property
    def scale(self) -> Scale:
        return self.current.scale

    @property
    def at_cluster(self) -> bool:
        return self.current is self.cluster

    def has_detail(self, site_name: str) -> bool:
        return site_name in self.details

    def detail_names(self) -> List[str]:
        return sorted(self.details)

    def register_detail(self, site_name: str, scene: Scene) -> Scene:
        scene.site_name = site_name
        self.details[site_name] = scene
        return scene

    def enter_detail(self, site_name: str) -> Simulation:
        """Drop into a site's detailed scene. Raises ``KeyError`` if there is
        no detailed map for it -- callers should check :meth:`has_detail`."""
        scene = self.details[site_name]
        self.current = scene
        self.history.append(scene.name)
        return scene.sim()

    def back_to_cluster(self) -> Simulation:
        self.current = self.cluster
        self.history.append(self.cluster.name)
        return self.cluster.sim()

    def enter_cluster(self) -> Simulation:
        """Drop from the regional scene into the settlement cluster."""
        if self.regional is None:
            raise RuntimeError("this app has no regional scene")
        self.current = self.cluster
        self.history.append(self.cluster.name)
        return self.cluster.sim()

    def up(self) -> Simulation:
        """One level up: village to cluster, cluster to region."""
        if self.current.scale is Scale.SITE:
            return self.back_to_cluster()
        if self.regional is not None and self.current is self.cluster:
            self.current = self.regional
            self.history.append(self.regional.name)
            return self.regional.sim()
        return self.current.sim()

    @property
    def at_root(self) -> bool:
        """True when ESC should leave the app rather than go up a scale."""
        if self.regional is not None:
            return self.current is self.regional
        return self.at_cluster

    def breadcrumb(self) -> str:
        if self.regional is None:
            if self.at_cluster:
                return self.cluster.name
            return f"{self.cluster.name}  >  {self.current.name}"
        parts = [self.regional.name]
        if self.current is not self.regional:
            parts.append(self.cluster.name)
        if self.current.scale is Scale.SITE:
            parts.append(self.current.name)
        return " \u203a ".join(parts)

    # ----------------------------------------------------------- edit state
    def mark_dirty(self, dirty: bool = True) -> None:
        self.current.dirty = dirty

    @property
    def dirty(self) -> bool:
        return self.current.dirty

    def dirty_scenes(self) -> List[Scene]:
        scenes = [self.cluster, *self.details.values()]
        if self.regional is not None:
            scenes.insert(0, self.regional)
        return [s for s in scenes if s.dirty]

    # ---------------------------------------------------------------- saving
    def save_current(self, keep: int = 20) -> str:
        """Save the current scene's geometry, archiving the previous version.

        Returns a short human-readable description of what happened, for the
        status line.
        """
        scene = self.current
        path = scene.save_path(self.save_dir)
        os.makedirs(self.save_dir, exist_ok=True)
        archived = scene.sim().save_geometry_versioned(path, keep=keep)
        scene.dirty = False
        name = os.path.basename(path)
        if archived:
            return f"saved {name} (previous kept as {os.path.basename(archived)})"
        return f"saved {name}"

    def load_current(self) -> str:
        scene = self.current
        path = scene.save_path(self.save_dir)
        if not os.path.exists(path):
            return f"no saved geometry for {scene.name}"
        scene.sim().load_geometry_json(path)
        scene.dirty = False
        n = len(Simulation.list_versions(path))
        return f"loaded {os.path.basename(path)} ({n} older version(s) on disk)"

    def versions_of_current(self) -> List[str]:
        return Simulation.list_versions(self.current.save_path(self.save_dir))

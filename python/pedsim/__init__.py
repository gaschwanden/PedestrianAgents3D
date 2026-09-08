"""pedsim -- a Python re-implementation of the PedestrianAgents3D simulation.

Grid-based, vision-driven pedestrian agents for ancient cities and settlements,
with topography-aware (slope-weighted) routing and simple importers for
archaeological site outlines and terrain models.
"""
from .agent import Agent
from .grid import NavGrid
from .importers import (
    ArchaeologicalSite,
    SiteFeature,
    load_site,
    load_topography,
)
from .od import OD
from .simulation import Simulation
from .topography import TerrainCost, Topography

__all__ = [
    "Agent",
    "NavGrid",
    "Simulation",
    "OD",
    "Topography",
    "TerrainCost",
    "ArchaeologicalSite",
    "SiteFeature",
    "load_site",
    "load_topography",
]

__version__ = "0.1.0"

"""pedsim -- a Python re-implementation of the PedestrianAgents3D simulation.

Grid-based, vision-driven pedestrian agents for ancient cities and settlements,
with topography-aware (slope-weighted) routing, DXF/site/terrain importers, the
full analysis suite (path overlap, facade visibility, traces, isovist) and an
editing API for buildings, obstacles, ODs and modules.
"""
from .agent import Agent
from .building import Building
from .dxf import DXFHandler, DXFLine, DXFMesh, DXFPoly
from .footprint import Footprint
from .grid import NavGrid
from .importers import (
    ArchaeologicalSite,
    SiteFeature,
    load_site,
    load_topography,
)
from .isovist import Isovist
from .landmark import Landmark
from .modules import ModulePrototype, PlacedModule
from .od import OD
from .simulation import (
    ANALYSIS_FACADE_VIS,
    ANALYSIS_FACADE_VIS_O,
    ANALYSIS_NONE,
    ANALYSIS_PATHOVERLAP,
    ANALYSIS_TRACES,
    ANALYSIS_TRACES_O,
    Simulation,
)
from .topography import TerrainCost, Topography
from .traces import Trace

__all__ = [
    "Agent",
    "Building",
    "Footprint",
    "NavGrid",
    "Simulation",
    "OD",
    "Topography",
    "TerrainCost",
    "ArchaeologicalSite",
    "SiteFeature",
    "load_site",
    "load_topography",
    "DXFHandler",
    "DXFLine",
    "DXFMesh",
    "DXFPoly",
    "Isovist",
    "Landmark",
    "ModulePrototype",
    "PlacedModule",
    "Trace",
    "ANALYSIS_NONE",
    "ANALYSIS_PATHOVERLAP",
    "ANALYSIS_FACADE_VIS",
    "ANALYSIS_FACADE_VIS_O",
    "ANALYSIS_TRACES",
    "ANALYSIS_TRACES_O",
]

__version__ = "0.2.0"

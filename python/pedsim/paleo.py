"""Early Holocene terrain correction for the Göbekli Tepe region.

A modern DEM shows today's ground surface. The valleys around Göbekli Tepe have
aggraded several metres since the site was in use, so the early Holocene
landscape was more incised than it now looks -- which is exactly the difference
that matters for where people could walk.

The correction implemented here is **point-constrained and deliberately local**.
It rests on the fourteen radiocarbon-dated sediment sequences of the Culap Suyu
basin published (open access, CC-BY) by:

    Nykamp, M., Becker, F., Braun, R., Pöllath, N., Knitter, D., Peters, J.,
    Schütt, B. (2021) "Sediment cascades and the entangled relationship between
    human impact and natural dynamics at the pre-pottery Neolithic site of
    Göbekli Tepe, Anatolia." Earth Surface Processes and Landforms 46(2):
    430-442. https://doi.org/10.1002/esp.5035

Core coordinates, total thicknesses and the 42 calibrated ages are that paper's
Tables I and II. The per-core *aggradation since 10 ka* values are **derived
here** by interpolating between the bracketing dated horizons -- they are not
published numbers, and two things limit them: deposition in this basin is
demonstrably episodic (the paper's own argument concerns pulses at 7.4-7.0 and
5.8-3.3 ka BP), and GT18/GT19 sit ~50 m apart yet differ by more than 3 m, so
lateral variability is of the same order as the correction.

Scope, stated plainly
---------------------
* **Culap Suyu basin** -- correction defensible, see :func:`aggradation_grid`.
* **Harran plain** -- *no correction is possible.* There is no Holocene isopach,
  no coring transect and no depth-to-Neolithic data for the plain; the 2023
  Taş Tepeler palaeoenvironment team names this gap as an open aspiration.
  Worse, Rosen's Kazane Höyük sequence suggests parts of the northern plain were
  **eroded** rather than buried, so even the sign is uncertain. Use modern
  topography there and say so.
* **Euphrates corridor / Nevalı Çori** -- a modern DEM returns the Atatürk
  reservoir surface, not terrain. No correction helps; pre-1992 sources
  (CORONA stereo) are required.
* **Channel positions** -- unconstrained at 10 ka. Nobody has mapped the Culap
  or Mucid palaeochannels; do not move rivers. The gross course of the Balikh
  was already modern by the end of the Pleistocene.
* **Timing** -- treat 10-8 ka as geomorphically *stable*. The best available
  study finds no erosion/deposition signal at the Younger Dryas-Holocene
  transition or during the PPN, so a time-varying model is unwarranted.
"""
from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

#: CRS of the core coordinates below: UTM zone 37N, WGS84.
CORE_CRS = "EPSG:32637"

#: Vertical RMSE of Copernicus GLO-30 in Türkiye (m). A correction smaller than
#: this is inside the DEM's own noise -- see :func:`meaningful`.
GLO30_VERTICAL_RMSE_M = 2.2


@dataclass(frozen=True)
class Core:
    """One sediment sequence from Nykamp et al. 2021, Table I.

    ``aggradation_m`` is the derived depth of the ~10,000 cal BP surface below
    today's ground level; ``uncertainty_m`` is a one-sided spread, not a formal
    error. ``basis`` says where the number comes from.
    """

    id: str
    easting: float
    northing: float
    elevation_m: float
    thickness_cm: int
    catchment_km2: float
    compartment: str
    aggradation_m: float
    uncertainty_m: float
    basis: str


#: The fourteen Culap Suyu cores. Thicknesses and coordinates are published;
#: aggradation values are derived (see the module docstring).
CULAP_CORES: Tuple[Core, ...] = (
    # Slope toes: total sequence is thin and entirely Late Holocene, so the
    # early Holocene surface is effectively bedrock -- subtract the lot.
    Core("GT03", 493656, 4118322, 661.4, 74, 0.003, "slope toe", 0.74, 0.15,
         "published thickness; all dated horizons Late Holocene"),
    Core("GT16", 494800, 4119940, 682.7, 78, 0.005, "slope toe", 0.78, 0.15,
         "published thickness; all dated horizons Late Holocene"),
    Core("GT15", 494912, 4119993, 679.9, 60, 0.006, "slope toe", 0.60, 0.15,
         "published thickness; all dated horizons Late Holocene"),
    Core("GT14", 494632, 4120264, 682.8, 80, 0.021, "slope toe", 0.80, 0.15,
         "published thickness; youngest horizon 661-551 cal BP"),
    # Proximal piedmont: whole sequence Bronze Age or younger.
    Core("GT11", 494922, 4120378, 670.9, 224, 0.523, "piedmont", 2.24, 0.5,
         "published thickness; sequence post-dates the window"),
    Core("GT12", 494925, 4120380, 670.9, 240, 0.523, "piedmont", 2.40, 0.5,
         "published thickness; sequence post-dates the window"),
    Core("GT06", 493946, 4117785, 641.3, 238, 1.962, "piedmont", 2.38, 0.5,
         "published thickness; sequence post-dates the window"),
    Core("GT05", 494017, 4117664, 638.3, 192, 2.026, "piedmont", 1.92, 0.5,
         "published thickness; sequence post-dates the window"),
    # Distal piedmont: dated, but wildly variable over short distances.
    Core("GT18", 501015, 4120596, 565.9, 600, 14.55, "piedmont", 5.50, 2.0,
         "lower bound only: 8.5 ka at 553 cm, 10 ka horizon below core base"),
    Core("GT19", 500973, 4120569, 566.5, 200, 14.55, "piedmont", 1.90, 0.6,
         "interpolated; 9.1 ka at 171 cm"),
    Core("GT22", 501202, 4121326, 557.0, 655, 21.64, "piedmont", 3.80, 1.5,
         "interpolated between 9.3 ka at 375 cm and 16.6 ka at 473 cm"),
    # Culap floodplain: the only compartment with a continuous record.
    Core("GT17", 502949, 4118940, 534.2, 679, 434.9, "floodplain", 3.10, 2.0,
         "interpolated across a wide bracket (7.1 ka at 250 cm, 13.3 ka at 369 cm)"),
    Core("GT20", 503214, 4118629, 530.8, 800, 436.2, "floodplain", 5.30, 1.0,
         "interpolated between 6.9 ka at 447 cm and 11.2 ka at 566 cm"),
    Core("GT21", 501326, 4111007, 490.5, 530, 481.7, "floodplain", 1.55, 2.0,
         "extrapolated up from 11.7 ka at 167 cm; no younger date"),
)

#: Fallback correction by landform unit, for cells too far from any core, in
#: metres ``(low, best, high)``. The landform units follow the geomorphological
#: map of Knitter et al. 2019 (Land 8(4): 72, open access) -- limestone and
#: basalt plateaus, scree slopes, undulating plains, flat plains, alluvial
#: plains. Note the plateau value is 0 because the upper slopes are published as
#: "usually devoid of sediments".
COMPARTMENT_AGGRADATION: Dict[str, Tuple[float, float, float]] = {
    "plateau": (0.0, 0.0, 0.2),
    "scree slope": (0.0, 0.1, 0.3),
    "slope toe": (0.6, 0.7, 0.8),
    "piedmont": (1.9, 2.4, 5.5),
    "undulating plain": (0.3, 1.0, 2.0),
    "floodplain": (1.4, 3.5, 5.3),
    "alluvial plain": (1.4, 3.5, 5.3),
}

#: Rough extent over which the core-based correction is defensible, as
#: ``(min_e, min_n, max_e, max_n)`` in :data:`CORE_CRS` with a 5 km margin.
CULAP_EXTENT: Tuple[float, float, float, float] = (
    min(c.easting for c in CULAP_CORES) - 5000,
    min(c.northing for c in CULAP_CORES) - 5000,
    max(c.easting for c in CULAP_CORES) + 5000,
    max(c.northing for c in CULAP_CORES) + 5000,
)


def meaningful(correction_m: float) -> bool:
    """Is a correction bigger than the DEM's own vertical noise?

    Floodplain corrections (~5 m) clear GLO-30's 2.2 m RMSE; plateau ones (0 m)
    are trivially right; piedmont ones (~2 m) are marginal. Conveniently, the
    correction bites exactly where it changes routing -- the valley floors.
    """
    return abs(correction_m) > GLO30_VERTICAL_RMSE_M


def aggradation_at(easting: float, northing: float, power: float = 2.0,
                   max_dist_m: float = 6000.0) -> Tuple[float, float]:
    """Aggradation since ~10 ka at one point, by inverse-distance weighting of
    the cores. Returns ``(metres, uncertainty_m)``.

    Beyond ``max_dist_m`` from every core there is no basis for a correction and
    this returns ``(0.0, inf)`` -- an explicit "unknown", not a quiet zero.
    """
    best = 0.0
    unc = 0.0
    wsum = 0.0
    for c in CULAP_CORES:
        d = math.hypot(easting - c.easting, northing - c.northing)
        if d < 1.0:
            return (c.aggradation_m, c.uncertainty_m)
        if d > max_dist_m:
            continue
        w = d ** (-power)
        best += w * c.aggradation_m
        unc += w * c.uncertainty_m
        wsum += w
    if wsum == 0.0:
        return (0.0, float("inf"))
    return (best / wsum, unc / wsum)


def aggradation_grid(eastings: np.ndarray, northings: np.ndarray,
                     power: float = 2.0, max_dist_m: float = 6000.0,
                     compartments: Optional[np.ndarray] = None
                     ) -> Tuple[np.ndarray, np.ndarray]:
    """Vectorised :func:`aggradation_at` over a grid of coordinates.

    Parameters
    ----------
    eastings, northings:
        Arrays of the same shape, in :data:`CORE_CRS`.
    compartments:
        Optional array of landform-unit names (keys of
        :data:`COMPARTMENT_AGGRADATION`) used wherever no core is within
        ``max_dist_m``. Without it, out-of-range cells get 0 m and infinite
        uncertainty.

    Returns
    -------
    ``(correction_m, uncertainty_m)`` -- subtract ``correction_m`` from a modern
    DEM to approximate the early Holocene surface.
    """
    e = np.asarray(eastings, dtype=float)
    n = np.asarray(northings, dtype=float)
    if e.shape != n.shape:
        raise ValueError("eastings and northings must have the same shape")

    num = np.zeros(e.shape, dtype=float)
    unum = np.zeros(e.shape, dtype=float)
    den = np.zeros(e.shape, dtype=float)
    for c in CULAP_CORES:
        d = np.hypot(e - c.easting, n - c.northing)
        np.maximum(d, 1.0, out=d)
        w = np.where(d <= max_dist_m, d ** (-power), 0.0)
        num += w * c.aggradation_m
        unum += w * c.uncertainty_m
        den += w

    have = den > 0
    corr = np.zeros(e.shape, dtype=float)
    unc = np.full(e.shape, np.inf, dtype=float)
    corr[have] = num[have] / den[have]
    unc[have] = unum[have] / den[have]

    if compartments is not None:
        comp = np.asarray(compartments)
        if comp.shape != e.shape:
            raise ValueError("compartments must match the coordinate shape")
        for name, (lo, best, hi) in COMPARTMENT_AGGRADATION.items():
            sel = (~have) & (comp == name)
            if sel.any():
                corr[sel] = best
                unc[sel] = max(best - lo, hi - best)
    return corr, unc


def correct_dem(elevation: np.ndarray, eastings: np.ndarray, northings: np.ndarray,
                **kw) -> Tuple[np.ndarray, np.ndarray]:
    """Strip post-10 ka aggradation from a modern DEM.

    Returns ``(paleo_elevation, uncertainty_m)``. Cells with no basis for a
    correction are returned unchanged, with infinite uncertainty, so downstream
    code can mask or flag them rather than mistake them for corrected ground.
    """
    corr, unc = aggradation_grid(eastings, northings, **kw)
    return np.asarray(elevation, dtype=float) - np.where(np.isfinite(corr), corr, 0.0), unc


def cores_by_compartment() -> Dict[str, List[Core]]:
    out: Dict[str, List[Core]] = {}
    for c in CULAP_CORES:
        out.setdefault(c.compartment, []).append(c)
    return out


#: Environmental settings for the cluster-scale friction layers, from the
#: on-site archaeobotany (90% of Göbekli Tepe charcoal is pistachio and almond;
#: fauna is open-grassland Ovis/Capra/Gazella/Equus). Deliberately *not* closed
#: oak forest: the off-site pollen cores suggest that, but it is contradicted by
#: the site's own archaeobotany and the cores' organic-matter dates have known
#: mean-residence-time problems.
VEGETATION = {
    "default": "open herbaceous steppe with scattered pistachio and almond",
    "valley_bottoms": "denser woody cover",
    "higher_elevations": "denser woody cover",
    "do_not_model": "closed oak forest",
}

#: Water: what is evidenced, and what is merely assumed.
WATER_NOTES = {
    "gobekli_springs": "none -- positively established, not an absence of evidence",
    "mucid_dere": "seasonal/ephemeral stream ~3 km west; no hydrological study exists",
    "edene_lake": "~5 km NE; attested by a single sentence, no coordinates or hydrology",
    "germus_lake": "~5 km SW; same single-sentence provenance",
    "gobekli_cisterns_m3": 153.0,   # Herrmann & Schmidt 2012; other figures in the
                                    # literature differ by two orders of magnitude
    "karahan_water_system": "500 m north: cisterns plus 133 settling pools over ~2 ha",
    "urfa_harran_karst": "Eocene plumbing certainly existed; outlet activity at 10 ka "
                         "is unevidenced -- treat as assumed",
}

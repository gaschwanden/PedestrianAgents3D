"""Published site plans, geophysics and 3D models — what exists, and what we can import.

Village-scale routing needs **walls in plan**. For these settlements that means
hand-drawn excavation plates, geophysical interpretations, or (rarely) a 3D
mesh. None of them ship georeferenced with the simulation, so every entry here
says three things:

* whether a **usable plan** exists in print or as open data,
* whether it carries a **scale / north / grid** we can pin with
  :mod:`pedsim.plans`,
* how to get it (URL, open-access or not).

This is a finding aid, not a download of the plates. The drawings remain under
their publishers' copyright; the importer expects you to supply a scan you are
allowed to use.

Confidence is about the *plan*, not the site coordinate (that lives in
:mod:`pedsim.sites`). A site can have a published lat/lon and still have no
importable architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class PlanKind(str, Enum):
    ARCHITECTURE = "architecture"   # excavated walls in plan
    GEOPHYSICS = "geophysics"       # magnetometry / GPR interpretation
    TOPOGRAPHY = "topography"       # contours / DEM of the mound
    PHOTO = "photo"                 # drone/oblique; not a drawing
    MODEL_3D = "model_3d"           # mesh / point cloud
    REGIONAL = "regional"           # several sites on one map


class Access(str, Enum):
    OPEN = "open"                   # PDF or data file, no paywall
    REGISTER = "register"           # free after login / proposal
    PAYWALL = "paywall"
    UNVERIFIED = "unverified"       # cited, not opened here


class Importability(str, Enum):
    """Can :mod:`pedsim.plans` turn this into walls today?"""

    YES = "yes"                     # scale or grid present; architecture
    WITH_CONTROL = "with_control"   # plan exists; needs two known points
    GEOPHYSICS = "geophysics"       # walls-as-anomalies, not excavated lines
    NO = "no"                       # photo, too coarse, or no drawing
    UNKNOWN = "unknown"             # figure not inspected


@dataclass(frozen=True)
class PlanSource:
    """One published figure or dataset."""

    site: str                       # catalogue name in :mod:`pedsim.sites`
    title: str
    kind: PlanKind
    citation: str
    url: str = ""
    access: Access = Access.UNVERIFIED
    importability: Importability = Importability.UNKNOWN
    scale_bar: Optional[bool] = None     # None = not verified
    north_arrow: Optional[bool] = None
    grid: str = ""                       # e.g. "L09 10 m excavation squares"
    extent_m: str = ""
    note: str = ""


# ------------------------------------------------------------------ Göbekli
GOBEKLI: List[PlanSource] = [
    PlanSource(
        site="Göbeklitepe",
        title="Southeast hollow: special buildings A–D and adjacent rectangular houses",
        kind=PlanKind.ARCHITECTURE,
        citation="Clare, L. (2024) Documenta Praehistorica 51, Fig. 4. "
                 "Drawing: M. Kinzel, DAI Göbeklitepe Project 2024.",
        url="https://journals.uni-lj.si/DocumentaPraehistorica/article/download/18771/16444/65967",
        access=Access.OPEN,
        importability=Importability.WITH_CONTROL,
        scale_bar=None,
        north_arrow=None,
        grid="trenches L09-58 … L09-80 (DAI 10 m squares)",
        extent_m="main excavation area, on the order of 50–80 m",
        note="Best currently open architectural plan of the excavated enclosures. "
             "The PDF caption does not state a scale bar; the labelled 10 m "
             "trench grid is the control-point route. Buildings A–D are "
             "multi-phase and shrink over time — this plate is a composite.",
    ),
    PlanSource(
        site="Göbeklitepe",
        title="World Heritage inscribed property, topographic map 1:25 000",
        kind=PlanKind.TOPOGRAPHY,
        citation="UNESCO / MoCT (2018) Nomination 1572, Map of the Inscribed Property "
                 "(whc.unesco.org/document/168770).",
        url="https://whc.unesco.org/document/168770",
        access=Access.OPEN,
        importability=Importability.NO,
        scale_bar=True,
        north_arrow=None,
        extent_m="nominated property 126 ha + buffer 461 ha",
        note="Use at cluster scale, not village scale: 1:25 000 does not resolve walls. "
             "The tell itself is ~300 m across / ~9 ha.",
    ),
    PlanSource(
        site="Göbeklitepe",
        title="Geomagnetic / GPR surveys of unexcavated enclosures",
        kind=PlanKind.GEOPHYSICS,
        citation="DAI Göbekli Tepe Project; summarised in The Tepe Telegrams, "
                 "18 July 2018, ‘Looking beneath the surface’.",
        url="https://www.dainst.blog/the-tepe-telegrams/2018/07/18/"
            "looking-beneath-the-surface-geophysical-surveys-at-gobekli-tepe/",
        access=Access.OPEN,
        importability=Importability.GEOPHYSICS,
        note="The blog is a discussion of published survey, not the georeferenced "
             "raster. The mound-wide ~20 enclosures live in DAI reports "
             "(e.g. Clare 2020 e-Forschungsberichte) — inspect the PDF figures "
             "for a scale bar before importing.",
    ),
    PlanSource(
        site="Göbeklitepe",
        title="Photogrammetric mesh of the excavated hollow (fan model)",
        kind=PlanKind.MODEL_3D,
        citation="rmark, Sketchfab ‘Gobekli Tepe’, from ~400 photographs.",
        url="https://sketchfab.com/3d-models/gobekli-tepe-5a4d25c355ff48d59ab76c36812b9cf3",
        access=Access.OPEN,
        importability=Importability.NO,
        extent_m="excavated area only",
        note="3.3 M triangles / 1.6 M vertices; Sketchfab lists it as free to download. "
             "Tourist/hobby photogrammetry, not a survey mesh. Useful as a visual "
             "check, not as walls.",
    ),
]

# ------------------------------------------------------------- Karahan / Sayburç
KARAHAN: List[PlanSource] = [
    PlanSource(
        site="Karahantepe",
        title="Western Terrace: structures AA, AB, AD (photographs and one section)",
        kind=PlanKind.ARCHITECTURE,
        citation="Karul, N. (2021) ‘Buried Buildings at Pre-Pottery Neolithic "
                 "Karahantepe’, Türk Arkeoloji ve Etnografya Dergisi 82. "
                 "Figs 2, 5–8.",
        url="https://taed.ktb.gov.tr/Eklenti/108276,82--necmi-karul--"
            "buried-buildings-at-pre-pottery-neolit-.pdf?0=",
        access=Access.OPEN,
        importability=Importability.NO,
        note="Open-access and the right structures (AB is the 7×6 m pillar room, "
             "AD ~23 m across), but the published figures in this paper are "
             "photographs and a north–south section (Fig. 8), not a measured "
             "site plan. A line-drawn overall plan has not been verified in this "
             "PDF. KST (Kazı Sonuçları Toplantısı) reports for 2020– are the "
             "next place to look.",
    ),
]

SAYBURC: List[PlanSource] = [
    PlanSource(
        site="Sayburç",
        title="Communal building, vertical drone photograph",
        kind=PlanKind.PHOTO,
        citation="Özdoğan, E. (2023) Antiquity — narrative relief at Sayburç, Fig. 2.",
        url="",
        access=Access.PAYWALL,
        importability=Importability.NO,
        note="Inspected via secondary reports of the figures: Fig. 2 is a drone "
             "shot of one building, no scale bar or north arrow reported. No "
             "settlement-wide line plan found in that article.",
    ),
]

SEFERTEPE: List[PlanSource] = [
    PlanSource(
        site="Sefertepe",
        title="No verified architectural plan",
        kind=PlanKind.ARCHITECTURE,
        citation="",
        importability=Importability.NO,
        note="Survey mentions exist (Güler, Çelik & Güler 2012 Anadolu 38 for the "
             "Viranşehir district). A published excavation plan of the architecture "
             "was not found. The site still has two conflicting coordinates "
             "(see pedsim.sites).",
    ),
]

CAKMAKTEPE: List[PlanSource] = [
    PlanSource(
        site="Çakmaktepe",
        title="2024 season overview and northern housing area",
        kind=PlanKind.PHOTO,
        citation="Şahin, F. (2025) ‘Çakmaktepe’den Avcı-Toplayıcı Yerleşiklere Dair "
                 "Yeni Veriler’, Arkeoloji Dergisi. Figs 4–7.",
        url="https://dergipark.org.tr/en/download/article-file/4726240",
        access=Access.OPEN,
        importability=Importability.NO,
        note="Open-access, and the text is useful (round pit-houses 3.5–6 m, two "
             "special buildings, G7/G8 20×20 m trenches, settlement ~100×80 m). "
             "Figs 4–5 are photographs labelled as such, not inked plans. Line "
             "drawings, if they exist, are more likely in KST 42(2) and 43(1).",
    ),
]

# ------------------------------------------------------------- Nevalı Çori group
NEVALI: List[PlanSource] = [
    PlanSource(
        site="Nevalı Çori",
        title="Schematic settlement plans, building levels I–III",
        kind=PlanKind.ARCHITECTURE,
        citation="Hauptmann, H. (1999) in Özdoğan & Başgelen (eds.) Neolithic in "
                 "Turkey, figs 1–3 (levels I, II, III). Cult building 13C also "
                 "Hauptmann 1993, Abb. 9.",
        url="https://www.ethesis.net/anatolia/anatolia.pdf",
        access=Access.OPEN,
        importability=Importability.WITH_CONTROL,
        scale_bar=None,
        north_arrow=None,
        extent_m="terrace settlement; cult building 13C ~13.3 m square",
        note="The most complete village plan in the group, because the site was "
             "fully excavated before flooding. The originals are in Hauptmann's "
             "monographs (not all open). Ercoskun's thesis reproduces the level "
             "plans (Ill. 5–8) and notes channel-house details at 1:20. The site "
             "is under the Atatürk reservoir: a modern DEM is water, not ground. "
             "Pre-flood topography: CORONA Atlas (University of Arkansas CAST), "
             "georeferenced 1960s imagery, free for non-commercial use.",
    ),
]

HARBETSUVAN: List[PlanSource] = [
    PlanSource(
        site="Harbetsuvan Tepesi",
        title="Magnetometry / GPR of the whole small settlement",
        kind=PlanKind.GEOPHYSICS,
        citation="Tada et al. (2026) Archaeological Prospection, "
                 "doi:10.1002/arp.70037. Data: Zenodo 10.5281/zenodo.18979006.",
        url="https://zenodo.org/records/18979006",
        access=Access.OPEN,
        importability=Importability.GEOPHYSICS,
        note="Best plan-like dataset for this site: geophysics of an entire "
             "EPPNB hamlet, with the supporting rasters on Zenodo (several GB). "
             "Çelik 2016 Documenta Praehistorica 43 is photographs of a round "
             "building and rectangular houses, not a measured plan. KST trench "
             "drawings (K11, K7, K4) exist in Uludağ's Turkish report.",
    ),
]

AYANLAR: List[PlanSource] = [
    PlanSource(
        site="Ayanlar Höyük",
        title="No verified architectural plan",
        kind=PlanKind.ARCHITECTURE,
        citation="Çelik survey publications; TAY Project entry.",
        importability=Importability.NO,
        note="Gre Hut / Ayanlar is located but a published wall plan was not found. "
             "Do not confuse with Gre Fılla.",
    ),
]

HAMZAN: List[PlanSource] = [
    PlanSource(
        site="Hamzan Tepe",
        title="No verified architectural plan",
        kind=PlanKind.ARCHITECTURE,
        citation="Çelik survey publications.",
        importability=Importability.NO,
        note="Known from survey; no excavation plan found.",
    ),
]

# ---------------------------------------------------------- remaining / sparse
GURCUTEPE: List[PlanSource] = [
    PlanSource(
        site="Gürcütepe",
        title="Soundings on four low tells; main excavation Gürcütepe II",
        kind=PlanKind.ARCHITECTURE,
        citation="Beile-Bohn, Gerber, Morsch & Schmidt (1998) Istanbuler "
                 "Mitteilungen 48: 5–78; Schmidt (2000) IM 50: 5–41.",
        access=Access.PAYWALL,
        importability=Importability.UNKNOWN,
        note="The DAI report almost certainly contains trench plans — not opened "
             "here. The four hills are now under modern building. The Wikidata "
             "coordinate that circulates is Kazane Höyük, not Gürcütepe.",
    ),
]

YENI_MAHALLE: List[PlanSource] = [
    PlanSource(
        site="Şanlıurfa Yeni Mahalle",
        title="Rescue excavation; Urfa Man findspot",
        kind=PlanKind.ARCHITECTURE,
        citation="Çelik, B. (2000) Neo-Lithics 2–3/00, and later notes.",
        importability=Importability.NO,
        note="Urban rescue. No usable settlement plan found; the site is under "
             "the modern city around Balıklıgöl.",
    ),
]

YOGUNBURC: List[PlanSource] = [
    PlanSource(
        site="Yoğunburç",
        title="Excavation began 2026; no plan yet",
        kind=PlanKind.ARCHITECTURE,
        citation="Anatolian Archaeology news reports, July 2026 (Gan Caichao / "
                 "Şanlıurfa Museum).",
        importability=Importability.NO,
        note="Previously unexcavated. First-season finds (beads, flint) only.",
    ),
]

MENDIKTEPE: List[PlanSource] = [
    PlanSource(
        site="Mendiktepe",
        title="BIAA / Liverpool excavation 2023– ; no published plan yet",
        kind=PlanKind.ARCHITECTURE,
        citation="Baird, D. (2025) ‘Mendiktepe 2025’, Heritage Türkiye, BIAA.",
        url="https://biaa.ac.uk/wp-content/uploads/2026/01/18-HT2025-Mendiktepe.pdf",
        access=Access.OPEN,
        importability=Importability.NO,
        note="PPNA. The report locates the site 15 km southwest of Şanlıurfa and "
             "1.3 km northeast of Mendik village — a description, not a "
             "coordinate. No architectural plan in this short report.",
    ),
]

SOGUT: List[PlanSource] = [
    PlanSource(
        site="Söğüt Tarlası",
        title="No verified plan or coordinate",
        kind=PlanKind.ARCHITECTURE,
        citation="Survey aliases: Biris Mezarlığı, Küçük Gölbaşı, U 51/1-2.",
        importability=Importability.NO,
        note="Still a gap in both location and architecture.",
    ),
    PlanSource(
        site="Biris Mezarlığı",
        title="No verified plan or coordinate",
        kind=PlanKind.ARCHITECTURE,
        citation="Surveyed with Söğüt Tarlası; mound 120 x 25 m (TAY).",
        importability=Importability.NO,
        note="Still a gap in both location and architecture.",
    ),
]

TASLI: List[PlanSource] = [
    PlanSource(
        site="Taşlı Tepe",
        title="Survey site; no excavation plan found",
        kind=PlanKind.ARCHITECTURE,
        citation="Çelik publications on the Şanlıurfa PPN survey.",
        importability=Importability.NO,
    ),
]

KURT: List[PlanSource] = [
    PlanSource(
        site="Kurt Tepesi",
        title="Survey site; no excavation plan found",
        kind=PlanKind.ARCHITECTURE,
        citation="Çelik publications; alias Kuça Gur.",
        importability=Importability.NO,
    ),
]

REGIONAL: List[PlanSource] = [
    PlanSource(
        site="",
        title="Şanlıurfa desert kites and PPN settlements",
        kind=PlanKind.REGIONAL,
        citation="Şahin, F. & Massa, M. (2024) Antiquity 99. "
                 "CC BY-NC-ND 4.0. Bilkent repository PDF.",
        url="https://repository.bilkent.edu.tr/items/"
            "719b5ffc-2901-4782-9841-37509112bb02",
        access=Access.OPEN,
        importability=Importability.NO,
        note="Regional satellite-based map of hunting kites, not village walls. "
             "Useful for landscape context around the cluster.",
    ),
    PlanSource(
        site="",
        title="CORONA Atlas of the Middle East — pre-dam landscape",
        kind=PlanKind.TOPOGRAPHY,
        citation="University of Arkansas CAST. Georeferenced 1960s CORONA, "
                 "~1.8 m, free for non-commercial use.",
        url="https://corona.cast.uark.edu/",
        access=Access.OPEN,
        importability=Importability.NO,
        note="The only honest terrain for Nevalı Çori (flooded 1992). Stereo "
             "pairs can yield a DEM; that is a separate photogrammetry job, "
             "not a wall plan.",
    ),
]


SOURCES: List[PlanSource] = (
    GOBEKLI + KARAHAN + SAYBURC + SEFERTEPE + CAKMAKTEPE
    + NEVALI + HARBETSUVAN + AYANLAR + HAMZAN
    + GURCUTEPE + YENI_MAHALLE + YOGUNBURC + MENDIKTEPE
    + SOGUT + TASLI + KURT + REGIONAL
)


def for_site(name: str) -> List[PlanSource]:
    """Plans attached to one catalogue site (aliases resolved via :mod:`pedsim.sites`)."""
    from . import sites as _sites

    site = _sites.find(name)
    wanted = {site.name, *site.aliases}
    return [p for p in SOURCES if p.site in wanted]


def importable(site: Optional[str] = None) -> List[PlanSource]:
    """Sources we can actually turn into a layer (architecture with a grid, or
    geophysics with a raster)."""
    ok = (Importability.YES, Importability.WITH_CONTROL, Importability.GEOPHYSICS)
    rows = for_site(site) if site else SOURCES
    return [p for p in rows if p.importability in ok]


def has_village_plan(name: str) -> bool:
    """True if a village-scale scene would have walls to import, not just DEM."""
    return any(
        p.importability in (Importability.YES, Importability.WITH_CONTROL,
                            Importability.GEOPHYSICS)
        for p in for_site(name)
    )


def summary() -> Dict[str, str]:
    """One-line status per site, for the README / HUD."""
    from . import sites as _sites

    out: Dict[str, str] = {}
    for s in _sites.SITES:
        plans = for_site(s.name)
        if not plans:
            out[s.name] = "no plan recorded"
            continue
        best = min(plans, key=lambda p: {
            Importability.YES: 0, Importability.WITH_CONTROL: 1,
            Importability.GEOPHYSICS: 2, Importability.UNKNOWN: 3,
            Importability.NO: 4,
        }[p.importability])
        out[s.name] = f"{best.importability.value}: {best.title}"
    return out

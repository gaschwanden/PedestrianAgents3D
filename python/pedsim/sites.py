"""Catalogue of the Taş Tepeler / Pre-Pottery Neolithic sites around Şanlıurfa.

The cluster-scale model needs to know where the settlements are, when they were
occupied, and -- just as important -- **how well each of those is actually
known**. Several of these sites have never had a coordinate published; two have
conflicting ones; one widely-circulated value belongs to a different site
altogether. Rather than quietly pick a number, every entry carries a
:class:`Confidence` so an analysis can exclude the weak ones and a figure can
mark them honestly.

Coordinates are WGS84 decimal degrees. Dates are calibrated BC (positive
numbers, larger = earlier), as published; ``None`` where no date exists.

Sources are cited per entry. The survey behind this table is summarised in the
project notes; the short keys are:

* KE       -- Kültür Envanteri (Turkish cultural inventory), kulturenvanteri.com
* Celik06  -- Çelik, B. (2006) Neo-Lithics 1/06: 23-25
* Celik10  -- Çelik, B. (2010) Documenta Praehistorica 37: 257-268
* Celik16  -- Çelik, B. (2016) Documenta Praehistorica 43: 421-
* Celik17  -- Çelik, B. (2017) Documenta Praehistorica 44: 360-367
* CelikGuler11 -- Çelik & Güler (2011) Anadolu/Anatolia 37
* Ozdogan24 -- Özdoğan, E. (2024) Documenta Praehistorica 51
* Karul21  -- Karul, N. (2021) Türk Arkeoloji ve Etnografya Dergisi 86: 22
* Baird25  -- Baird, D. (2025) BIAA annual report, "Mendiktepe 2025"
* BeileBohn98 -- Beile-Bohn et al. (1998) Istanbuler Mitteilungen 48: 5-78
* Hauptmann07 -- Hauptmann, H. (2007/2011) in The Neolithic in Turkey
* DEFC     -- Digitizing Early Farming Cultures (ÖAW) site records
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Confidence(str, Enum):
    """How much to trust a site's coordinate."""

    PUBLISHED = "published"      # a coordinate printed in an excavation report
    APPROXIMATE = "approximate"  # curated gazetteer, or inferred from a description
    CONFLICTING = "conflicting"  # two or more irreconcilable published values
    UNKNOWN = "unknown"          # no coordinate published anywhere found


@dataclass
class Site:
    """One settlement, with its provenance attached.

    Parameters
    ----------
    lat, lon:
        WGS84 decimal degrees, or ``None`` when unlocated.
    confidence:
        Quality of the coordinate -- see :class:`Confidence`.
    start_bc, end_bc:
        Calibrated BC, larger first (``9500, 8000`` = 9500-8000 cal BC).
    alt_coord:
        The rival value for a ``CONFLICTING`` site, so both can be plotted.
    official:
        One of the twelve sites on the Ministry of Culture's Taş Tepeler list.
    date_quality:
        ``radiocarbon`` / ``typological`` / ``none``. Filled after the table
        from the note (a mention of 14C) so a guessed lab date is never
        written in by hand.
    start_bc_sd, end_bc_sd:
        Optional one-sigma year widths for ensemble sampling. ``None`` means
        the bound is not sampled.
    phase_ids:
        Village phases this settlement record is tied to. Usually empty; the
        phase list lives on the village geometry.
    pin:
        Optional ``always_on`` / ``always_off`` override for what-if runs.
    """

    name: str
    lat: Optional[float]
    lon: Optional[float]
    confidence: Confidence
    period: str = ""
    start_bc: Optional[int] = None
    end_bc: Optional[int] = None
    elevation_m: Optional[float] = None
    area_ha: Optional[float] = None
    setting: str = ""
    aliases: Tuple[str, ...] = ()
    official: bool = False
    alt_coord: Optional[Tuple[float, float]] = None
    #: A point inside the area the descriptions pin an unlocated site to. It is
    #: a placeholder so the site can take part in a run, never a location:
    #: ``lat``/``lon`` stay ``None`` and every client marks the site as unsure.
    search_coord: Optional[Tuple[float, float]] = None
    #: For a ``CONFLICTING`` site: which of the two values to *work* on, when
    #: independent evidence favours one. ``"alt"`` or ``""`` (the first). The
    #: conflict stays recorded; this only picks the working position.
    prefer: str = ""
    sources: Tuple[str, ...] = ()
    note: str = ""
    phase_ids: Tuple[str, ...] = ()
    date_quality: str = "none"
    start_bc_sd: Optional[float] = None
    end_bc_sd: Optional[float] = None
    pin: Optional[str] = None

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def usable(self) -> bool:
        """Good enough to route on: located and not a coin-toss between two
        points kilometres apart."""
        return self.located and self.confidence in (
            Confidence.PUBLISHED, Confidence.APPROXIMATE)

    def __str__(self) -> str:
        where = f"{self.lat:.5f}, {self.lon:.5f}" if self.located else "unlocated"
        return f"{self.name} ({where}, {self.confidence.value})"


# ---------------------------------------------------------------------------
# The catalogue. Order: the official twelve first, then related PPN sites that
# matter for the cluster model even though they are not on the ministry list.
# ---------------------------------------------------------------------------
SITES: List[Site] = [
    Site(
        name="Göbeklitepe", aliases=("Göbekli Tepe", "Girê Mirazan"),
        lat=37.22361, lon=38.92167, confidence=Confidence.PUBLISHED,
        period="PPNA -> Early/Middle PPNB", start_bc=9500, end_bc=8000,
        elevation_m=760.0, area_ha=9.0, official=True,
        setting="Hilltop on a limestone ridge of the Germuş range; no water on the hill",
        sources=("KE", "Wikidata Q214944", "OSM"),
        note="Nearest seasonal stream (Mucid Dere) ~3 km west; no springs known. "
             "Rainwater cisterns total ~153 m3 (Herrmann & Schmidt 2012).",
    ),
    Site(
        name="Karahantepe", aliases=("Karahan Tepe", "Keçilitepe"),
        lat=37.09250, lon=39.30361, confidence=Confidence.PUBLISHED,
        period="PPNA-PPNB", start_bc=9400, end_bc=8000,
        elevation_m=700.0, area_ha=10.0, official=True,
        setting="Rocky hill on the north edge of the Tektek Mountains, east of the Harran plain",
        sources=("KE 165235", "Karul21", "OSM"),
        note="Plus ~5 ha of T-pillar quarries. Rock-cut water system 500 m north: "
             "cisterns (mouths 1.5-2 m, depth 5-6 m) and 133 settling pools.",
    ),
    Site(
        name="Sefertepe", aliases=("Sefer Tepe",),
        lat=37.18643, lon=39.48982, confidence=Confidence.CONFLICTING,
        alt_coord=(37.17230, 39.48950),
        # Clare24 Fig. 28 plots Sefer Tepe 0.6 km from this second value and
        # 2.1 km from the first, read off the figure with ~0.5 km accuracy.
        prefer="alt",
        period="Early/Middle PPNB", start_bc=8300, end_bc=8000,
        elevation_m=700.0, area_ha=0.1, official=True,
        setting="Low shallow mound; Viranşehir plain N and E, Tektek Mountains S and W",
        sources=("KE 37217", "Celik06", "Wikidata Q118133735"),
        note="Two published values 1.6 km apart, both present in OSM as separate "
             "nodes. Çelik06 itself prints no coordinate. The rival value comes "
             "with a different elevation (600 m) and area (~0.7 ha), so the two "
             "may descend from different Çelik publications. Needs adjudication.",
    ),
    Site(
        name="Sayburç",
        lat=37.11124, lon=38.62070, confidence=Confidence.PUBLISHED,
        period="Early PPNB", start_bc=8600, end_bc=8300,
        official=True,
        setting="Low mound on the Şanlıurfa plateau, almost entirely under the modern village",
        sources=("Ozdogan24", "Wikidata", "OSM"),
        note="11 consistent 14C dates from structure floors; occupation ~300 years. "
             "KE 165222 gives a point ~600 m SE; the site has two excavation areas, "
             "so 'the' coordinate is somewhat arbitrary.",
    ),
    Site(
        name="Harbetsuvan Tepesi",
        lat=37.04868, lon=39.25243, confidence=Confidence.PUBLISHED,
        period="Early PPNB", start_bc=9100, end_bc=8400,
        elevation_m=714.0, area_ha=0.6, official=True,
        setting="Summit of a rocky mesa on the west edge of the Tektek Mountains",
        sources=("Celik16",),
        note="Coordinate printed to the arcsecond in Celik16. No natural water: "
             "rainwater cisterns. Harran plain 5 km west.",
    ),
    Site(
        name="Gürcütepe", aliases=("Gürcütepe I-VIII",),
        lat=37.14028, lon=38.82460, confidence=Confidence.APPROXIMATE,
        period="Late/Final PPNB -> PPNC -> earliest Pottery Neolithic",
        start_bc=7500, end_bc=7000, official=True,
        setting="Eight low mounds/flat sites on the NW edge of the Harran plain, "
                "at springs on the Sırrın stream; now largely built over",
        sources=("KE 165212", "BeileBohn98"),
        note="DO NOT use the widely copied 37.11987, 38.84593 -- that is Kazane "
             "Höyük's OSM position (a Bronze Age site), mis-assigned upstream. "
             "The KE value used here is unverified and 3.2 km from Kazane. "
             "Complex spans ~1200 x 800 m.",
    ),
    Site(
        name="Çakmaktepe", aliases=("Çakmak Tepe",),
        lat=37.08634, lon=38.63018, confidence=Confidence.APPROXIMATE,
        period="PPNA", start_bc=9600, end_bc=8800,
        elevation_m=670.0, area_ha=1.8, official=True,
        setting="Hilltop on the Eocene limestone plateau of the Fatik Mountains, "
                "20 km SW of Şanlıurfa",
        sources=("KE 165224", "Wikidata Q119166486"),
        note="No radiocarbon dates yet; period from El-Khiam/Jerf el-Ahmar/"
             "Salibiya/Helwan point typology. ~150 m core diameter plus outliers.",
    ),
    Site(
        name="Şanlıurfa Yeni Mahalle", aliases=("Balıklıgöl Höyüğü", "Urfa-Yeni Mahalle"),
        lat=37.14869, lon=38.78528, confidence=Confidence.APPROXIMATE,
        period="Late PPNA -> Middle PPNB", start_bc=9500, end_bc=7580,
        official=True,
        setting="Valley bottom in the old city, immediately north of the Balıklıgöl "
                "springs; entirely buried under modern housing",
        sources=("DEFC 206", "Celik05 PhD"),
        note="DEFC records 'exact location: no' (source GeoNames). Known only from "
             "a ~15 m rescue section, so the extent is unknown.",
    ),
    Site(
        name="Yoğunburç",
        lat=37.14479, lon=38.61902, confidence=Confidence.APPROXIMATE,
        period="Neolithic (undated)", area_ha=2.2, official=True,
        setting="Karaköprü district; on a N-S line with Sayburç, Çakmaktepe and Ayanlar",
        sources=("KE 165220", "Wikidata Q132182829"),
        note="KE itself prints 'konum tahmini belirlenmiştir' (location estimated). "
             "First excavated July 2026; no radiocarbon yet. A reliable coordinate "
             "should appear in the season report.",
    ),
    Site(
        name="Ayanlar Höyük", aliases=("Gre Hut",),
        lat=37.18531, lon=38.56073, confidence=Confidence.APPROXIMATE,
        period="Early/Middle PPNB", start_bc=8800, end_bc=8000,
        elevation_m=733.0, area_ha=14.0, official=True,
        setting="Broad shallow mound (250 x 300 m) with six hillocks on bedrock, "
                "partly under Ayanlar Mahallesi; basalt plateau of Mt Kasmer 2 km east",
        sources=("Celik17", "KE 165218"),
        note="NOT Gre Fılla -- that is a separate PPN site near Kocaköy, Diyarbakır. "
             "17 ha including the bedrock pool groups. No local flint.",
    ),
    Site(
        name="Mendiktepe", aliases=("Mendik Tepe",),
        lat=None, lon=None, confidence=Confidence.UNKNOWN,
        # Read off Clare24 Fig. 28 (map georeferenced on five published sites,
        # ~0.5 km accuracy). It is 4.9 km from Çakmaktepe and 13 km SW of
        # Şanlıurfa, as the descriptions say, but 6.8 km from the box the
        # "1.3 km NE of Mendik village" clue gave; the two clues disagree.
        search_coord=(37.0743, 38.6835),
        period="PPNA, possibly terminal Epipalaeolithic", start_bc=10000, end_bc=9000,
        area_ha=4.0, official=True,
        setting="Upper part of a ~200 m ridge between a higher southern and a lower "
                "northern eminence; Payamlı Mahallesi, Eyyübiye",
        sources=("Baird25",),
        note="No coordinate published anywhere found. Constraints: 15 km SW of "
             "Şanlıurfa, 1.3 km NE of Mendik village, ~5 km from Çakmaktepe -- "
             "which pins it only to roughly 37.02-37.06 N, 38.59-38.65 E. "
             "Area >=4 ha is very extensive for a PPNA site.",
    ),
    Site(
        name="Söğüt Tarlası", aliases=("Sögüt Tarlasi", "Küçük Gölbaşı", "U 51/1-2"),
        lat=None, lon=None, confidence=Confidence.UNKNOWN,
        # Biris village plus a nominal step north ("just north of Biris
        # Mezarlığı"). The step only keeps the two sites in separate cells.
        search_coord=(37.3120, 38.5500),
        period="Epipalaeolithic + PPNB", elevation_m=580.0, official=True,
        setting="Low flat rise ~2 km SW of Bozova, just north of Biris Mezarlığı, "
                "which sits on a rocky slope by a spring on the west edge of a "
                "modern irrigation reservoir",
        sources=("TAY", "Di Nocera (tastepeler.org)"),
        note="No coordinate in TAY, tastepeler.org or KE. Bozova is at "
             "37.3620, 38.5254 and Biris village at 37.3095, 38.5500. "
             "Biris mound 120 x 25 m; Söğüt Tarlası extent unpublished.",
    ),
    Site(
        name="Biris Mezarlığı", aliases=("Biris Mezarligi", "Biris"),
        lat=None, lon=None, confidence=Confidence.UNKNOWN,
        search_coord=(37.3095, 38.5500),      # Biris village, not the site
        period="Epipalaeolithic + PPN", official=False,
        setting="Rocky slope by a spring on the west edge of a modern irrigation "
                "reservoir, ~2 km SW of Bozova; mound 120 x 25 m",
        sources=("TAY", "Di Nocera (tastepeler.org)"),
        note="Recorded together with Söğüt Tarlası, which lies just north of it. "
             "No coordinate published anywhere found; Biris village is at "
             "37.3095, 38.5500. Listed separately because the two are distinct "
             "find-spots.",
    ),
    Site(
        name="Kocanizam", aliases=("Kocanizam Tepesi",),
        lat=None, lon=None, confidence=Confidence.UNKNOWN,
        search_coord=(37.2013, 39.4844),      # read off Clare24 Fig. 28, ~0.5 km
        period="possible Early PPNB", official=False,
        sources=("Clare24",),
        note="Known here only from the map in Clare24 Fig. 28, where it is "
             "plotted as a possible EPPNB site ~3.7 km north of Sefer Tepe. "
             "No coordinate or description found.",
    ),
    # --- related PPN sites, not on the official twelve ---------------------
    Site(
        name="Nevalı Çori", aliases=("Nevali Cori", "Newala Çorî"),
        lat=37.51833, lon=38.60556, confidence=Confidence.PUBLISHED,
        period="PPNB (strata I-V)", start_bc=8400, end_bc=8100,
        elevation_m=490.0,
        setting="Both banks of the Kantara Çay, 3 km south of the Euphrates, "
                "in Anti-Taurus foothills",
        sources=("Hauptmann07",),
        note="SUBMERGED beneath the Atatürk Dam reservoir since 1992. A modern DEM "
             "returns the water surface here, not terrain -- use pre-1992 sources "
             "(CORONA stereo) for anything in the Euphrates corridor.",
    ),
    Site(
        name="Hamzan Tepe",
        lat=37.08278, lon=38.80150, confidence=Confidence.APPROXIMATE,
        period="Lower Palaeolithic station, then early PPNB",
        elevation_m=600.0, area_ha=0.5,
        setting="On bedrock in the Fatik Mountains, 10 km S of Şanlıurfa; no water "
                "source; Harran plain 1 km east",
        sources=("Celik10", "KE 165232"),
        note="Celik10 prints a garbled grid reference that cannot be converted; the "
             "value here is from gazetteers, mutually consistent to ~40 m. "
             "T-shaped pillar and two round buildings.",
    ),
    Site(
        name="Taşlı Tepe", aliases=("Taşlıtepe",),
        lat=37.36890, lon=39.28046, confidence=Confidence.APPROXIMATE,
        period="Late PPNA / early PPNB", elevation_m=740.0, area_ha=1.2,
        setting="Cultivated land on the flank of Karacadağ, Siverek district",
        sources=("CelikGuler11", "KE 37218"),
        note="Consistent with Çelik's '1 km north of Başbük village' (OSM puts "
             "Başbük 1.55 km south of this point).",
    ),
    Site(
        name="Kurt Tepesi", aliases=("Kurttepesi", "Kuça Gur"),
        lat=37.23470, lon=39.24150, confidence=Confidence.APPROXIMATE,
        period="Pre-Pottery Neolithic (undated)", elevation_m=730.0, area_ha=1.0,
        setting="Small mound on a calcareous plateau ridge, commanding the Çoban "
                "Deresi pass between the Harran plain and the Viranşehir region",
        sources=("Celik15",),
        note="Well corroborated by two independent distance constraints (3 km S of "
             "Sumaklı, 6 km NW of Kösecik), both of which fit. Dated only by a "
             "T-pillar negative in a looters' pit plus PPN flint.",
    ),
]

#: Period attributions plotted in Clare24, Figs 26-28 (Epipalaeolithic
#: 10900-9600, PPNA 9600-8700, EPPNB 8700-8200 cal BC). ``True`` is a site the
#: map draws solid, ``False`` one it draws as "possible".
CLARE24_PERIODS: Dict[str, Tuple[Tuple[str, int, int, bool], ...]] = {
    "Söğüt Tarlası": (("Epipalaeolithic", 10900, 9600, False),),
    "Çakmaktepe": (("Epipalaeolithic", 10900, 9600, False), ("PPNA", 9600, 8700, True)),
    "Göbeklitepe": (("PPNA", 9600, 8700, True), ("EPPNB", 8700, 8200, True)),
    "Karahantepe": (("PPNA", 9600, 8700, True), ("EPPNB", 8700, 8200, True)),
    "Nevalı Çori": (("EPPNB", 8700, 8200, True),),
    "Şanlıurfa Yeni Mahalle": (("EPPNB", 8700, 8200, True),),
    "Sayburç": (("EPPNB", 8700, 8200, True),),
    "Harbetsuvan Tepesi": (("EPPNB", 8700, 8200, True),),
    "Sefertepe": (("EPPNB", 8700, 8200, True),),
    "Taşlı Tepe": (("EPPNB", 8700, 8200, False),),
    "Kurt Tepesi": (("EPPNB", 8700, 8200, False),),
    "Kocanizam": (("EPPNB", 8700, 8200, False),),
    "Ayanlar Höyük": (("EPPNB", 8700, 8200, False),),
    "Yoğunburç": (("EPPNB", 8700, 8200, False),),
    "Hamzan Tepe": (("EPPNB", 8700, 8200, False),),
    "Mendiktepe": (("EPPNB", 8700, 8200, False),),
}

# The Ministry of Culture's official Taş Tepeler twelve.
TAS_TEPELER_12: Tuple[str, ...] = tuple(s.name for s in SITES if s.official)

for _site in SITES:
    note = _site.note.lower()
    if _site.start_bc is None or _site.end_bc is None:
        # No date of its own: take the span Clare24 plots it in, and say that
        # it is an attribution on a map, not a dated occupation.
        spans = CLARE24_PERIODS.get(_site.name)
        if spans:
            _site.start_bc = max(s[1] for s in spans)
            _site.end_bc = min(s[2] for s in spans)
            _site.date_quality = "possible"
            _site.sources = tuple(_site.sources) + ("Clare24 Figs 26-28",)
        else:
            _site.date_quality = "none"
    elif "14c" in note or "radiocarbon" in note:
        _site.date_quality = "radiocarbon"
    else:
        # A published range whose laboratory basis is not in this note.
        # Treat it as typological until the researcher upgrades the entry.
        _site.date_quality = "typological"


def _index() -> Dict[str, Site]:
    idx: Dict[str, Site] = {}
    for s in SITES:
        idx[s.name.casefold()] = s
        for a in s.aliases:
            idx[a.casefold()] = s
    return idx


_BY_NAME = _index()


def find(name: str) -> Site:
    """Look a site up by name or any published alias (case-insensitive)."""
    try:
        return _BY_NAME[name.casefold()]
    except KeyError:
        raise KeyError(f"unknown site {name!r}; known: {sorted(set(s.name for s in SITES))}")


def located(usable_only: bool = False) -> List[Site]:
    """Sites with a coordinate. ``usable_only`` also drops the conflicting ones."""
    return [s for s in SITES if (s.usable if usable_only else s.located)]


def position(site: Site, include_uncertain: bool = True
             ) -> Optional[Tuple[float, float, str]]:
    """Where to put a site in a run: ``(lat, lon, quality)`` or ``None``.

    ``quality`` is ``published`` / ``approximate`` for a usable coordinate.
    With ``include_uncertain`` a conflicting site is placed on its first
    published value (``conflicting``) and an unlocated one on its
    ``search_coord`` (``search area``), so every site can take part. Those two
    kinds are working positions, and clients must show them as such.
    """
    if site.usable:
        return site.lat, site.lon, site.confidence.value
    if not include_uncertain:
        return None
    if site.located:
        if site.prefer == "alt" and site.alt_coord is not None:
            return site.alt_coord[0], site.alt_coord[1], Confidence.CONFLICTING.value
        return site.lat, site.lon, Confidence.CONFLICTING.value
    if site.search_coord is not None:
        return site.search_coord[0], site.search_coord[1], "search area"
    return None


def placed(include_uncertain: bool = True) -> List[Tuple[Site, float, float, str]]:
    """Every site that :func:`position` can place, with that position."""
    out = []
    for s in SITES:
        p = position(s, include_uncertain)
        if p is not None:
            out.append((s, p[0], p[1], p[2]))
    return out


def bounds(usable_only: bool = False) -> Tuple[float, float, float, float]:
    """Lat/lon bounding box of the located sites: ``(min_lat, min_lon, max_lat, max_lon)``."""
    pts = [(s.lat, s.lon) for s in located(usable_only)]
    if not pts:
        raise ValueError("no located sites")
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return (min(lats), min(lons), max(lats), max(lons))


def occupied_at(year_bc: int) -> List[Site]:
    """Sites whose published range covers ``year_bc`` (calibrated BC)."""
    out = []
    for s in SITES:
        if s.start_bc is None or s.end_bc is None:
            continue
        if s.end_bc <= year_bc <= s.start_bc:
            out.append(s)
    return out


def data_gaps() -> List[Site]:
    """Sites that need a decision or more research before routing on them."""
    return [s for s in SITES
            if s.confidence in (Confidence.UNKNOWN, Confidence.CONFLICTING)]

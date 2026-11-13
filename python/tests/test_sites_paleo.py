"""Integrity tests for the site catalogue and the palaeo-terrain correction.

These mostly guard against silent data rot: a coordinate getting "fixed" to a
wrong published value, a confidence flag being dropped, or the palaeo
correction quietly returning zero where it has no basis at all.

Run with pytest or directly (``python python/tests/test_sites_paleo.py``).
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pedsim import paleo, sites
from pedsim.sites import Confidence

# The whole cluster sits inside this box; anything outside is a typo.
REGION = (36.9, 38.4, 37.7, 39.6)   # min_lat, min_lon, max_lat, max_lon


# ------------------------------------------------------------------ catalogue
def test_official_twelve():
    assert len(sites.TAS_TEPELER_12) == 12
    assert "Göbeklitepe" in sites.TAS_TEPELER_12
    assert "Yoğunburç" in sites.TAS_TEPELER_12
    # these two are related PPN sites, deliberately NOT on the ministry list
    assert "Taşlı Tepe" not in sites.TAS_TEPELER_12
    assert "Kurt Tepesi" not in sites.TAS_TEPELER_12


def test_every_coordinate_is_in_the_region():
    for s in sites.located():
        assert REGION[0] < s.lat < REGION[2], s
        assert REGION[1] < s.lon < REGION[3], s
        if s.alt_coord:
            assert REGION[0] < s.alt_coord[0] < REGION[2], s
            assert REGION[1] < s.alt_coord[1] < REGION[3], s


def test_unlocated_sites_have_no_coordinate():
    for s in sites.SITES:
        if s.confidence is Confidence.UNKNOWN:
            assert s.lat is None and s.lon is None, f"{s.name} should be unlocated"
            assert not s.usable
        else:
            assert s.located, f"{s.name} claims {s.confidence} but has no coordinate"


def test_known_data_gaps_are_flagged():
    names = {s.name for s in sites.data_gaps()}
    assert names == {"Sefertepe", "Mendiktepe", "Söğüt Tarlası", "Biris Mezarlığı"}


def test_every_site_can_be_placed_and_says_how_sure_it_is():
    rows = sites.placed()
    assert len(rows) == len(sites.SITES) == 17
    quality = {s.name: q for s, _lat, _lon, q in rows}
    assert quality["Göbeklitepe"] == "published"
    assert quality["Sefertepe"] == "conflicting"
    assert quality["Mendiktepe"] == quality["Biris Mezarlığı"] == "search area"
    # a search area is a placeholder: the site itself stays unlocated
    assert sites.find("Mendiktepe").lat is None
    assert sites.position(sites.find("Mendiktepe"), include_uncertain=False) is None
    assert {s.name for s, *_ in sites.placed(include_uncertain=False)} == {
        s.name for s in sites.located(usable_only=True)}


def test_sefertepe_keeps_both_rival_coordinates():
    s = sites.find("Sefertepe")
    assert s.confidence is Confidence.CONFLICTING
    assert s.alt_coord is not None
    # the two published values are ~1.6 km apart; make sure we didn't collapse them
    dlat = abs(s.lat - s.alt_coord[0])
    assert dlat > 0.01, "the rival Sefertepe coordinates must stay distinct"


def test_gurcutepe_is_not_the_kazane_coordinate():
    """Regression guard: the value circulating on Wikidata/Vici/tour sites for
    Gürcütepe is byte-for-byte Kazane Höyük's, a different Bronze Age site."""
    s = sites.find("Gürcütepe")
    assert abs(s.lat - 37.11987) > 0.001 or abs(s.lon - 38.84593) > 0.001


def test_ayanlar_alias_is_gre_hut_not_gre_filla():
    s = sites.find("Gre Hut")
    assert s.name == "Ayanlar Höyük"
    # Gre Fılla is a separate site near Kocaköy, Diyarbakır
    try:
        sites.find("Gre Fılla")
    except KeyError:
        return
    raise AssertionError("Gre Fılla must not be an alias of Ayanlar Höyük")


def test_lookup_by_alias_is_case_insensitive():
    assert sites.find("göbekli tepe").name == "Göbeklitepe"
    assert sites.find("KARAHAN TEPE").name == "Karahantepe"


def test_date_ranges_are_ordered():
    for s in sites.SITES:
        if s.start_bc is not None and s.end_bc is not None:
            assert s.start_bc > s.end_bc, f"{s.name}: start_bc must be the earlier date"


def test_occupied_at_picks_a_plausible_ppna_set():
    at9000 = {s.name for s in sites.occupied_at(9000)}
    assert "Göbeklitepe" in at9000 and "Karahantepe" in at9000
    # Gürcütepe is late PPNB onwards, ~7500-7000 BC
    assert "Gürcütepe" not in at9000
    assert "Gürcütepe" in {s.name for s in sites.occupied_at(7200)}


def test_bounds_exclude_conflicting_sites_when_asked():
    all_b = sites.bounds()
    usable_b = sites.bounds(usable_only=True)
    # Sefertepe (conflicting) is the easternmost site
    assert all_b[3] > usable_b[3]


# ---------------------------------------------------------------- palaeo data
def test_fourteen_cores_with_sane_values():
    assert len(paleo.CULAP_CORES) == 14
    assert len({c.id for c in paleo.CULAP_CORES}) == 14
    for c in paleo.CULAP_CORES:
        assert c.compartment in ("slope toe", "piedmont", "floodplain")
        # the 10 ka surface cannot be deeper than the whole sequence
        assert 0.0 <= c.aggradation_m <= c.thickness_cm / 100.0 + 1e-9, c.id
        assert c.basis, f"{c.id} must record where its number comes from"


def test_slope_toes_are_effectively_bedrock():
    for c in paleo.CULAP_CORES:
        if c.compartment == "slope toe":
            # the whole thin sequence is Late Holocene, so subtract all of it
            assert abs(c.aggradation_m - c.thickness_cm / 100.0) < 1e-9


def test_aggradation_at_a_core_returns_that_core():
    c = next(x for x in paleo.CULAP_CORES if x.id == "GT20")
    got, unc = paleo.aggradation_at(c.easting, c.northing)
    assert abs(got - c.aggradation_m) < 1e-9
    assert abs(unc - c.uncertainty_m) < 1e-9


def test_no_basis_means_infinite_uncertainty_not_a_quiet_zero():
    """The Harran plain has no Holocene data at all -- the module must say so
    rather than imply a zero correction is a measurement."""
    corr, unc = paleo.aggradation_at(530000, 4080000)
    assert corr == 0.0
    assert not np.isfinite(unc)


def test_floodplain_correction_clears_the_dem_noise_floor():
    c = next(x for x in paleo.CULAP_CORES if x.id == "GT20")
    assert paleo.meaningful(c.aggradation_m)
    toe = next(x for x in paleo.CULAP_CORES if x.id == "GT03")
    assert not paleo.meaningful(toe.aggradation_m)


def test_grid_matches_the_scalar_version():
    e = np.array([[503214.0, 493656.0]])
    n = np.array([[4118629.0, 4118322.0]])
    corr, _ = paleo.aggradation_grid(e, n)
    for i in range(2):
        want, _ = paleo.aggradation_at(e[0, i], n[0, i])
        # the scalar version snaps to a core within 1 m, the grid version clamps
        # the distance instead, so they differ by microns at a core location
        assert abs(corr[0, i] - want) < 1e-3


def test_compartment_fallback_fills_out_of_range_cells():
    e = np.array([[530000.0]])
    n = np.array([[4080000.0]])
    comp = np.array([["floodplain"]])
    bare, bare_u = paleo.aggradation_grid(e, n)
    filled, filled_u = paleo.aggradation_grid(e, n, compartments=comp)
    assert bare[0, 0] == 0.0 and not np.isfinite(bare_u[0, 0])
    assert filled[0, 0] == paleo.COMPARTMENT_AGGRADATION["floodplain"][1]
    assert np.isfinite(filled_u[0, 0])


def test_correct_dem_lowers_valleys_and_leaves_unknown_ground_alone():
    e = np.array([[503214.0, 530000.0]])
    n = np.array([[4118629.0, 4080000.0]])
    dem = np.array([[600.0, 600.0]])
    out, unc = paleo.correct_dem(dem, e, n)
    assert out[0, 0] < 595.0            # floodplain: ~5.3 m of aggradation removed
    assert out[0, 1] == 600.0           # no basis: unchanged
    assert not np.isfinite(unc[0, 1])


def test_plateaus_get_no_correction():
    assert paleo.COMPARTMENT_AGGRADATION["plateau"][1] == 0.0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()

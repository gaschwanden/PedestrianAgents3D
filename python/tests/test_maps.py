"""Catalogue of published site plans — finding aid, not the drawings themselves."""
from __future__ import annotations

from pedsim import maps, sites
from pedsim.maps import Access, Importability, PlanKind


def test_every_catalogue_site_has_an_entry():
    """A missing site is a research gap we forgot to record, not a quiet None."""
    covered = {p.site for p in maps.SOURCES if p.site}
    for s in sites.SITES:
        assert s.name in covered, f"{s.name} has no plan-status entry"


def test_gobekli_has_an_open_architectural_plan():
    plans = maps.for_site("Göbekli Tepe")
    arch = [p for p in plans if p.kind is PlanKind.ARCHITECTURE]
    assert arch
    best = arch[0]
    assert best.access is Access.OPEN
    assert best.importability is Importability.YES
    assert "L9-" in best.grid and best.scale_bar and best.north_arrow
    assert best.url.startswith("https://journals.uni-lj.si/")


def test_nevali_cori_plan_is_the_complete_village():
    plans = maps.importable("Nevalı Çori")
    assert plans
    assert any("Hauptmann" in p.citation for p in plans)


def test_harbetsuvan_best_source_is_the_geophysics_raster():
    best = maps.importable("Harbetsuvan Tepesi")
    assert best and best[0].kind is PlanKind.GEOPHYSICS
    assert "zenodo" in best[0].url


def test_sayburc_and_karahan_are_honest_about_photos_not_plans():
    assert not maps.has_village_plan("Sayburç")
    karahan = maps.for_site("Karahantepe")
    assert karahan[0].importability is Importability.NO
    assert "photograph" in karahan[0].note.lower()


def test_sites_without_drawings_say_so():
    for name in ("Yoğunburç", "Mendiktepe", "Söğüt Tarlası", "Mendik Tepe"):
        assert maps.has_village_plan(name) is False


def test_summary_covers_the_official_twelve():
    lines = maps.summary()
    assert "Göbeklitepe" in lines
    assert lines["Göbeklitepe"].startswith("yes")
    assert lines["Yoğunburç"].startswith("no:")

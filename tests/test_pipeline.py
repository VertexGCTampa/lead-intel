"""Offline tests: scoring rules, address merging, dashboard build. Run: python -m pytest tests"""
from pathlib import Path

import yaml

from leadintel import dashboard, store
from leadintel.score import score_item

ROOT = Path(__file__).resolve().parent.parent
PROFILE = yaml.safe_load((ROOT / "config" / "fit_profile.yaml").read_text())


def lead(**kw):
    base = dict(source_id="test", source_name="Test source", county="Pinellas", category="bids",
                sector="commercial", project_type="other", stage="bid_open", title="Test")
    base.update(kw)
    return base


def tier(**kw):
    return score_item(lead(**kw), PROFILE)


# ---- commercial ----
def test_city_hall_conversion_in_range_is_pursue():
    r = tier(title="Park Station City Hall Conversion", project_type="municipal_building",
             is_public_bid=True, est_value=1_800_000)
    assert r["tier"] == "pursue", r


def test_civil_is_excluded():
    assert tier(project_type="site_civil", est_value=2_000_000)["tier"] == "excluded"


def test_single_trade_roof_is_excluded():
    assert tier(project_type="municipal_building", single_trade=True, est_value=600_000)["tier"] == "excluded"


def test_public_bid_over_bond_limit_excluded():
    r = tier(project_type="municipal_building", is_public_bid=True, est_value=5_000_000)
    assert r["tier"] == "excluded" and "bonded" in r["excluded_because"][0]


def test_private_job_up_to_8m_kept():
    assert tier(project_type="medical", stage="planning", est_value=7_500_000)["tier"] == "pursue"


def test_under_400k_excluded():
    assert tier(project_type="tenant_improvement", est_value=250_000)["tier"] == "excluded"


def test_estimate_just_under_min_is_kept_and_flagged():
    r = tier(project_type="medical", est_value=370_000, value_is_estimate=True)
    assert r["tier"] == "watch" and "estimate near a limit" in r["flags"]


def test_unknown_value_goes_to_watch():
    assert tier(project_type="retail", stage="planning")["tier"] == "watch"


def test_big_warehouse_excluded():
    assert tier(project_type="small_industrial", sqft=150_000, est_value=6_000_000)["tier"] == "excluded"


def test_outside_counties_excluded():
    assert tier(county="Pasco", project_type="medical", est_value=1_000_000)["tier"] == "excluded"


# ---- residential ----
def test_custom_home_over_2500_in_south_tampa_pursue():
    r = tier(sector="residential", category="planning", county="Hillsborough", project_type="custom_home",
             stage="permit", sqft=4200, zip="33629", new_construction=True)
    assert r["tier"] == "pursue", r


def test_custom_home_under_2500_excluded():
    assert tier(sector="residential", project_type="custom_home", stage="permit", sqft=2100)["tier"] == "excluded"


def test_teardown_without_size_is_watch():
    r = tier(sector="residential", project_type="custom_home", stage="demolition", zip="33609")
    assert r["tier"] == "watch" and "size unknown" in r["flags"]


def test_townhomes_20_units_excluded_19_kept():
    assert tier(sector="residential", project_type="townhome", stage="planning", units=20)["tier"] == "excluded"
    assert tier(sector="residential", project_type="townhome", stage="planning", units=19)["tier"] == "pursue"


def test_duplex_any_size_kept():
    assert tier(sector="residential", project_type="duplex", stage="planning")["tier"] in ("pursue", "watch")


def test_renovation_and_condo_excluded():
    assert tier(sector="residential", project_type="renovation", stage="variance")["tier"] == "excluded"
    assert tier(sector="residential", project_type="condo", stage="planning")["tier"] == "excluded"


# ---- merging and dashboard ----
def test_same_address_merges_and_keeps_history():
    leads = {}
    demo = lead(sector="residential", project_type="custom_home", stage="demolition",
                address="4900 W. Example Avenue South", source_id="permits", source_name="Permits")
    var = lead(sector="residential", project_type="custom_home", stage="variance", reference="VRB-26-01",
               address="4900 W Example Ave S", sqft=3800, source_id="tampa_cares", source_name="Tampa CARES")
    new1 = store.merge(leads, [demo], "2026-11-16")
    new2 = store.merge(leads, [var], "2026-11-23")
    assert len(leads) == 1 and new1 and not new2
    only = next(iter(leads.values()))
    assert only["sqft"] == 3800 and len(only["history"]) == 2 and only["first_seen"] == "2026-11-16"


def test_dashboard_builds(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "OUT", tmp_path / "index.html")
    leads = {}
    store.merge(leads, [lead(project_type="medical", est_value=900_000, title="Clinic </script> TI")], "2026-11-23")
    for l in leads.values():
        score_item(l, PROFILE)
    out = dashboard.build(leads, "2026-11-23")
    html = out.read_text()
    assert "Clinic <\\/script> TI" in html and "__LEADS__" not in html and "November 23, 2026" in html

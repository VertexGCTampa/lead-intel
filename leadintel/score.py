"""Apply the fit profile: exclusions, size and value limits, points, tier."""
from __future__ import annotations


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _relationship_hit(item: dict, names: list[str]) -> str | None:
    hay = " ".join(str(item.get(k) or "") for k in ("owner", "applicant", "design_team")).lower()
    for name in names:
        if name and name.lower() in hay:
            return name
    return None


def score_item(item: dict, profile: dict) -> dict:
    """Return the item with score, tier, reasons and flags added."""
    reasons: list[str] = []
    flags: list[str] = []
    excluded: list[str] = []
    points = 0

    ptype = item.get("project_type") or "other"
    sector = item.get("sector") or "other"
    stage = item.get("stage") or "other"
    value = _num(item.get("est_value"))
    sqft = _num(item.get("sqft"))
    units = _num(item.get("units"))

    if item.get("county") not in profile["counties"]:
        excluded.append("outside Hillsborough and Pinellas")

    if sector == "commercial":
        c = profile["commercial"]
        if ptype in c["excluded_types"]:
            excluded.append(f"excluded type: {ptype.replace('_', ' ')}")
        if c.get("exclude_single_trade") and item.get("single_trade"):
            excluded.append("single-trade work")
        if ptype in ("small_industrial", "large_warehouse") and sqft and sqft > c["large_warehouse_sqft"]:
            excluded.append(f"warehouse over {int(c['large_warehouse_sqft']):,} sq ft")

        cap = c["max_value_public"] if item.get("is_public_bid") else c["max_value_private"]
        margin = c["near_line_margin"]
        if value is not None:
            estimated = bool(item.get("value_is_estimate"))
            low_line = c["min_value"] * (1 - margin) if estimated else c["min_value"]
            high_line = cap * (1 + margin) if estimated else cap
            if value < low_line:
                excluded.append(f"under ${c['min_value']:,.0f}")
            elif value > high_line:
                label = "bonded limit" if item.get("is_public_bid") else "limit"
                excluded.append(f"over ${cap:,.0f} {label}")
            else:
                if estimated and (value < c["min_value"] or value > cap):
                    flags.append("estimate near a limit")
                points += profile["value_estimated_points"] if estimated else profile["value_known_points"]
                reasons.append(f"{'est. ' if estimated else ''}${value:,.0f}")
        else:
            flags.append("value unknown")

        tp = c["type_points"].get(ptype, 0)
        if tp:
            points += tp
            reasons.append(ptype.replace("_", " "))

    elif sector == "residential":
        r = profile["residential"]
        if ptype in r["excluded_types"]:
            excluded.append(f"excluded type: {ptype.replace('_', ' ')}")
        if item.get("new_construction") is False:
            excluded.append("not new construction")

        if ptype == "custom_home":
            if sqft is not None and sqft < r["custom_home_min_sqft"]:
                excluded.append(f"under {r['custom_home_min_sqft']:,} sq ft")
            elif sqft is not None:
                points += profile["value_known_points"]
                reasons.append(f"{sqft:,.0f} sq ft")
            else:
                flags.append("size unknown")
        if ptype == "townhome":
            if units is not None and units > r["townhome_max_units"]:
                excluded.append(f"{units:.0f} units (limit {r['townhome_max_units']})")
            elif units is not None:
                points += profile["value_known_points"]
                reasons.append(f"{units:.0f} units")
            else:
                flags.append("unit count unknown")

        tp = r["type_points"].get(ptype, 0)
        if tp:
            points += tp
            reasons.append(ptype.replace("_", " "))
        if str(item.get("zip") or "") in r["priority_zips"]:
            points += 10
            reasons.append("priority area")
    else:
        excluded.append("not commercial or residential building work")

    sp = profile["stage_points"].get(stage, 0)
    if sp:
        points += sp
        reasons.append(stage.replace("_", " "))

    rel = _relationship_hit(item, profile["relationships"]["names"])
    if rel:
        points += profile["relationships"]["points"]
        reasons.append(f"known: {rel}")

    score = min(points, 100)
    t = profile["tiers"]
    if excluded:
        tier = "excluded"
    elif score >= t["pursue"] and not flags:
        tier = "pursue"
    elif score >= t["watch"] or flags:
        tier = "watch"
    else:
        tier = "low"

    item.update(score=score, tier=tier, reasons=reasons, flags=flags, excluded_because=excluded)
    return item

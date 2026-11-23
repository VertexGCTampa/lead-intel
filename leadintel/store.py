"""Lead log stored as JSON in the repo. De-duplicates and merges by address."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LEADS_FILE = DATA / "leads.json"
SEEN_DOCS_FILE = DATA / "seen_docs.json"

STAGE_ORDER = ["news", "lot_sale", "demolition", "variance", "planning", "lease", "rfq", "bid_open", "permit"]


def _norm_address(addr: str | None) -> str:
    if not addr:
        return ""
    a = addr.lower()
    a = re.sub(r"[.,#]", " ", a)
    for long, short in {"street": "st", "avenue": "ave", "boulevard": "blvd", "drive": "dr",
                        "road": "rd", "south": "s", "north": "n", "west": "w", "east": "e"}.items():
        a = re.sub(rf"\b{long}\b", short, a)
    return re.sub(r"\s+", " ", a).strip()


def lead_key(item: dict) -> str:
    if item.get("reference"):
        basis = f"{item['source_id']}|{item['reference']}".lower()
    elif item.get("address"):
        basis = f"addr|{_norm_address(item['address'])}|{item.get('sector')}"
    else:
        basis = f"{item['source_id']}|{item.get('title', '').lower()}"
    return hashlib.sha1(basis.encode()).hexdigest()[:12]


def load_leads() -> dict:
    if LEADS_FILE.exists():
        return json.loads(LEADS_FILE.read_text())
    return {}


def save_leads(leads: dict) -> None:
    DATA.mkdir(exist_ok=True)
    LEADS_FILE.write_text(json.dumps(leads, indent=1, sort_keys=True))


def load_seen_docs() -> set[str]:
    if SEEN_DOCS_FILE.exists():
        return set(json.loads(SEEN_DOCS_FILE.read_text()))
    return set()


def save_seen_docs(seen: set[str]) -> None:
    DATA.mkdir(exist_ok=True)
    SEEN_DOCS_FILE.write_text(json.dumps(sorted(seen), indent=1))


def _find_same_address(leads: dict, item: dict) -> str | None:
    """Residential leads at one address across sources become one lead (demo -> variance -> permit)."""
    addr = _norm_address(item.get("address"))
    if not addr or item.get("sector") != "residential":
        return None
    for key, lead in leads.items():
        if lead.get("sector") == "residential" and _norm_address(lead.get("address")) == addr:
            return key
    return None


def merge(leads: dict, items: list[dict], today: str | None = None) -> list[str]:
    """Add or update leads. Returns keys that are new this run."""
    today = today or date.today().isoformat()
    new_keys = []
    for item in items:
        key = _find_same_address(leads, item) or lead_key(item)
        if key in leads:
            old = leads[key]
            history = old.get("history", [])
            if item.get("stage") != old.get("stage") or item.get("source_id") != old.get("source_id"):
                history.append({"date": today, "stage": item.get("stage"), "source": item.get("source_name")})
            # keep the most advanced stage and any facts the new record adds
            merged = {**old, **{k: v for k, v in item.items() if v not in (None, "", [])}}
            old_stage, new_stage = old.get("stage"), item.get("stage")
            if old_stage in STAGE_ORDER and new_stage in STAGE_ORDER \
                    and STAGE_ORDER.index(old_stage) > STAGE_ORDER.index(new_stage):
                merged["stage"] = old_stage
            merged.update(first_seen=old["first_seen"], last_seen=today, history=history, key=key)
            leads[key] = merged
        else:
            leads[key] = {**item, "key": key, "first_seen": today, "last_seen": today,
                          "history": [{"date": today, "stage": item.get("stage"),
                                       "source": item.get("source_name")}]}
            new_keys.append(key)
    return new_keys

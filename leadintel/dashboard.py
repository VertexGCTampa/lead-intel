"""Build docs/index.html (served by GitHub Pages) with the lead data embedded."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "dashboard.html"
OUT = ROOT / "docs" / "index.html"

KEEP_FIELDS = [
    "key", "tier", "score", "reasons", "flags", "excluded_because", "sector", "category", "county",
    "title", "description", "project_type", "stage", "reference", "address", "city", "zip",
    "est_value", "value_is_estimate", "sqft", "units", "due_date", "hearing_date", "owner",
    "applicant", "design_team", "url", "source_name", "first_seen", "last_seen", "history",
]


def build(leads: dict, last_run: str) -> Path:
    rows = [{k: lead.get(k) for k in KEEP_FIELDS} for lead in leads.values()]
    data = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text()
    html = html.replace("/*__LEADS__*/[]", data)
    html = html.replace("__LAST_RUN__", last_run)
    html = html.replace("__UPDATED__", datetime.strptime(last_run, "%Y-%m-%d").strftime("%B %-d, %Y"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    return OUT

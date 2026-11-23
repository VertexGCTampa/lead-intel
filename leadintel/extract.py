"""Use Claude to turn raw page or agenda text into structured lead records."""
from __future__ import annotations

import json
import os
import re

import anthropic

MODEL = os.environ.get("LEADINTEL_MODEL", "claude-haiku-5-5")

PROJECT_TYPES = [
    # commercial
    "tenant_improvement", "medical", "office", "retail", "restaurant", "commercial_building",
    "small_industrial", "large_warehouse", "municipal_building", "hotel", "multifamily",
    # residential
    "custom_home", "duplex", "townhome", "condo", "renovation", "addition", "production_subdivision",
    # not building work
    "site_civil", "service_contract", "supply", "other",
]
STAGES = ["bid_open", "rfq", "planning", "variance", "permit", "demolition", "lot_sale",
          "lease", "news", "other"]

SYSTEM = f"""You read public notices, bid listings and planning agendas for a general contractor
in Hillsborough and Pinellas County, Florida. Pull out every individual project or opportunity.

Return ONLY a JSON array, no prose and no code fences. One object per item, with these keys:
  title            short project name
  reference        bid, case or file number, or null
  address          street address, or null
  city             city, or null
  zip              5-digit ZIP if stated, or null
  description      one sentence on what is being built or requested
  project_type     one of {PROJECT_TYPES}
  sector           "commercial", "residential" or "other"
  new_construction true, false, or null if unclear
  single_trade     true if the work is one trade only (roofing, HVAC, flooring, painting, etc.)
  is_public_bid    true if a government agency is soliciting bids or qualifications
  stage            one of {STAGES}
  est_value        dollar value if stated, else your rough estimate, else null
  value_is_estimate true if est_value is your estimate rather than stated
  sqft             building square footage if stated, else null
  units            dwelling unit count if stated, else null
  due_date         bid due date YYYY-MM-DD, or null
  hearing_date     hearing date YYYY-MM-DD, or null
  owner            property owner or soliciting agency, or null
  applicant        applicant or agent, or null
  design_team      architect or engineer named, or null
  url              direct link to the item if one appears in the text, else null

Rules:
- Do not invent facts. Use null when the text does not say.
- Only estimate est_value when the scope is clear enough (for example square footage and use).
- Skip navigation, headers, closed or awarded items, and anything that is not a project.
- If there are no items, return []."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def _parse(text: str) -> list[dict]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("title")]


def extract_items(text: str, source: dict, page_url: str, links: list[dict] | None = None) -> list[dict]:
    """Send one chunk of text to Claude and return the items it finds."""
    link_lines = ""
    if links:
        useful = [f"{l['text'][:80]} -> {l['href']}" for l in links if l.get("text")][:300]
        link_lines = "\n\nLinks on the page:\n" + "\n".join(useful)

    prompt = (
        f"Source: {source['name']} ({source['county']} County, category: {source['category']})\n"
        f"Page: {page_url}\n\n"
        f"Text:\n{text}{link_lines}"
    )
    msg = _client().messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    out = "".join(block.text for block in msg.content if block.type == "text")
    items = _parse(out)
    for item in items:
        item["source_id"] = source["id"]
        item["source_name"] = source["name"]
        item["county"] = source["county"]
        item["category"] = source["category"]
        item["source_url"] = page_url
        item["url"] = item.get("url") or page_url
    return items

"""Weekly run: collect from each source, extract with Claude, score, save, build dashboard, email."""
from __future__ import annotations

import argparse
import os
import traceback
from datetime import date
from pathlib import Path

import requests
import yaml

from . import dashboard, digest, store
from .extract import extract_items
from .fetch import Browser, chunks, find_pdf_links, pdf_text
from .mailbox import fetch_alerts
from .score import score_item

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    profile = yaml.safe_load((ROOT / "config" / "fit_profile.yaml").read_text())
    sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["sources"]
    return profile, sources


def collect_listing(browser: Browser, source: dict) -> list[dict]:
    page = browser.render(source["url"])
    return extract_items(page["text"], source, source["url"], page["links"])


def collect_pdfs(browser: Browser, source: dict, seen: set[str]) -> list[dict]:
    page = browser.render(source["url"])
    if source.get("doc_page_pattern"):
        return _collect_via_doc_pages(browser, source, page, seen)
    pdfs = find_pdf_links(page["links"], source["url"], source["pdf_pattern"])
    new_pdfs = [p for p in pdfs if p not in seen][: source.get("max_new_docs", 1)]
    items = []
    for pdf_url in new_pdfs:
        text = pdf_text(pdf_url)
        for part in chunks(text):
            items.extend(extract_items(part, source, pdf_url))
        seen.add(pdf_url)
    return items


def _collect_via_doc_pages(browser: Browser, source: dict, page: dict, seen: set[str]) -> list[dict]:
    """Index page links to one page per document, which links to the PDF (e.g. tampa.gov /document/...)."""
    doc_pages = find_pdf_links(page["links"], source["url"], source["doc_page_pattern"])
    new_pages = [d for d in doc_pages if d not in seen][: source.get("max_new_docs", 1)]
    items = []
    for doc_url in new_pages:
        sub = browser.render(doc_url, wait_ms=1500)
        for pdf_url in find_pdf_links(sub["links"], doc_url, source["pdf_pattern"])[:1]:
            for part in chunks(pdf_text(pdf_url)):
                items.extend(extract_items(part, source, pdf_url))
        seen.add(doc_url)
    return items


def collect_legistar(source: dict, seen: set[str]) -> list[dict]:
    """Agenda PDFs for one board, from the city's public Legistar data feed."""
    resp = requests.get(
        f"https://webapi.legistar.com/v1/{source['legistar_client']}/events",
        params={
            "$filter": f"EventBodyName eq '{source['legistar_body']}'",
            "$orderby": "EventDate desc",
            "$top": "6",
        },
        headers={"Accept": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    agendas = [e["EventAgendaFile"] for e in resp.json() if e.get("EventAgendaFile")]
    new_pdfs = [a for a in agendas if a not in seen][: source.get("max_new_docs", 1)]
    items = []
    for pdf_url in new_pdfs:
        for part in chunks(pdf_text(pdf_url)):
            items.extend(extract_items(part, source, pdf_url))
        seen.add(pdf_url)
    return items


def collect_email(source: dict, seen: set[str]) -> list[dict]:
    """Bid-alert emails in the scanner's inbox (e.g. OpenGov vendor notices)."""
    items = []
    for alert in fetch_alerts(source["from_filter"], seen):
        text = f"Email subject: {alert['subject']}\n\n{alert['text']}"
        for part in chunks(text):
            items.extend(extract_items(part, source, source["url"]))
        seen.add(alert["id"])
    return items


def run(only: str | None = None) -> None:
    profile, sources = load_config()
    today = date.today().isoformat()
    leads = store.load_leads()
    seen = store.load_seen_docs()
    collected: list[dict] = []
    report: list[str] = []

    active = [s for s in sources if s.get("enabled") and s["url"] != "VERIFY"]
    if only:
        active = [s for s in active if s["id"] == only]

    with Browser() as browser:
        for source in active:
            try:
                if source["kind"] == "listing_page":
                    items = collect_listing(browser, source)
                elif source["kind"] == "pdf_index":
                    items = collect_pdfs(browser, source, seen)
                elif source["kind"] == "legistar":
                    items = collect_legistar(source, seen)
                elif source["kind"] == "email_alerts":
                    items = collect_email(source, seen)
                else:
                    raise ValueError(f"unknown kind {source['kind']}")
                collected.extend(items)
                report.append(f"OK    {source['id']}: {len(items)} items")
            except Exception as exc:  # one broken source never stops the run
                report.append(f"FAIL  {source['id']}: {exc}")
                traceback.print_exc()

    new_keys = store.merge(leads, collected, today)
    for lead in leads.values():
        score_item(lead, profile)

    store.save_leads(leads)
    store.save_seen_docs(seen)
    dashboard.build(leads, today)

    print("\n".join(report))
    tiers = {}
    for k in new_keys:
        tiers[leads[k]["tier"]] = tiers.get(leads[k]["tier"], 0) + 1
    print(f"New leads: {len(new_keys)} {tiers}")

    subject, html = digest.compose(leads, new_keys, os.environ.get("DASHBOARD_URL", ""))
    failed = [r for r in report if r.startswith("FAIL")]
    if failed:
        html += "<p style='color:#A86A12'>Sources that failed this week: " + \
                ", ".join(r.split()[1].rstrip(":") for r in failed) + "</p>"
    if only:
        print("Single-source test run; email not sent.")
    else:
        digest.send(subject, html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vertex lead scanner")
    parser.add_argument("--only", help="run a single source id, for testing")
    run(parser.parse_args().only)

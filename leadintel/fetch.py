"""Fetching: render pages in a headless browser, download PDFs, pull text."""
from __future__ import annotations

import io
import re
from urllib.parse import urljoin

import pdfplumber
import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_TEXT = 60_000  # characters sent to Claude per page


class Browser:
    """One shared headless Chromium for the whole run."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._context = self._browser.new_context(user_agent=USER_AGENT)
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def render(self, url: str, wait_ms: int = 4000) -> dict:
        """Return the visible text and all links of a fully rendered page."""
        page = self._context.new_page()
        try:
            # Portals like OpenGov keep background requests open forever, so
            # "networkidle" can never fire. Load the page, give the network a
            # short chance to settle, then wait for listings to render.
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass  # still-busy pages are fine; we wait below either way
            page.wait_for_timeout(wait_ms)
            text = page.inner_text("body")
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
            )
        finally:
            page.close()
        return {"url": url, "text": text[:MAX_TEXT], "links": links}


def find_pdf_links(links: list[dict], base_url: str, pattern: str) -> list[str]:
    """PDF links matching pattern, in page order, de-duplicated."""
    rx = re.compile(pattern, re.IGNORECASE)
    out: list[str] = []
    for link in links:
        href = urljoin(base_url, link.get("href", ""))
        if rx.search(href) and href not in out:
            out.append(href)
    return out


def pdf_text(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    pages = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def chunks(text: str, size: int = MAX_TEXT) -> list[str]:
    """Split long agenda text on paragraph breaks so no item is cut in half."""
    if len(text) <= size:
        return [text]
    parts, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) > size and current:
            parts.append(current)
            current = ""
        current += para + "\n\n"
    if current:
        parts.append(current)
    return parts

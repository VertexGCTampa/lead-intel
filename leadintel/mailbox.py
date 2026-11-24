"""Read bid-alert emails (e.g. OpenGov vendor notices) from the scanner's Gmail inbox.

Uses the same account and app password as the digest email (SMTP_USER / SMTP_PASSWORD).
Each email is read once: its Message-ID is stored in seen_docs.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from html import unescape

IMAP_HOST = os.environ.get("IMAP_HOST") or "imap.gmail.com"


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</li>|</h\d>", "\n", html)
    # keep link targets so Claude can attach the bid URL
    html = re.sub(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _body(msg: email.message.Message) -> str:
    plain, html = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    return _html_to_text(html) if html else plain


def fetch_alerts(from_filter: str, seen: set[str], days: int = 10) -> list[dict]:
    """Return [{'id', 'subject', 'text'}] for unseen alert emails from the last `days` days."""
    user, password = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
    out: list[dict] = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, "FROM", f'"{from_filter}"', "SINCE", since)
        for num in data[0].split():
            _, parts = imap.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1])
            msg_id = "mail:" + (msg.get("Message-ID") or f"{from_filter}-{num.decode()}").strip()
            if msg_id in seen:
                continue
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            out.append({"id": msg_id, "subject": subject, "text": _body(msg)})
    return out

"""Monday email: top new leads plus a link to the dashboard."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from html import escape

TOP_N = 8


def _line(lead: dict) -> str:
    bits = [lead.get("address") or "", lead.get("city") or ""]
    where = ", ".join(b for b in bits if b)
    when = f"due {lead['due_date']}" if lead.get("due_date") else (
        f"hearing {lead['hearing_date']}" if lead.get("hearing_date") else "")
    size = ""
    if lead.get("est_value"):
        size = f"${lead['est_value']:,.0f}{' est.' if lead.get('value_is_estimate') else ''}"
    elif lead.get("sqft"):
        size = f"{lead['sqft']:,.0f} sq ft"
    extras = ", ".join(x for x in (where, size, when) if x)
    return extras


def compose(leads: dict, new_keys: list[str], dashboard_url: str) -> tuple[str, str]:
    new = [leads[k] for k in new_keys if leads[k]["tier"] in ("pursue", "watch")]
    new.sort(key=lambda l: (l["tier"] != "pursue", -l["score"]))
    pursue = sum(1 for l in new if l["tier"] == "pursue")
    subject = f"Vertex leads: {pursue} to pursue, {len(new) - pursue} to watch"

    items = "".join(
        f'<li style="margin-bottom:10px"><a href="{escape(l.get("url") or dashboard_url)}">'
        f'{escape(l["title"])}</a> ({escape(l["tier"].title())}, {l["score"]})<br>'
        f'<span style="color:#5E6A75">{escape(_line(l))}</span></li>'
        for l in new[:TOP_N]
    ) or "<li>No new leads matched this week.</li>"
    more = f"<p>{len(new) - TOP_N} more on the dashboard.</p>" if len(new) > TOP_N else ""
    html = (
        f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#1D2733">'
        f"<p>New this week:</p><ul style='padding-left:18px'>{items}</ul>{more}"
        f'<p><a href="{escape(dashboard_url)}">Open the dashboard</a></p></div>'
    )
    return subject, html


def send(subject: str, html: str) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("SMTP_HOST not set; skipping email.")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
    msg["To"] = os.environ["DIGEST_TO"]
    msg.set_content("Open this email in an HTML-capable client to see this week's leads.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)

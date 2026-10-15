"""'Bangalore RealEstate Delta' email: what changed today, sent after the daily batch.

* From/subject/options: config/email.yaml. Secrets + owner recipients: .env (git-ignored).
* Recipients: To = EMAIL_TO (owner); Bcc = website subscribers who have not unsubscribed.
* Idempotent: data/app/app.db `email_log`; an edition is sent once, so re-running the batch is safe.
* No SMTP_HOST -> dry run: .eml files in data/app/outbox/<edition>/ (nothing leaves the machine).
* Every message carries a List-Unsubscribe (mailto) header and an unsubscribe line in the footer.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from urllib.parse import quote

from harness.common import DATA, PROCESSED, REPORTS, ROOT, iso, load_config, now_ist, read_json
from validation.verification import USABLE

OUTBOX = DATA / "app" / "outbox"


def load_env(path: Path = ROOT / ".env") -> dict:
    """Minimal .env reader (KEY=VALUE lines). Real environment variables take precedence."""
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                                                              "EMAIL_TO", "APP_SECRET")})
    return env


def unsubscribe_token(email: str, secret: str) -> str:
    return hmac.new((secret or "dev-secret").encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def _ensure_log():
    from app.store import db
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS email_log (id INTEGER PRIMARY KEY, edition TEXT NOT NULL, email TEXT NOT NULL,
                       sent_at TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, UNIQUE(edition, email))""")


def recipients(env: dict, cfg: dict) -> list[str]:
    from app.store import db
    out = [e.strip().lower() for e in env.get("EMAIL_TO", "").split(",") if e.strip()]
    if cfg["send_to_subscribers"]:
        with db() as con:
            out += [r[0] for r in con.execute("SELECT email FROM subscribers WHERE status != 'unsubscribed' ORDER BY id")]
    seen, uniq = set(), []
    for e in out:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq[: cfg["max_recipients_per_run"]]


# ------------------------------------------------------------------------------------------ content
def delta(edition: str) -> dict:
    """The day's changes, from the published daily dataset + website data."""
    from harness.report import brief_items, fresh_claims, standalone
    from harness.report import cor_name as _cn
    cor_name = lambda c: "Bengaluru (city-wide)" if c == "unmapped" else _cn(c)  # noqa: E731
    d = read_json(REPORTS / "daily" / f"{edition}.json")
    if not d:
        raise SystemExit(f"no published daily report for {edition}")
    site = read_json(DATA / "app" / "site.json", {})
    ds = {"claims": d["claims"], "stories": []}
    fresh = [c for c in fresh_claims(ds) if c["verification_status"] in USABLE]
    brief = brief_items(ds, 6)
    gov = [c for c in fresh if c["claim_type"] in ("infrastructure", "policy", "legal") and c not in brief][:5]
    projects = [{"name": p["name"], "developer": p.get("developer"), "area": cor_name(p["corridor"]).split("(")[0].strip(),
                 "type": p.get("property_type"), "status": (p.get("status") or "").replace("_", " ")} for p in d.get("projects", [])][:6]
    return {
        "edition": edition, "window": d["meta"]["window"], "status": d["meta"]["status"],
        "changes": [c.lstrip("- ") for c in d["meta"]["changes"]],
        "brief": [{"text": standalone(c), "area": cor_name(c["corridor"]), "source": c["publisher"], "url": c["url"]} for c in brief],
        "gov": [{"text": standalone(c), "source": c["publisher"], "url": c["url"]} for c in gov],
        "stage_changes": [{"name": s["name"], "to": s["stage"].replace("_", " ")} for s in d.get("stage_changes", [])],
        "projects": projects,
        "kpis": site.get("metrics", {}).get("kpis", [])[:6],
        "headlines": site.get("news", {}).get("headlines", [])[:8],
        "magazine": site.get("magazine", {}).get("label"),
    }


def render(dl: dict, cfg: dict, unsub_url: str) -> tuple[str, str]:
    e = lambda s: html.escape(str(s or ""))  # noqa: E731
    site = cfg["site_url"].rstrip("/")
    date = now_ist().strftime("%d %b %Y")

    def items(rows, fmt):
        return "".join(fmt(r) for r in rows)

    li = lambda r: (f'<li style="margin:0 0 10px">{e(r["text"])}<br><span style="color:#6b7280;font-size:13px">'  # noqa: E731
                    f'{e(r.get("area", ""))}{" · " if r.get("area") else ""}<a href="{e(r["url"])}" style="color:#1c5cab">{e(r["source"])}</a></span></li>')
    section = lambda title, body: (f'<h2 style="font:700 17px Georgia,serif;color:#0d366b;border-bottom:2px solid #0d366b;'  # noqa: E731
                                   f'padding-bottom:4px;margin:26px 0 10px">{title}</h2>{body}') if body else ""
    kpis = "".join(f'<td style="padding:10px;background:#eef5fe;border-top:3px solid #0d366b;vertical-align:top;width:33%">'
                   f'<div style="font:800 20px Arial,sans-serif;color:#0d366b">{e(k["display"])}</div>'
                   f'<div style="font:700 12px Arial,sans-serif">{e(k["label"])}</div>'
                   f'<div style="font:12px Arial,sans-serif;color:#1b8f63">{e(k["change"])}</div></td>'
                   + ("</tr><tr>" if i % 3 == 2 else "") for i, k in enumerate(dl["kpis"]))
    body = f"""<!doctype html><html><body style="margin:0;background:#f3f4f6">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 10px">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:#fff;border-radius:10px;overflow:hidden">
<tr><td style="background:#0d366b;padding:22px 26px;color:#fff">
  <div style="font:800 13px Arial,sans-serif;letter-spacing:1.5px;color:#ffcf5a">BANGALORE REALESTATE DELTA</div>
  <div style="font:800 24px Georgia,serif;margin-top:4px">Bengaluru Property Review</div>
  <div style="font:13px Arial,sans-serif;color:#c9d8ee;margin-top:4px">{e(date)} · changes in the 72 hours to {e(dl['window']['end'][:16].replace('T', ' '))} IST</div>
</td></tr>
<tr><td style="padding:6px 26px 26px;font:15px/1.55 Arial,sans-serif;color:#111827">
{section("What changed since yesterday", "<ul style='padding-left:18px;margin:0'>" + items(dl["changes"], lambda c: f"<li>{e(c)}</li>") + "</ul>")}
{section("Today’s top moves", ("<ul style='padding-left:18px;margin:0'>" + items(dl["brief"], li) + "</ul>") if dl["brief"] else "<p>No major verified change today; headlines below.</p>")}
{section("Government & infrastructure", ("<ul style='padding-left:18px;margin:0'>" + items(dl["gov"], li) + items(dl["stage_changes"], lambda s: f"<li>{e(s['name'])}: now <b>{e(s['to'])}</b></li>") + "</ul>") if (dl["gov"] or dl["stage_changes"]) else "")}
{section("New & updated projects", ("<ul style='padding-left:18px;margin:0'>" + items(dl["projects"], lambda p: f"<li><b>{e(p['name'])}</b> — {e(p['developer'])}, {e(p['area'])} ({e(p['type'])}, {e(p['status'])})</li>") + "</ul>") if dl["projects"] else "")}
{section("Market at a glance", f'<table role="presentation" width="100%" cellspacing="6" cellpadding="0"><tr>{kpis}</tr></table>') if dl["kpis"] else ""}
{section("Headlines", "<ul style='padding-left:18px;margin:0'>" + items(dl["headlines"], lambda h: f"<li style='margin-bottom:6px'><a href='{e(h['url'])}' style='color:#1c5cab'>{e(h['title'])}</a> <span style='color:#6b7280;font-size:12px'>{e((h.get('publishers') or [''])[0])}</span></li>") + "</ul>") if dl["headlines"] else ""}
<p style="margin:26px 0 0"><a href="{e(site)}" style="background:#ffcf5a;color:#0a2a54;text-decoration:none;font-weight:700;padding:11px 18px;border-radius:999px">Open the dashboard</a>
&nbsp; <a href="{e(site)}/download/magazine-latest.pdf" style="color:#0d366b;font-weight:700">Download the {e(dl['magazine'] or 'latest')} magazine</a></p>
</td></tr>
<tr><td style="background:#f9fafb;padding:16px 26px;font:12px/1.5 Arial,sans-serif;color:#6b7280">
Compiled from public sources; figures are attributed to the organisations that published them. Information only, not investment advice.<br>
Sent by Bengaluru Property Review · {e(cfg['from_address'])} · <a href="{e(unsub_url)}" style="color:#6b7280">Unsubscribe</a>
</td></tr></table></td></tr></table></body></html>"""
    text = [f"BANGALORE REALESTATE DELTA — {date}", "", "What changed since yesterday:"] + [f"- {c}" for c in dl["changes"]]
    if dl["brief"]:
        text += ["", "Today's top moves:"] + [f"- {b['text']} ({b['source']}: {b['url']})" for b in dl["brief"]]
    if dl["gov"] or dl["stage_changes"]:
        text += ["", "Government & infrastructure:"] + [f"- {g['text']} ({g['url']})" for g in dl["gov"]] + \
                [f"- {s['name']}: now {s['to']}" for s in dl["stage_changes"]]
    if dl["kpis"]:
        text += ["", "Market at a glance:"] + [f"- {k['label']}: {k['display']} ({k['change']})" for k in dl["kpis"]]
    if dl["headlines"]:
        text += ["", "Headlines:"] + [f"- {h['title']} — {h['url']}" for h in dl["headlines"]]
    text += ["", f"Dashboard: {site}", f"Unsubscribe: {unsub_url}", "Information only, not investment advice."]
    return body, "\n".join(text)


def build_message(to: str, dl: dict, cfg: dict, env: dict, attachments: list[Path]) -> EmailMessage:
    # One Bcc'd message for everyone -> a shared unsubscribe route (reply / mailto), not per-person links
    unsub = f"mailto:{cfg['reply_to']}?subject=unsubscribe"
    html_body, text_body = render(dl, cfg, unsub)
    msg = EmailMessage()
    msg["From"] = formataddr((cfg["from_name"], cfg["from_address"]))
    msg["To"] = to
    msg["Subject"] = cfg["subject"]
    msg["Reply-To"] = cfg["reply_to"]
    msg["Message-ID"] = make_msgid(domain=cfg["from_address"].split("@")[1])
    msg["List-Unsubscribe"] = f"<{unsub}>"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for p in attachments:
        msg.add_attachment(p.read_bytes(), maintype="application", subtype="pdf", filename=p.name)
    return msg


def attachments_for(edition: str, cfg: dict) -> list[Path]:
    out = []
    daily = REPORTS / "daily" / f"{edition}.pdf"
    if cfg["attachments"]["daily_pdf"] and daily.exists():
        out.append(daily)
    if cfg["attachments"]["magazine_pdf_when_new"]:
        mags = sorted((REPORTS / "magazine").glob("bengaluru-property-review-*.pdf"))
        if mags:
            from app.store import db
            with db() as con:   # attach the magazine only until each issue has been emailed once
                sent = con.execute("SELECT 1 FROM email_log WHERE edition LIKE ? LIMIT 1", (f"mag:{mags[-1].stem}%",)).fetchone()
            if not sent:
                out.append(mags[-1])
    return out


def send_delta(edition: str | None = None, only_to: str | None = None, dry_run: bool | None = None, log=None) -> dict:
    """One message per edition: To = EMAIL_TO (owner), Bcc = every active subscriber.

    Subscribers never see each other's addresses (Bcc is passed to the SMTP envelope only,
    never written into the headers). `only_to` sends a single test copy and records nothing.
    """
    from app.store import db
    cfg = load_config("email")
    if not cfg["enabled"]:
        return {"status": "disabled"}
    env = load_env()
    edition = edition or now_ist().date().isoformat()
    dry = (not env.get("SMTP_HOST")) if dry_run is None else dry_run
    _ensure_log()
    to = [only_to.lower()] if only_to else [e.strip().lower() for e in env.get("EMAIL_TO", "").split(",") if e.strip()]
    if not to:
        return {"status": "no recipient: set EMAIL_TO in .env", "edition": edition}
    bcc = [] if only_to else [e for e in recipients({}, cfg) if e not in to]
    if not only_to:
        with db() as con:
            if con.execute("SELECT 1 FROM email_log WHERE edition=? AND status='sent' LIMIT 1", (edition,)).fetchone():
                return {"status": "already sent for this edition", "edition": edition}
    dl = delta(edition)
    files = attachments_for(edition, cfg)
    msg = build_message(", ".join(to), dl, cfg, env, files)
    envelope = to + bcc
    mode = "dry_run" if dry else "smtp"
    if dry:
        path = OUTBOX / edition / "delta.eml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(msg))
        (path.parent / "envelope.txt").write_text("\n".join(envelope) + "\n")     # local only (git-ignored)
    else:
        port = int(env.get("SMTP_PORT") or cfg["smtp"]["port"])
        ctx = ssl.create_default_context()
        if cfg["smtp"]["starttls"] and port != 465:
            server = smtplib.SMTP(env["SMTP_HOST"], port, timeout=cfg["smtp"]["timeout_seconds"])
            server.starttls(context=ctx)
        else:
            server = smtplib.SMTP_SSL(env["SMTP_HOST"], port, timeout=cfg["smtp"]["timeout_seconds"], context=ctx)
        try:
            if env.get("SMTP_USER"):
                server.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
            refused = server.send_message(msg, to_addrs=envelope) or {}
        finally:
            try:
                server.quit()
            except smtplib.SMTPException:
                pass
        if refused:
            envelope = [e for e in envelope if e not in refused]
    if not only_to:
        with db() as con:
            status = "sent" if not dry else "dry_run"
            for addr in envelope:
                con.execute("INSERT OR REPLACE INTO email_log(edition, email, sent_at, mode, status) VALUES (?,?,?,?,?)",
                            (edition, addr, iso(now_ist()), mode, status))
            if not dry:
                for f in files:
                    if "bengaluru-property-review" in f.name:
                        con.execute("INSERT OR IGNORE INTO email_log(edition, email, sent_at, mode, status) VALUES (?,?,?,?,?)",
                                    (f"mag:{f.stem}", "*", iso(now_ist()), mode, "sent"))
    result = {"status": "ok", "mode": mode, "edition": edition, "to": len(to), "bcc": len(bcc), "sent": len(envelope),
              "attachments": [f.name for f in files], "outbox": str(OUTBOX / edition) if dry else None}
    if log:
        log("email_delta", **result)
    return result

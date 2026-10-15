"""Delta email: config-driven From/Subject, recipients, idempotent sending, unsubscribe links."""
import email
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path
    for d in ("config", "content_engineering", "prompts", "validation", "app"):
        (root / d).symlink_to(REPO / d)
    (root / "reports" / "daily").mkdir(parents=True)
    (root / "reports" / "magazine").mkdir(parents=True)
    meta = {"window": {"start": "2026-10-12T06:00:00+05:30", "end": "2026-10-15T06:00:00+05:30"}, "status": "ok",
            "changes": ["3 new claims, 2 usable."]}
    (root / "reports" / "daily" / "2026-10-15.json").write_text(json.dumps({"meta": meta, "claims": [], "projects": [], "stage_changes": []}))
    (root / "reports" / "daily" / "2026-10-15.pdf").write_bytes(b"%PDF-1.4 daily")
    (root / "reports" / "magazine" / "bengaluru-property-review-2026-10.pdf").write_bytes(b"%PDF-1.4 mag")
    (root / "data" / "app").mkdir(parents=True)
    (root / "data" / "app" / "site.json").write_text(json.dumps({"metrics": {"kpis": [{"label": "Sales", "display": "16,670", "change": "+12%"}]},
                                                                "news": {"headlines": []}, "magazine": {"label": "October 2026"}}))
    (root / ".env").write_text("EMAIL_TO=owner@example.com\nAPP_SECRET=s3cret\n")
    monkeypatch.setenv("BREI_ROOT", str(root))
    for k in ("SMTP_HOST", "EMAIL_TO", "APP_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for m in [m for m in sys.modules if m.startswith(("app", "harness", "validation", "analysis", "noise_removal", "recheck"))]:
        del sys.modules[m]
    import harness.mailer as mailer
    from app import store
    store.add_subscriber("reader@example.com")
    return root, mailer, store


def test_dry_run_to_owner_bcc_subscribers(env):
    root, mailer, _ = env
    r = mailer.send_delta("2026-10-15")
    assert r["mode"] == "dry_run" and (r["to"], r["bcc"], r["sent"]) == (1, 1, 2)
    assert r["attachments"] == ["2026-10-15.pdf", "bengaluru-property-review-2026-10.pdf"]
    raw = (root / "data/app/outbox/2026-10-15/delta.eml").read_bytes()
    msg = email.message_from_bytes(raw)
    assert msg["Subject"] == "Bangalore RealEstate Delta"
    assert "info@raditsoftware.com" in msg["From"] and msg["To"] == "owner@example.com"
    assert msg["Bcc"] is None and b"reader@example.com" not in raw        # subscribers never in headers
    assert msg["List-Unsubscribe"].strip().startswith("<mailto:info@raditsoftware.com")
    assert (root / "data/app/outbox/2026-10-15/envelope.txt").read_text().split() == ["owner@example.com", "reader@example.com"]


def test_smtp_send_is_idempotent_and_skips_unsubscribed(env, monkeypatch):
    root, mailer, store = env
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def starttls(self, **k): pass
        def login(self, u, p): sent.append(("login", u))
        def send_message(self, m, to_addrs=None): sent.extend(to_addrs); return {}
        def quit(self): pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    (root / ".env").write_text("SMTP_HOST=smtp.test\nSMTP_USER=info@raditsoftware.com\nSMTP_PASSWORD=x\n"
                               "EMAIL_TO=owner@example.com\nAPP_SECRET=s3cret\n")
    store.add_subscriber("second@example.com")
    store.unsubscribe("reader@example.com")
    r1 = mailer.send_delta("2026-10-15")
    r2 = mailer.send_delta("2026-10-15")
    assert r1["mode"] == "smtp" and sent == [("login", "info@raditsoftware.com"), "owner@example.com", "second@example.com"]
    assert r2["status"] == "already sent for this edition"


def test_unsubscribe_token_is_signed(env):
    _, mailer, _ = env
    t = mailer.unsubscribe_token("a@b.com", "s3cret")
    assert t == mailer.unsubscribe_token("A@B.com", "s3cret") and t != mailer.unsubscribe_token("a@b.com", "other")

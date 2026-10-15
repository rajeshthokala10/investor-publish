"""Web app API: data endpoints, downloads allow-list, subscribe validation, admin locality."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("web")
    for d in ("config", "content_engineering", "prompts", "validation", "app"):
        (root / d).symlink_to(REPO / d)
    (root / "data" / "app" / "downloads").mkdir(parents=True)
    site = {"generated_at": "2026-10-15T06:00:00+05:30", "daily": {}, "magazine": {"label": "October 2026"},
            "news": {"insights": [], "headlines": [{"title": "Metro update", "url": "https://x", "publishers": ["The Hindu"],
                                                     "published_at": None, "zone": "East"}]},
            "metrics": {"kpis": [{"label": "Sales", "display": "16,670"}], "series": [], "area_prices": [], "builders": [],
                        "tracked_developers": []}, "plans": [], "growth_towns": [], "zones": [], "quotes": [], "downloads": {}}
    (root / "data" / "app" / "site.json").write_text(json.dumps(site))
    (root / "data" / "app" / "downloads" / "magazine-latest.pdf").write_bytes(b"%PDF-1.4 test")
    os.environ["BREI_ROOT"] = str(root)
    for m in [m for m in sys.modules if m.startswith(("app", "harness"))]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.server import app
    yield TestClient(app)
    os.environ.pop("BREI_ROOT")


def test_data_endpoints(client):
    assert client.get("/healthz").json()["site_data"] is True
    assert client.get("/api/metrics").json()["kpis"][0]["display"] == "16,670"
    assert client.get("/api/news").json()["headlines"][0]["zone"] == "East"
    assert client.get("/").status_code == 200 and "Bengaluru" in client.get("/").text


def test_downloads_allow_list(client):
    r = client.get("/download/magazine-latest.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert client.get("/download/site.json").status_code == 404
    assert client.get("/download/daily-brief-latest.pdf").status_code == 404     # not published in this fixture


def test_subscribe_validates_and_dedupes(client):
    assert client.post("/api/subscribe", json={"email": "nope"}).status_code == 422
    r1 = client.post("/api/subscribe", json={"email": "Reader@Example.com", "interests": ["east"]})
    r2 = client.post("/api/subscribe", json={"email": "reader@example.com"})
    assert r1.json()["ok"] and "already" in r2.json()["message"]
    assert client.get("/api/status").json()["subscribers"] == 1

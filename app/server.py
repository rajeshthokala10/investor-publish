"""Bengaluru Property Review — business website (FastAPI).

Public:  GET  /                       landing page; site data is embedded server-side (no client API calls)
         GET  /privacy, /terms        policy pages
         POST /subscribe              {email, name?, interests?}
         GET  /download/{file}        magazine-latest.pdf, daily-brief-latest.pdf, magazine-cover.png
Local only (this machine): /api/* data + admin endpoints, for monitoring and the batch job.
No public API documentation is served.
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import store
from app.site_data import APP_DATA, DOWNLOADS
from harness.common import read_json

STATIC = Path(__file__).parent / "static"
ALLOWED_DOWNLOADS = {"magazine-latest.pdf", "daily-brief-latest.pdf", "magazine-cover.png"}

app = FastAPI(title="Bengaluru Property Review", docs_url=None, redoc_url=None, openapi_url=None)

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",                       # no embedding in other sites (also blocks frame-based scraping)
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), display-capture=()",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
                                "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; "
                                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.url.path.startswith("/api/") and (request.client is None or
                                                 request.client.host not in ("127.0.0.1", "::1", "testclient")):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


def site() -> dict:
    data = read_json(APP_DATA / "site.json")
    if data is None:
        raise HTTPException(503, "Site data not built yet. Run: python -m harness.cli batch --steps metrics,site")
    return data


class Subscription(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(default="", max_length=80)
    interests: list[str] = Field(default_factory=list, max_length=8)


def local_only(request: Request):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(403, "Admin endpoints are available from this machine only.")


@app.get("/api/site")
def api_site():
    return site()


@app.get("/api/news")
def api_news():
    return site()["news"]


@app.get("/api/metrics")
def api_metrics():
    m = site()["metrics"]
    return {k: m[k] for k in ("kpis", "series", "area_prices")}


@app.get("/api/builders")
def api_builders():
    m = site()["metrics"]
    return {"builders": m["builders"], "tracked_developers": m["tracked_developers"]}


@app.get("/api/plans")
def api_plans():
    s = site()
    return {"plans": s["plans"], "growth_towns": s["growth_towns"]}


@app.get("/api/status")
def api_status():
    s = read_json(APP_DATA / "site.json", {})
    return {"generated_at": s.get("generated_at"), "daily": s.get("daily"), "magazine": s.get("magazine", {}).get("label"),
            "subscribers": store.subscriber_count(), "jobs": store.last_jobs(5)}


@app.post("/subscribe")
@app.post("/api/subscribe")
def api_subscribe(sub: Subscription):
    ok, msg = store.add_subscriber(sub.email, sub.name, sub.interests)
    return JSONResponse({"ok": ok, "message": msg}, status_code=200 if ok else 422)


@app.get("/download/{name}")
def download(name: str):
    if name not in ALLOWED_DOWNLOADS:
        raise HTTPException(404, "Not found")
    path = DOWNLOADS / name
    if not path.exists():
        raise HTTPException(404, "Not published yet")
    media = "application/pdf" if name.endswith(".pdf") else "image/png"
    disposition = "attachment" if name.endswith(".pdf") else "inline"
    return FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition)


@app.get("/api/admin/subscribers")
def admin_subscribers(request: Request):
    local_only(request)
    return {"subscribers": store.list_subscribers()}


@app.post("/api/admin/refresh")
def admin_refresh(request: Request):
    local_only(request)
    from harness.batch import run_batch
    threading.Thread(target=run_batch, args=(["metrics", "site"],), daemon=True).start()
    return {"started": True}


@app.get("/unsubscribe")
def unsubscribe(email: str, token: str):
    import hmac as _hmac
    from fastapi.responses import HTMLResponse
    from harness.mailer import load_env, unsubscribe_token
    if not _hmac.compare_digest(token, unsubscribe_token(email, load_env().get("APP_SECRET", ""))):
        raise HTTPException(403, "Invalid unsubscribe link")
    store.unsubscribe(email)
    return HTMLResponse("<!doctype html><meta charset=utf-8><title>Unsubscribed</title><body style='font-family:system-ui;"
                        "max-width:520px;margin:15vh auto;padding:16px'><h1>You're unsubscribed</h1><p>You will no longer receive "
                        "the Bangalore RealEstate Delta email.</p><p><a href='/'>Back to Bengaluru Property Review</a></p>")


@app.get("/healthz")
def healthz():
    return {"ok": True, "site_data": (APP_DATA / "site.json").exists()}


def public_site() -> dict:
    """The landing page's data, minus internal fields (job history, dropped items, raw paths)."""
    s = dict(read_json(APP_DATA / "site.json", {}))
    s["metro"] = read_json(STATIC.parent / "content" / "metro.json", {})
    return s


@app.get("/", response_class=HTMLResponse)
def index():
    import json as _json
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    data = _json.dumps(public_site(), ensure_ascii=False).replace("</", "<\\/")
    return HTMLResponse(page.replace("<!--SITE_DATA-->", f'<script id="site-data" type="application/json">{data}</script>'),
                        headers={"Cache-Control": "no-store"})


@app.get("/index.html")
def index_alias():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/", status_code=301)


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return HTMLResponse((STATIC / "privacy.html").read_text(encoding="utf-8"))


@app.get("/terms", response_class=HTMLResponse)
def terms():
    return HTMLResponse((STATIC / "terms.html").read_text(encoding="utf-8"))


app.mount("/", StaticFiles(directory=STATIC, html=False), name="static")

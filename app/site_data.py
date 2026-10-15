"""Assemble data/app/site.json: everything the web app shows, from the validated datasets."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from harness.common import DATA, PROCESSED, REPORTS, ROOT, iso, now_ist, read_json, write_json
from harness.registry import corridors, region_of
from validation.verification import USABLE

APP_DATA = DATA / "app"
DOWNLOADS = APP_DATA / "downloads"
REGION_NAME = {"east": "East", "north": "North", "south": "South", "west": "West", "peripheral": "Outer ring",
               "unmapped": "City-wide"}


def latest(pattern: str, folder: Path) -> Path | None:
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


def cover_thumbnail(mag_html: Path, out_png: Path) -> bool:
    """Screenshot the magazine's first page (A4 at 96 dpi) for the landing page."""
    from harness.report import CHROME
    exe = next((x for x in CHROME if Path(x).exists()), None)
    if not exe:
        return False
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=794,1123",
                    f"--screenshot={out_png}", mag_html.resolve().as_uri()], capture_output=True, timeout=120)
    return out_png.exists()


TOPIC = re.compile(r"\b(real estate|realty|property|properties|housing|home ?buyers?|apartments?|flats?|villas?|plots?|plotted|"
                   r"layout|launch|rera|developer|builder|metro|bmrcl|suburban|k-ride|ring road|strr|prr|flyover|underpass|"
                   r"expressway|tunnel|airport|bwssb|cauvery|water supply|drain|lake|bda|bmrda|gba|greater bengaluru|zoning|"
                   r"master plan|guidance value|stamp duty|khata|office|leasing|tech park|gcc|kiadb|township|rent|rental|"
                   r"price|sq ?ft|land|infrastructure|road)\b", re.I)
OFF_TOPIC = re.compile(r"\b(murder|murdered|killed|dies|death|arrested|accident|crash|silver rate|gold rate|cricket|ipl|"
                       r"noida|gurugram|gurgaon|mumbai|pune|hyderabad|chennai|kolkata|delhi|ahmedabad|horoscope)\b", re.I)
CITY = re.compile(r"\b(bengaluru|bangalore|karnataka|namma metro|bmrcl|bda|gba|bwssb)\b", re.I)


def relevant_headline(title: str, zone: str) -> bool:
    """Website news: Bengaluru real-estate/infrastructure stories only (the daily pipeline keeps everything)."""
    if not TOPIC.search(title) or (OFF_TOPIC.search(title) and not CITY.search(title)):
        return False
    if re.search(r"\b(murder|murdered|killed|arrested|accident|silver rate|gold rate|stolen|theft|robbery|organ|heart|"
                 r"surgery|hospital|patient)\b", title, re.I):
        return False
    return bool(CITY.search(title)) or zone != "City-wide"


def news(daily: dict) -> dict:
    claims = daily.get("claims", [])
    fresh = [c for c in claims if c.get("novelty") != "repeat" and c["verification_status"] in USABLE
             and not {"outside_window", "republished_old_event"} & set(c["flags"])
             and c["origin"] != "agent:market_baseline"]
    from harness.report import standalone
    insights = [{"title": standalone(c), "subject": c["subject"], "area": corridors().get(c["corridor"], {}).get("name", "Bengaluru"),
                 "zone": REGION_NAME.get(region_of(c["corridor"]), "City-wide"), "publisher": c["publisher"], "url": c["url"],
                 "published_at": c["published_at"], "type": c["claim_type"]} for c in fresh][:12]
    stories = []
    for s in daily.get("stories", []):
        if s.get("novelty") == "repeat" or s.get("stale_flags"):
            continue
        zone = REGION_NAME.get((s.get("regions") or ["unmapped"])[0], "City-wide")
        if not relevant_headline(s["title"], zone):
            continue
        stories.append({"title": s["title"], "url": s["url"], "publishers": s["publishers"],
                        "published_at": s.get("published_at"),
                        "zone": zone})
    # evening refresh (18:00 IST) goes first; then the morning edition; one entry per URL
    ev = read_json(APP_DATA / "news_refresh.json", {})
    if ev and ev.get("generated_at", "") > (daily.get("meta", {}).get("generated_at") or ""):
        ev_ins = [{"title": standalone(c), "subject": c["subject"], "area": corridors().get(c["corridor"], {}).get("name", "Bengaluru"),
                   "zone": REGION_NAME.get(region_of(c["corridor"]), "City-wide"), "publisher": c["publisher"], "url": c["url"],
                   "published_at": c["published_at"], "type": c["claim_type"]} for c in ev.get("claims", [])]
        insights = (ev_ins + insights)[:12]
        for s in ev.get("stories", []):
            zone = REGION_NAME.get((s.get("regions") or ["unmapped"])[0], "City-wide")
            if relevant_headline(s["title"], zone):
                stories.append({"title": s["title"], "url": s["url"], "publishers": s["publishers"],
                                "published_at": s.get("published_at"), "zone": zone})
    uniq = {}
    for h in stories:
        uniq.setdefault(h["url"], h)
    stories = sorted(uniq.values(), key=lambda s: s["published_at"] or "", reverse=True)
    return {"insights": insights, "headlines": stories[:40], "evening_refresh": ev.get("generated_at") if ev else None}


def _fmt_value(f: dict) -> str:
    v, u = f["value"], f["unit"].lower()
    num = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")
    if "crore" in u:
        return f"₹{num} crore"
    if "bn" in u or "billion" in u:
        return f"₹{num} bn"
    return f"{num} {f['unit']}".replace("mn sft", "mn sq ft")


def top_builders() -> list[dict]:
    """Sobha, Godrej Properties, Brigade: project counts + sales value, each with period, scope and source."""
    data = read_json(APP_DATA / "builders.json", {})
    out = []
    for b in data.get("builders", []):
        seen, projects, sales, other = set(), [], [], []
        for f in b["figures"]:
            key = (f["metric"], f["value"])
            if key in seen:
                continue
            seen.add(key)
            row = {"label": f["label"].split(" (")[0], "value": _fmt_value(f), "period": f["period"],
                   "scope": "Bengaluru" if f["scope"] == "bengaluru" else "Company-wide", "source": f["publisher"], "url": f["url"]}
            if f["metric"] in ("total_projects", "completed_projects", "ongoing_projects", "bengaluru_projects"):
                projects.append(row)
            elif f["metric"] == "sales_value":
                sales.append(row)
            elif f["metric"] in ("sales_area", "collections"):
                other.append(row)
        sales.sort(key=lambda r: ("Q" in r["period"].split()[0], r["scope"] != "Company-wide"))
        out.append({"name": b["name"], "headline": b.get("headline", ""), "projects": projects[:3], "sales": sales[:4],
                    "other": other[:2], "bengaluru_projects": b.get("bengaluru_projects", [])[:5]})
    return out


def build_site(log=None) -> dict:
    daily_json = latest("????-??-??.json", REPORTS / "daily")
    daily = read_json(daily_json, {}) if daily_json else {}
    mag_pdf = latest("bengaluru-property-review-*.pdf", REPORTS / "magazine")
    mag_html = latest("bengaluru-property-review-*.html", REPORTS / "magazine")
    edition = mag_pdf.stem.rsplit("-", 2)[-2] + "-" + mag_pdf.stem.rsplit("-", 1)[-1] if mag_pdf else None
    issue = read_json(PROCESSED / "magazine" / f"{edition}.issue.json", {}) if edition else {}
    metrics = read_json(APP_DATA / "metrics.json", {})

    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    downloads = {}
    if mag_pdf:
        shutil.copy2(mag_pdf, DOWNLOADS / "magazine-latest.pdf")
        downloads["magazine"] = {"file": "magazine-latest.pdf", "title": f"Bengaluru Property Review — {issue.get('_meta', {}).get('label', edition)}",
                                 "pages": 10, "size_mb": round(mag_pdf.stat().st_size / 1e6, 1)}
        if mag_html and cover_thumbnail(mag_html, DOWNLOADS / "magazine-cover.png"):
            downloads["magazine"]["cover"] = "magazine-cover.png"
            shutil.copy2(DOWNLOADS / "magazine-cover.png", APP_DATA / "magazine-cover.png")   # committed for deploys
    daily_pdf = daily_json.with_suffix(".pdf") if daily_json else None
    if daily_pdf and daily_pdf.exists():
        shutil.copy2(daily_pdf, DOWNLOADS / "bangalore-realestate-delta-latest.pdf")
        shutil.copy2(daily_pdf, DOWNLOADS / "daily-brief-latest.pdf")          # old link keeps working
        downloads["daily"] = {"file": "bangalore-realestate-delta-latest.pdf", "title": f"Bangalore Realestate Delta — {daily_json.stem}", "pages": 5,
                              "size_mb": round(daily_pdf.stat().st_size / 1e6, 1)}

    site = {
        "generated_at": iso(now_ist()),
        "daily": {"edition": daily_json.stem if daily_json else None, "window": daily.get("meta", {}).get("window"),
                  "status": daily.get("meta", {}).get("status")},
        "magazine": {"edition": edition, "label": issue.get("_meta", {}).get("label"),
                     "cover": issue.get("cover"), "editor_note": issue.get("editor_note", [])},
        "news": news(daily),
        "metrics": {k: metrics.get(k, []) for k in ("kpis", "series", "area_prices", "builders", "tracked_developers")},
        "top_builders": top_builders(),
        "plans": issue.get("gov_rows", []),
        "growth_towns": issue.get("growth_towns", []),
        "zones": [{"zone": z["zone"], "title": z["title"], "standfirst": z["standfirst"],
                   "markets": z["micro_markets"]} for z in issue.get("zones", [])],
        "quotes": read_json(ROOT / "app" / "content" / "quotes.json", []),
        "clusters": [__import__("app.articles", fromlist=["summary"]).summary(c) for c in
                     read_json(APP_DATA / "clusters.json", {}).get("clusters", [])],
        "downloads": downloads,
    }
    write_json(APP_DATA / "site.json", site)
    if log:
        log("site_built", headlines=len(site["news"]["headlines"]), insights=len(site["news"]["insights"]),
            kpis=len(site["metrics"]["kpis"]), series=len(site["metrics"]["series"]))
    return site

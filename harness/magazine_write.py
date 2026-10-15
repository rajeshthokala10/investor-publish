"""Magazine writer: an LLM with NO tools turns publishable claims into magazine copy.

Guardrails enforced in code after generation:
* every cited claim ID must be publishable (see magazine.publishable);
* every number in a text block must appear in the claims it cites;
* failing blocks are removed (logged), never printed.
"""
from __future__ import annotations

import json
import re

from harness import agent
from harness.common import PROMPTS, iso, now_ist, read_json, write_json
from harness.registry import corridors, region_of

P = {"type": "object", "additionalProperties": False, "required": ["text", "claim_ids"],
     "properties": {"text": {"type": "string"}, "claim_ids": {"type": "array", "items": {"type": "string"}}}}
PARAS = {"type": "array", "items": P}


def _row(fields: list[str]) -> dict:
    props = {f: {"type": "string"} for f in fields}
    props["claim_ids"] = {"type": "array", "items": {"type": "string"}}
    return {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                       "required": fields + ["claim_ids"], "properties": props}}


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["cover", "editor_note", "key_figures", "glance", "gov_intro", "gov_rows", "growth_map_caption",
                 "zones", "growth_intro", "growth_towns", "property_types", "outlook", "watch_list", "projects"],
    "properties": {
        "cover": {"type": "object", "additionalProperties": False,
                  "required": ["headline", "subhead", "cover_lines", "claim_ids"],
                  "properties": {"headline": {"type": "string"}, "subhead": {"type": "string"},
                                 "cover_lines": {"type": "array", "items": {"type": "string"}},
                                 "claim_ids": {"type": "array", "items": {"type": "string"}}}},
        "editor_note": PARAS,
        "key_figures": _row(["label", "value_text", "context"]),
        "glance": PARAS,
        "gov_intro": PARAS,
        "gov_rows": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["category", "project", "status", "timeline", "areas", "claim_ids"],
                     "properties": {"category": {"enum": ["metro", "suburban_rail", "road", "airport", "township",
                                                          "water", "governance", "policy"]},
                                    "project": {"type": "string"}, "status": {"type": "string"},
                                    "timeline": {"type": "string"}, "areas": {"type": "string"},
                                    "claim_ids": {"type": "array", "items": {"type": "string"}}}}},
        "growth_map_caption": PARAS,
        "zones": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "required": ["zone", "title", "standfirst", "paragraphs", "micro_markets"],
                  "properties": {"zone": {"enum": ["east", "north", "south", "west"]}, "title": {"type": "string"},
                                 "standfirst": {"type": "string"}, "paragraphs": PARAS,
                                 "micro_markets": _row(["name", "price_text", "drivers", "watch"])}}},
        "growth_intro": PARAS,
        "growth_towns": _row(["name", "why", "price_text", "risks"]),
        "property_types": {"type": "object", "additionalProperties": False,
                           "required": ["plots", "villas", "apartments", "verdict"],
                           "properties": {k: PARAS for k in ("plots", "villas", "apartments", "verdict")}},
        "outlook": PARAS,
        "watch_list": _row(["item", "why"]),
        "projects": _row(["name", "developer", "location", "type", "detail"]),
    },
}

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def nums(text: str) -> set[str]:
    out = set()
    for n in NUM.findall(text or ""):
        n = n.replace(",", "").rstrip(".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def fact_bank(claims: list[dict]) -> list[dict]:
    rows = []
    for c in claims:
        fig = ""
        if c["value"] is not None:
            fig = f"{c['value']:g}" + (f"–{c['value_max']:g}" if c.get("value_max") else "") + f" {c['unit'] or ''}"
            if c["metric"] in ("price_psf", "price_total"):
                fig += f" ({c['price_basis']}, {c['price_kind'].replace('_', ' ')})"
        rows.append({"id": c["claim_id"], "fact": c["statement"], "place": c.get("locality") or c["subject"],
                     "zone": region_of(c["corridor"]), "type": c["claim_type"], "figure": fig.strip(),
                     "source": c["publisher"], "date": c["published_at"], "stage": c.get("evidenced_stage") or ""})
    return rows


def check_block(text: str, ids: list[str], by: dict) -> str | None:
    """None if fine, else reason. Numbers must come from the cited claims."""
    cited = [by[i] for i in ids if i in by]
    if not cited:
        return "no valid claim cited"
    allowed = set()
    for c in cited:
        allowed |= nums(c["statement"]) | nums(c["excerpt"]) | nums(c["subject"]) | nums(c.get("published_at") or "")
        for v in (c.get("value"), c.get("value_max"), c.get("period_years")):
            if v is not None:
                allowed |= nums(f"{v:g}")
    extra = nums(text) - allowed
    return f"numbers not in cited claims: {sorted(extra)}" if extra else None


def validate(issue: dict, by: dict, log) -> tuple[dict, list[str]]:
    dropped = []

    def keep_paras(paras, where):
        out = []
        for p in paras:
            why = check_block(p["text"], p["claim_ids"], by)
            if why:
                dropped.append(f"{where}: {why} :: {p['text'][:80]}")
            else:
                out.append(p)
        return out

    def keep_rows(rows, fields, where):
        out = []
        for r in rows:
            why = check_block(" ".join(r[f] for f in fields), r["claim_ids"], by)
            if why:
                dropped.append(f"{where}: {why} :: {r[fields[0]][:60]}")
            else:
                out.append(r)
        return out

    cv = issue["cover"]
    why = check_block(" ".join([cv["headline"], cv["subhead"], *cv["cover_lines"]]), cv["claim_ids"], by)
    if why:   # keep the cover but strip numbers from it rather than print an unsupported figure
        dropped.append(f"cover: {why}")
        for k in ("headline", "subhead"):
            cv[k] = NUM.sub("", cv[k]).replace("  ", " ").strip()
        cv["cover_lines"] = [l for l in cv["cover_lines"] if not NUM.search(l)]
    for k in ("editor_note", "glance", "gov_intro", "growth_map_caption", "growth_intro", "outlook"):
        issue[k] = keep_paras(issue[k], k)
    for k in ("plots", "villas", "apartments", "verdict"):
        issue["property_types"][k] = keep_paras(issue["property_types"][k], f"property_types.{k}")
    issue["key_figures"] = keep_rows(issue["key_figures"], ["label", "value_text", "context"], "key_figures")
    issue["gov_rows"] = keep_rows(issue["gov_rows"], ["project", "status", "timeline", "areas"], "gov_rows")
    issue["growth_towns"] = keep_rows(issue["growth_towns"], ["name", "why", "price_text", "risks"], "growth_towns")
    issue["watch_list"] = keep_rows(issue["watch_list"], ["item", "why"], "watch_list")
    issue["projects"] = keep_rows(issue["projects"], ["name", "developer", "location", "type", "detail"], "projects")
    for z in issue["zones"]:
        z["paragraphs"] = keep_paras(z["paragraphs"], f"zone.{z['zone']}")
        z["micro_markets"] = keep_rows(z["micro_markets"], ["name", "price_text", "drivers", "watch"], f"zone.{z['zone']}.mm")
        why = check_block(z["standfirst"], [i for p in z["paragraphs"] for i in p["claim_ids"]], by) if NUM.search(z["standfirst"]) else None
        if why:
            z["standfirst"] = ""
            dropped.append(f"zone.{z['zone']}.standfirst: {why}")
    return issue, dropped


def write_issue(edition: str, log) -> dict:
    from harness.magazine import MAG_OUT, cfg, publishable
    data = read_json(MAG_OUT / f"{edition}.json")
    pub = [c for c in data["claims"] if publishable(c)]
    by = {c["claim_id"]: c for c in pub}
    label = now_ist().strftime("%B %Y") if edition == now_ist().strftime("%Y-%m") else edition
    facts = "\n".join(json.dumps(r, ensure_ascii=False) for r in fact_bank(pub))
    prompt = (PROMPTS / "magazine_writer.md").read_text(encoding="utf-8") \
        .replace("{{EDITION_LABEL}}", label).replace("{{FACTS}}", facts)
    res = agent.run_agent(prompt, SCHEMA, name=f"magazine_writer_{edition}", out_path=MAG_OUT / f"{edition}.writer_raw.json",
                          budget_usd=cfg()["agent"]["writer_budget_usd"], timeout_min=20, log=log, tools=[])
    if not res["ok"]:
        raise SystemExit(f"magazine writer failed: {res['error']}")
    issue, dropped = validate(res["data"], by, log)
    issue["_meta"] = {"edition": edition, "label": label, "written_at": iso(now_ist()), "facts": len(pub),
                      "dropped_blocks": dropped}
    write_json(MAG_OUT / f"{edition}.issue.json", issue)
    log("magazine_written", facts=len(pub), dropped=len(dropped))
    return issue

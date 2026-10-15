"""Marketing-language and unsupported-guarantee detection."""
from __future__ import annotations

import re

GUARANTEE = re.compile(
    r"(guarantee[d]?\s+(returns?|appreciation|rental|growth|profit)|assured\s+(returns?|appreciation|rental|buy-?back)|"
    r"double\s+your\s+(money|investment)|prices?\s+(will|are\s+set\s+to)\s+(double|triple|skyrocket|soar)|"
    r"risk[- ]free\s+investment|\d+\s*%\s+(guaranteed|assured))", re.I)
HYPE = re.compile(
    r"(once[- ]in[- ]a[- ]lifetime|limited[- ]period\s+offer|pre[- ]launch\s+offer|hurry|book\s+now|best\s+investment|"
    r"never\s+before|unbeatable|lowest\s+price\s+ever|high\s+roi|massive\s+appreciation|next\s+(gurgaon|whitefield|gold\s+mine)|"
    r"luxury\s+redefined|world[- ]class\s+amenities|exclusive\s+offer|few\s+units\s+left|spot\s+offer|zero\s+brokerage|"
    r"call\s+now|whatsapp|emi\s+holiday|no\s+pre-?emi)", re.I)


def marketing_profile(*texts: str | None) -> dict:
    text = " ".join(t for t in texts if t)
    guarantees = sorted({m.group(0).lower() for m in GUARANTEE.finditer(text)})
    hype = sorted({m.group(0).lower() for m in HYPE.finditer(text)})
    words = max(len(text.split()), 1)
    score = min(1.0, (3 * len(guarantees) + len(hype)) / max(3.0, words / 25))
    return {"guarantee_phrases": guarantees, "hype_phrases": hype, "marketing_score": round(score, 2)}


def flags_for(profile: dict) -> list[str]:
    flags = []
    if profile["guarantee_phrases"]:
        flags.append("unsupported_guarantee")
    if profile["marketing_score"] >= 0.5 or len(profile["hype_phrases"]) >= 2:
        flags.append("marketing_language")
    return flags

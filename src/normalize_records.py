import json
import re
from typing import Dict, Any

PHONE_RE = re.compile(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')


def extract_phone(text: str):
    m = PHONE_RE.search(text)
    return m.group(1) if m else None


def infer_eligibility_flags(text: str):
    t = text.lower()
    return {
        "family_friendly": ("family" in t or "families" in t or "children" in t),
        "senior_only": ("senior" in t or "seniors" in t),
        "veterans_only": ("veteran" in t or "veterans" in t),
        "appointment_required": ("appointment required" in t)
    }


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    text = raw.get("text", "")
    eligibility_text = raw.get("eligibility_text", text)
    inferred = infer_eligibility_flags(eligibility_text)
    explicit = raw.get("eligibility_flags")
    if isinstance(explicit, dict):
        eligibility_flags = {**inferred, **explicit}
    else:
        eligibility_flags = inferred

    return {
        "resource_id": raw.get("resource_id"),
        "org_name": raw.get("org_name", ""),
        "service_category": raw.get("service_category", []),
        "description": raw.get("description", ""),
        "address": raw.get("address", ""),
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "zip": raw.get("zip", ""),
        "lat": raw.get("lat"),
        "lon": raw.get("lon"),
        "hours_text": raw.get("hours_text", ""),
        "hours_normalized": raw.get("hours_normalized", {}),
        "eligibility_text": eligibility_text,
        "eligibility_flags": eligibility_flags,
        "phone": raw.get("phone") or extract_phone(text),
        "source_url": raw.get("source_url", ""),
        "source_type": raw.get("source_type", ""),
        "last_verified": raw.get("last_verified", "")
    }


def normalize_jsonl(infile: str, outfile: str):
    with open(infile, "r", encoding="utf-8") as fin, open(outfile, "w", encoding="utf-8") as fout:
        for line in fin:
            raw = json.loads(line)
            norm = normalize_record(raw)
            fout.write(json.dumps(norm, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    normalize_jsonl("../data/raw_resources.jsonl", "../data/normalized_resources.jsonl")

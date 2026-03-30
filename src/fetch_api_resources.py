"""
API-based resource fetcher for 211.org and HUD.
Pulls structured JSON directly — no HTML scraping.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 HOW TO GET API KEYS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 211 API (United Way):
   1. Go to https://api.211.org/
   2. Click "Request Access" and fill out the form
      (academic / research use is approved quickly)
   3. Set the key as:  export API_211_KEY="your_key_here"
   Docs: https://api.211.org/docs

 HUD API (housing resources):
   1. Go to https://www.huduser.gov/portal/dataset/apidescription.html
   2. Click "Request a Token" — free, instant
   3. Set the key as:  export HUD_API_KEY="your_key_here"
   Docs: https://www.huduser.gov/portal/dataset/apidescription.html

 You can also paste keys directly into the CONFIG block below.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    python fetch_api_resources.py                     # both sources, default locations
    python fetch_api_resources.py --source 211        # 211 only
    python fetch_api_resources.py --source hud        # HUD only
    python fetch_api_resources.py --output ../data/raw_resources_api.jsonl
"""

import argparse
import json
import os
import re
import time
from datetime import date
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# CONFIG — edit here or set environment variables
# ---------------------------------------------------------------------------

API_211_KEY = os.getenv("API_211_KEY", "")
HUD_API_KEY = os.getenv("HUD_API_KEY", "")

# Search locations: (display_name, latitude, longitude, radius_miles)
SEARCH_LOCATIONS = [
    ("Ann Arbor, MI",      42.2808, -83.7430, 15),
    ("Ypsilanti, MI",      42.2411, -83.6130, 10),
    ("Detroit, MI",        42.3314, -83.0458, 20),
    ("Lansing, MI",        42.7325, -84.5555, 15),
    ("Flint, MI",          43.0125, -83.6875, 15),
    ("Grand Rapids, MI",   42.9634, -85.6681, 15),
    ("Kalamazoo, MI",      42.2917, -85.5872, 15),
    ("Saginaw, MI",        43.4195, -83.9508, 15),
]

# 211 taxonomy codes for the service types we care about
# See: https://api.211.org/docs/taxonomy
TAXONOMY_211 = {
    "food_pantry":        "BD-1800",   # Food Pantries
    "shelter":            "BH-1800",   # Emergency Shelter
    "housing_assistance": "BH-3000",   # Housing Assistance Programs
}

TODAY = date.today().isoformat()
PHONE_RE = re.compile(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')


# ---------------------------------------------------------------------------
# 211 API
# ---------------------------------------------------------------------------

def fetch_211_resources(
    api_key: str,
    lat: float,
    lon: float,
    radius_miles: int,
    taxonomy_codes: Optional[list] = None,
) -> list:
    """
    Query the 211.org API for social service resources near a coordinate.
    Returns raw API records (list of dicts).

    API reference: https://api.211.org/docs
    """
    base = "https://api.211.org/search/v1/organizations"
    codes = taxonomy_codes or list(TAXONOMY_211.values())
    results = []

    for code in codes:
        params = {
            "latitude":  lat,
            "longitude": lon,
            "radius":    radius_miles,
            "taxonomy":  code,
            "per_page":  100,
            "page":      1,
        }
        headers = {"x-api-key": api_key}

        while True:
            try:
                resp = requests.get(base, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            except requests.HTTPError as e:
                print(f"    211 API error ({code}): {e}")
                break

            data = resp.json()
            page_results = data.get("organizations") or data.get("results") or []
            results.extend(page_results)

            # Pagination
            if len(page_results) < params["per_page"]:
                break
            params["page"] += 1
            time.sleep(0.3)

    return results


def map_211_record(rec: dict, location_name: str, idx: int) -> Optional[dict]:
    """Map a 211 API record to the project schema."""
    org_name = rec.get("name") or rec.get("org_name", "")
    if not org_name:
        return None

    # Address
    addr = rec.get("address") or {}
    if isinstance(addr, str):
        address_text = addr
        city = location_name.split(",")[0].strip()
        state = "MI"
        zip_code = ""
    else:
        address_text = " ".join(filter(None, [
            addr.get("address_1"), addr.get("address_2"),
            addr.get("city"), addr.get("state_province"), addr.get("postal_code"),
        ]))
        city  = addr.get("city", location_name.split(",")[0].strip())
        state = addr.get("state_province", "MI")
        zip_code = addr.get("postal_code", "")

    # Coordinates
    lat = rec.get("latitude") or rec.get("lat")
    lon = rec.get("longitude") or rec.get("lon")

    # Phone
    phones = rec.get("phones") or rec.get("phone_numbers") or []
    phone = ""
    if phones:
        raw_phone = phones[0].get("phone") or phones[0].get("number") or ""
        m = PHONE_RE.search(raw_phone)
        phone = m.group(1) if m else raw_phone
    if not phone:
        m = PHONE_RE.search(rec.get("phone", ""))
        if m:
            phone = m.group(1)

    # Hours
    hours_raw = rec.get("hours") or rec.get("regular_schedules") or []
    if isinstance(hours_raw, str):
        hours_text = hours_raw
    elif isinstance(hours_raw, list) and hours_raw:
        hours_text = "; ".join(
            h.get("description") or h.get("opens_at", "") + "-" + h.get("closes_at", "")
            for h in hours_raw
            if isinstance(h, dict)
        )
    else:
        hours_text = ""

    # Service category
    taxonomies = rec.get("taxonomy_codes") or rec.get("categories") or []
    service_category = infer_category_from_taxonomy(taxonomies, rec.get("description", ""))

    # Eligibility
    eligibility_text = rec.get("eligibility") or rec.get("eligibility_notes") or ""

    city_slug = city.lower().replace(" ", "_")
    resource_id = f"mi_{city_slug}_211_{idx:04d}"

    return {
        "resource_id": resource_id,
        "org_name": org_name,
        "service_category": service_category,
        "description": rec.get("description", ""),
        "address": address_text,
        "city": city,
        "state": state,
        "zip": str(zip_code),
        "lat": lat,
        "lon": lon,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": eligibility_text,
        "phone": phone,
        "source_url": rec.get("url") or rec.get("source_url") or "",
        "source_type": "211_api",
        "last_verified": TODAY,
    }


# ---------------------------------------------------------------------------
# HUD API
# ---------------------------------------------------------------------------

def fetch_hud_resources(
    api_key: str,
    lat: float,
    lon: float,
    radius_miles: int,
) -> list:
    """
    Query the HUD Resource Locator API for housing-related resources.
    Returns raw API records.

    HUD API docs: https://www.huduser.gov/portal/dataset/apidescription.html

    The Resource Locator endpoint returns HUD-assisted housing and
    homeless/shelter programs registered with HUD.
    """
    base = "https://api.hud.gov/v1/resources/nearby"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "lat":    lat,
        "lon":    lon,
        "radius": radius_miles,
    }

    results = []
    page = 1

    while True:
        params["page"] = page
        try:
            resp = requests.get(base, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"    HUD API error: {e}")
            # Try alternate known endpoint path
            alt = "https://api.hud.gov/resources/v1/nearby"
            try:
                resp = requests.get(alt, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            except Exception:
                break

        data = resp.json()
        page_results = (
            data.get("resources")
            or data.get("results")
            or data.get("data")
            or []
        )
        results.extend(page_results)

        total = data.get("total") or data.get("count") or 0
        if not page_results or len(results) >= total:
            break
        page += 1
        time.sleep(0.3)

    return results


def map_hud_record(rec: dict, location_name: str, idx: int) -> Optional[dict]:
    """Map a HUD API record to the project schema."""
    org_name = (
        rec.get("name")
        or rec.get("organization_name")
        or rec.get("program_name")
        or ""
    )
    if not org_name:
        return None

    city = rec.get("city") or location_name.split(",")[0].strip()
    state = rec.get("state") or "MI"
    address_parts = filter(None, [
        rec.get("address") or rec.get("address1"),
        rec.get("address2"),
        city, state,
        str(rec.get("zip") or rec.get("zipcode") or ""),
    ])
    address_text = " ".join(address_parts)

    lat = rec.get("latitude") or rec.get("lat")
    lon = rec.get("longitude") or rec.get("lon")

    phone_raw = rec.get("phone") or rec.get("phone_number") or ""
    m = PHONE_RE.search(phone_raw)
    phone = m.group(1) if m else phone_raw

    # HUD resource types map to our service categories
    resource_type = (rec.get("resource_type") or rec.get("type") or "").lower()
    if any(k in resource_type for k in ("shelter", "homeless", "emergency")):
        service_category = ["shelter"]
    elif any(k in resource_type for k in ("housing", "rental", "hud")):
        service_category = ["housing_assistance"]
    else:
        service_category = ["housing_assistance"]

    city_slug = city.lower().replace(" ", "_")
    resource_id = f"mi_{city_slug}_hud_{idx:04d}"

    return {
        "resource_id": resource_id,
        "org_name": org_name,
        "service_category": service_category,
        "description": rec.get("description") or rec.get("summary") or "",
        "address": address_text,
        "city": city,
        "state": state,
        "zip": str(rec.get("zip") or rec.get("zipcode") or ""),
        "lat": lat,
        "lon": lon,
        "hours_text": rec.get("hours") or "",
        "hours_normalized": {},
        "eligibility_text": rec.get("eligibility") or rec.get("eligibility_requirements") or "",
        "phone": phone,
        "source_url": rec.get("url") or rec.get("website") or "",
        "source_type": "hud_api",
        "last_verified": TODAY,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def infer_category_from_taxonomy(codes: list, description: str = "") -> list:
    """Map 211 taxonomy codes to project service_category values."""
    cats = set()
    code_str = " ".join(str(c) for c in codes).upper()
    desc_lc = description.lower()

    if "BD-18" in code_str or "food" in desc_lc or "pantry" in desc_lc or "meal" in desc_lc:
        cats.add("food_pantry")
    if "BH-18" in code_str or "shelter" in desc_lc or "overnight" in desc_lc:
        cats.add("shelter")
    if "BH-30" in code_str or "housing" in desc_lc or "rental" in desc_lc:
        cats.add("housing_assistance")

    return sorted(cats) or ["shelter"]


def deduplicate(records: list) -> list:
    """Remove duplicate resource_ids, keeping first occurrence."""
    seen = {}
    for rec in records:
        rid = rec.get("resource_id")
        if rid and rid not in seen:
            seen[rid] = rec
    return list(seen.values())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch social service resources from 211 and HUD APIs."
    )
    parser.add_argument(
        "--source",
        choices=["211", "hud", "both"],
        default="both",
        help="Which API to query (default: both)",
    )
    parser.add_argument(
        "--output",
        default="../data/raw_resources_api.jsonl",
        help="Output JSONL file path",
    )
    args = parser.parse_args()

    all_records = []
    global_idx = 1

    # ── 211 ──────────────────────────────────────────────────────────────
    if args.source in ("211", "both"):
        if not API_211_KEY:
            print(
                "⚠  211 API key not set. Register at https://api.211.org/ "
                "then set API_211_KEY env var.\n   Skipping 211 source."
            )
        else:
            print("Fetching from 211 API...")
            for loc_name, lat, lon, radius in SEARCH_LOCATIONS:
                print(f"  {loc_name}")
                raw = fetch_211_resources(API_211_KEY, lat, lon, radius)
                print(f"    {len(raw)} raw records")
                for rec in raw:
                    mapped = map_211_record(rec, loc_name, global_idx)
                    if mapped:
                        all_records.append(mapped)
                        global_idx += 1
                time.sleep(0.5)

    # ── HUD ──────────────────────────────────────────────────────────────
    if args.source in ("hud", "both"):
        if not HUD_API_KEY:
            print(
                "⚠  HUD API key not set. Register at "
                "https://www.huduser.gov/portal/dataset/apidescription.html "
                "then set HUD_API_KEY env var.\n   Skipping HUD source."
            )
        else:
            print("Fetching from HUD API...")
            for loc_name, lat, lon, radius in SEARCH_LOCATIONS:
                print(f"  {loc_name}")
                raw = fetch_hud_resources(HUD_API_KEY, lat, lon, radius)
                print(f"    {len(raw)} raw records")
                for rec in raw:
                    mapped = map_hud_record(rec, loc_name, global_idx)
                    if mapped:
                        all_records.append(mapped)
                        global_idx += 1
                time.sleep(0.5)

    all_records = deduplicate(all_records)

    with open(args.output, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_records)} records → {args.output}")
    print("Next: add to merge_raw.py inputs, then run normalize_records.py")


if __name__ == "__main__":
    main()

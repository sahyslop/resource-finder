"""
Targeted scraper for foodpantries.org — Michigan cities.
Outputs raw_resources JSONL matching the project schema.

Usage:
    python scrape_foodpantries.py
    python scrape_foodpantries.py --output ../data/raw_resources_scraped.jsonl
    python scrape_foodpantries.py --cities ann_arbor ypsilanti
"""

import argparse
import json
import re
import time
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "ResourceFinder/1.0 (academic research project, University of Michigan; "
        "not for commercial use)"
    )
}
TODAY = date.today().isoformat()
GEOCODER = Nominatim(user_agent="resource_finder_umich_academic")

# Michigan cities to scrape — (url_slug, display_name)
MICHIGAN_CITIES = [
    ("ann_arbor", "Ann Arbor"),
    ("ypsilanti", "Ypsilanti"),
    ("detroit", "Detroit"),
    ("lansing", "Lansing"),
    ("flint", "Flint"),
    ("grand_rapids", "Grand Rapids"),
    ("kalamazoo", "Kalamazoo"),
    ("saginaw", "Saginaw"),
    ("pontiac", "Pontiac"),
    ("dearborn", "Dearborn"),
    ("sterling_heights", "Sterling Heights"),
    ("warren", "Warren"),
    ("muskegon", "Muskegon"),
    ("battle_creek", "Battle Creek"),
    ("jackson", "Jackson"),
]

PHONE_RE = re.compile(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')
ZIP_RE = re.compile(r'\b(\d{5})\b')
HOURS_RE = re.compile(
    r'\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|'
    r'saturday|sunday|hours|[0-9]{1,2}:[0-9]{2}\s*[ap]m|[0-9]{1,2}\s*[ap]m)\b',
    re.I,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch(url: str, delay: float = 1.5) -> BeautifulSoup:
    time.sleep(delay)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def geocode(address: str, city: str, retries: int = 2) -> tuple:
    query = f"{address}, {city}, MI" if address else f"{city}, MI"
    for attempt in range(retries):
        try:
            loc = GEOCODER.geocode(query, timeout=10)
            if loc:
                return loc.latitude, loc.longitude
        except (GeocoderTimedOut, GeocoderServiceError):
            pass
        time.sleep(1.5 * (attempt + 1))
    return None, None


def extract_phone(text: str) -> str:
    m = PHONE_RE.search(text)
    return m.group(1) if m else ""


def extract_zip(text: str) -> str:
    m = ZIP_RE.search(text)
    return m.group(1) if m else ""


def best_hours_line(soup: BeautifulSoup) -> str:
    """Return the most likely hours line from the page."""
    candidates = []
    for tag in soup.select("p, li, td, div"):
        text = tag.get_text(" ", strip=True)
        if HOURS_RE.search(text) and 10 < len(text) < 300:
            candidates.append(text)
    # Prefer shorter, denser matches
    candidates.sort(key=lambda t: (len(t), -len(HOURS_RE.findall(t))))
    return candidates[0] if candidates else ""


def best_address(soup: BeautifulSoup, city_name: str) -> str:
    """Return the most likely street address block."""
    city_lc = city_name.lower()
    for tag in soup.select("p, div, span, td"):
        text = tag.get_text(" ", strip=True)
        if ZIP_RE.search(text) and city_lc in text.lower() and len(text) < 200:
            return text
    return ""


def best_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for p in soup.select("p"):
        text = p.get_text(strip=True)
        if len(text) > 50:
            return text
    return ""


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------

def scrape_listing(url: str, city_name: str, idx: int, city_slug: str) -> Optional[dict]:
    print(f"      {url}")
    try:
        soup = fetch(url, delay=1.0)
    except Exception as e:
        print(f"        skip ({e})")
        return None

    h1 = soup.find("h1")
    org_name = h1.get_text(strip=True) if h1 else ""
    if not org_name:
        return None

    page_text = soup.get_text(" ", strip=True)
    address_text = best_address(soup, city_name)
    hours_text = best_hours_line(soup)
    description = best_description(soup)
    phone = extract_phone(page_text)
    zip_code = extract_zip(address_text)

    # Geocode — Nominatim requires ≥1 s between requests
    lat, lon = geocode(address_text, city_name)
    time.sleep(1.1)

    resource_id = f"mi_{city_slug.replace('-', '_')}_food_{idx:03d}"

    return {
        "resource_id": resource_id,
        "org_name": org_name,
        "service_category": ["food_pantry"],
        "description": description,
        "address": address_text,
        "city": city_name,
        "state": "MI",
        "zip": zip_code,
        "lat": lat,
        "lon": lon,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": "",
        "phone": phone,
        "source_url": url,
        "source_type": "directory",
        "last_verified": TODAY,
    }


def scrape_city(city_slug: str, city_name: str) -> list:
    city_url = f"https://www.foodpantries.org/ci/mi-{city_slug}"
    print(f"\n  {city_name}: {city_url}")

    try:
        soup = fetch(city_url)
    except Exception as e:
        print(f"    city page failed: {e}")
        return []

    # Collect unique listing paths like /li/...
    seen = set()
    listing_paths = []
    for a in soup.select("a[href^='/li/']"):
        href = a["href"]
        if href not in seen:
            seen.add(href)
            listing_paths.append(href)

    print(f"    found {len(listing_paths)} listings")

    records = []
    for i, path in enumerate(listing_paths, start=1):
        rec = scrape_listing(
            f"https://www.foodpantries.org{path}",
            city_name,
            i,
            city_slug,
        )
        if rec:
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape foodpantries.org for Michigan cities.")
    parser.add_argument(
        "--output",
        default="../data/raw_resources_scraped.jsonl",
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        metavar="SLUG",
        help="Limit to specific city slugs, e.g. ann_arbor ypsilanti",
    )
    args = parser.parse_args()

    cities = MICHIGAN_CITIES
    if args.cities:
        slug_set = set(args.cities)
        cities = [(s, n) for s, n in MICHIGAN_CITIES if s in slug_set]
        if not cities:
            print(f"No matching cities. Available slugs: {[s for s,_ in MICHIGAN_CITIES]}")
            return

    all_records = []
    for city_slug, city_name in cities:
        records = scrape_city(city_slug, city_name)
        all_records.extend(records)
        print(f"    collected {len(records)} records from {city_name}")

    with open(args.output, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nDone. Wrote {len(all_records)} records to {args.output}")
    print("Next: run normalize_records.py to produce normalized_resources.jsonl")


if __name__ == "__main__":
    main()

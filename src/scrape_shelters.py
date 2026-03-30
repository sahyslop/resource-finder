"""
Targeted scraper for shelterlistings.org — Michigan cities.
Covers emergency shelters and housing assistance resources.
Outputs raw_resources JSONL matching the project schema.

Usage:
    python scrape_shelters.py
    python scrape_shelters.py --output ../data/raw_resources_shelters.jsonl
    python scrape_shelters.py --max-cities 5
"""

import argparse
import json
import re
import time
from datetime import date
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STATE_URL = "https://www.shelterlistings.org/state/michigan/"
BASE_URL = "https://www.shelterlistings.org"

HEADERS = {
    "User-Agent": (
        "ResourceFinder/1.0 (academic research project, University of Michigan; "
        "not for commercial use)"
    )
}
TODAY = date.today().isoformat()
GEOCODER = Nominatim(user_agent="resource_finder_umich_academic")

PHONE_RE = re.compile(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')
ZIP_RE = re.compile(r'\b(\d{5})\b')
HOURS_RE = re.compile(
    r'\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|'
    r'saturday|sunday|hours|[0-9]{1,2}:[0-9]{2}\s*[ap]m|[0-9]{1,2}\s*[ap]m)\b',
    re.I,
)

# Keywords used to infer service_category
HOUSING_KEYWORDS = [
    "transitional housing", "housing assistance", "section 8", "rapid rehousing",
    "hud", "affordable housing", "rental assistance", "permanent supportive",
]
SHELTER_KEYWORDS = [
    "shelter", "overnight", "emergency", "bed", "beds", "night", "sleep",
    "homeless", "transitional",
]


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


def infer_service_category(text: str) -> list:
    t = text.lower()
    cats = []
    if any(k in t for k in HOUSING_KEYWORDS):
        cats.append("housing_assistance")
    if any(k in t for k in SHELTER_KEYWORDS):
        cats.append("shelter")
    return cats or ["shelter"]


def best_address(soup: BeautifulSoup, city_name: str) -> str:
    city_lc = city_name.lower()
    for tag in soup.select("p, div, span, td, li"):
        text = tag.get_text(" ", strip=True)
        if ZIP_RE.search(text) and city_lc in text.lower() and len(text) < 200:
            return text
    return ""


def best_hours_line(soup: BeautifulSoup) -> str:
    candidates = []
    for tag in soup.select("p, li, td, div"):
        text = tag.get_text(" ", strip=True)
        if HOURS_RE.search(text) and 10 < len(text) < 300:
            candidates.append(text)
    candidates.sort(key=lambda t: (len(t), -len(HOURS_RE.findall(t))))
    return candidates[0] if candidates else ""


def best_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for p in soup.select("p"):
        text = p.get_text(strip=True)
        if len(text) > 50:
            return text
    return ""


def extract_eligibility(soup: BeautifulSoup) -> str:
    """Look for eligibility / who-we-serve language."""
    keywords = ("eligib", "who we serve", "requirements", "must be", "adults only",
                 "families", "veterans", "18+", "women", "men only")
    for tag in soup.select("p, li, td"):
        text = tag.get_text(strip=True)
        if any(k in text.lower() for k in keywords) and len(text) < 300:
            return text
    return ""


# ---------------------------------------------------------------------------
# Discovery: state page → city URLs → listing URLs
# ---------------------------------------------------------------------------

def get_city_urls() -> list:
    """Scrape the Michigan state page to discover city page URLs."""
    print(f"Discovering city pages from {STATE_URL}")
    try:
        soup = fetch(STATE_URL)
    except Exception as e:
        print(f"  Failed to fetch state page: {e}")
        return []

    city_urls = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a["href"]
        # City pages are under /city/ and should contain 'mi' or 'michigan'
        if "/city/" in href and href not in seen:
            full = urljoin(BASE_URL, href)
            city_urls.append(full)
            seen.add(href)

    print(f"  Found {len(city_urls)} city pages")
    return city_urls


def get_listing_urls(city_url: str) -> list:
    """Return all shelter listing URLs found on a city page."""
    try:
        soup = fetch(city_url)
    except Exception as e:
        print(f"    city page failed: {e}")
        return []

    listing_urls = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/shelter/" in href and href not in seen:
            listing_urls.append(urljoin(BASE_URL, href))
            seen.add(href)

    return listing_urls


# ---------------------------------------------------------------------------
# Scraping a single listing page
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
    eligibility_text = extract_eligibility(soup)
    phone = ""
    m = PHONE_RE.search(page_text)
    if m:
        phone = m.group(1)
    zip_code = ""
    mz = ZIP_RE.search(address_text)
    if mz:
        zip_code = mz.group(1)

    service_category = infer_service_category(page_text)

    lat, lon = geocode(address_text, city_name)
    time.sleep(1.1)  # Nominatim rate limit

    resource_id = f"mi_{city_slug}_shelter_{idx:03d}"

    return {
        "resource_id": resource_id,
        "org_name": org_name,
        "service_category": service_category,
        "description": description,
        "address": address_text,
        "city": city_name,
        "state": "MI",
        "zip": zip_code,
        "lat": lat,
        "lon": lon,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": eligibility_text,
        "phone": phone,
        "source_url": url,
        "source_type": "directory",
        "last_verified": TODAY,
    }


# ---------------------------------------------------------------------------
# City-level scrape
# ---------------------------------------------------------------------------

def city_name_from_url(url: str) -> tuple:
    """Extract a display name and slug from a city URL like /city/ann-arbor-mi/."""
    segment = url.rstrip("/").split("/")[-1]
    # Strip trailing state code, e.g. "ann-arbor-mi" → "ann-arbor"
    slug = re.sub(r'-mi$', '', segment)
    display = slug.replace("-", " ").title()
    return display, slug.replace("-", "_")


def scrape_city(city_url: str) -> list:
    city_name, city_slug = city_name_from_url(city_url)
    print(f"\n  {city_name}: {city_url}")

    listing_urls = get_listing_urls(city_url)
    print(f"    found {len(listing_urls)} listings")

    records = []
    for i, lurl in enumerate(listing_urls, start=1):
        rec = scrape_listing(lurl, city_name, i, city_slug)
        if rec:
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape shelterlistings.org for Michigan shelter and housing resources."
    )
    parser.add_argument(
        "--output",
        default="../data/raw_resources_shelters.jsonl",
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--max-cities",
        type=int,
        default=None,
        help="Limit number of cities scraped (useful for testing)",
    )
    args = parser.parse_args()

    city_urls = get_city_urls()
    if args.max_cities:
        city_urls = city_urls[: args.max_cities]

    all_records = []
    for city_url in city_urls:
        records = scrape_city(city_url)
        all_records.extend(records)
        city_name, _ = city_name_from_url(city_url)
        print(f"    collected {len(records)} records from {city_name}")

    with open(args.output, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nDone. Wrote {len(all_records)} records to {args.output}")
    print("Next: merge with food pantry data, then run normalize_records.py")


if __name__ == "__main__":
    main()

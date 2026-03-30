"""
Collect Michigan social service resources from three sources:
  - foodpantries.org  (food pantries, by city)
  - shelterlistings.org  (emergency shelters and housing assistance)
  - OpenStreetMap via Overpass API  (social facilities and food banks)

Each source is geocoded right after collection, then written to its own JSONL file.

Usage:
    python collect_data.py                           # all three sources
    python collect_data.py --sources food shelters   # subset of sources
    python collect_data.py --sources food --cities ann_arbor ypsilanti
    python collect_data.py --sources shelters --max-shelter-cities 5
    python collect_data.py --skip-geocode            # skip geocoding step
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
# Shared utilities
# ---------------------------------------------------------------------------

TODAY = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "ResourceFinder/1.0 (academic research project, University of Michigan; "
        "not for commercial use)"
    )
}

PHONE_RE = re.compile(r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')
ZIP_RE = re.compile(r'\b(\d{5})\b')
HOURS_RE = re.compile(
    r'\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|'
    r'saturday|sunday|hours|[0-9]{1,2}:[0-9]{2}\s*[ap]m|[0-9]{1,2}\s*[ap]m)\b',
    re.I,
)

GEOCODER = Nominatim(user_agent="resource_finder_umich_academic")


def fetch(url: str, delay: float = 1.5) -> BeautifulSoup:
    time.sleep(delay)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def geocode_record(city: str, state: str, zip_code: str, address: str = "", retries: int = 2) -> tuple:
    """
    Try to geocode using address first, then zip, then city+state.
    Returns (lat, lon) or (None, None) if all attempts fail.
    """
    queries = []
    if address and zip_code:
        queries.append(f"{address}, {city}, {state}")
    if zip_code:
        queries.append(f"{zip_code}, {state}")
    queries.append(f"{city}, {state}")

    for query in queries:
        if not query.strip(", "):
            continue
        for attempt in range(retries):
            try:
                loc = GEOCODER.geocode(query, timeout=10)
                if loc:
                    return loc.latitude, loc.longitude
            except (GeocoderTimedOut, GeocoderServiceError):
                pass
            time.sleep(1.5 * (attempt + 1))
    return None, None


# ---------------------------------------------------------------------------
# Food pantry helpers (foodpantries.org)
# ---------------------------------------------------------------------------

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

ELIGIBILITY_KEYWORDS = (
    "requirement", "eligib", "open to", "documentation required",
    "must show", "id required", "photo id", "referral", "proof of",
    "appointment required", "residents of", "income",
)


def _food_best_address(soup: BeautifulSoup, city_name: str) -> str:
    """
    foodpantries.org puts the address in a <p> that starts with
    'View Website and Full Address'. The first such paragraph is the
    current listing; subsequent ones are nearby listings.
    """
    for tag in soup.select("p"):
        text = tag.get_text(" ", strip=True)
        if text.startswith("View Website and Full Address") and ZIP_RE.search(text):
            addr = re.sub(r"^View Website and Full Address", "", text).strip()
            addr = re.sub(r"Food Pantry Location:.*$", "", addr).strip()
            return addr
    # Fallback: any paragraph with a zip and the city name
    city_lc = city_name.lower()
    for tag in soup.select("p, div, span, td"):
        text = tag.get_text(" ", strip=True)
        if ZIP_RE.search(text) and city_lc in text.lower() and len(text) < 200:
            return text
    return ""


def _food_best_hours(soup: BeautifulSoup) -> str:
    """foodpantries.org puts hours in a <p> starting with 'Hours:'."""
    for tag in soup.select("p"):
        text = tag.get_text(" ", strip=True)
        if text.startswith("Hours:") and len(text) < 400:
            return text
    candidates = []
    for tag in soup.select("p, li, td"):
        text = tag.get_text(" ", strip=True)
        if HOURS_RE.search(text) and 10 < len(text) < 300:
            candidates.append(text)
    candidates.sort(key=lambda t: (len(t), -len(HOURS_RE.findall(t))))
    return candidates[0] if candidates else ""


def _food_best_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for p in soup.select("p"):
        text = p.get_text(strip=True)
        if len(text) > 50 and not text.startswith("View Website") and not text.startswith("Hours:"):
            return text
    return ""


def _food_extract_eligibility(soup: BeautifulSoup, hours_text: str) -> str:
    """
    Extract eligibility / requirements text from the listing page.

    Priority:
      1. A paragraph containing explicit eligibility keywords.
      2. The 'Requirements:' section split out of the hours paragraph.
      3. If no restrictions are found at all, return 'Open to all'
         so normalize_records.py doesn't falsely infer family_friendly=False.
    """
    for tag in soup.select("p"):
        text = tag.get_text(" ", strip=True)
        if any(k in text.lower() for k in ELIGIBILITY_KEYWORDS) and len(text) < 500:
            if not text.startswith("Hours:"):
                return text

    if "Requirements:" in hours_text:
        return hours_text.split("Requirements:", 1)[1].strip()
    if "Documentation required:" in hours_text:
        return hours_text.split("Documentation required:", 1)[1].strip()

    return "Open to all"


def _scrape_food_listing(url: str, city_name: str, idx: int, city_slug: str) -> Optional[dict]:
    print(f"      {url}")
    try:
        soup = fetch(url, delay=1.0)
    except Exception as e:
        print(f"        skip ({e})")
        return None

    # Org name is in h2: "Pantry Details, hours, photos, information: NAME"
    h2 = soup.find("h2")
    raw_h2 = h2.get_text(strip=True) if h2 else ""
    org_name = re.split(r":\s+", raw_h2, maxsplit=1)[-1].strip() if raw_h2 else ""
    if not org_name:
        return None

    page_text = soup.get_text(" ", strip=True)
    address_text = _food_best_address(soup, city_name)
    hours_text = _food_best_hours(soup)
    description = _food_best_description(soup)
    eligibility_text = _food_extract_eligibility(soup, hours_text)
    m_phone = PHONE_RE.search(page_text)
    phone = m_phone.group(1) if m_phone else ""
    m_zip = ZIP_RE.search(address_text)
    zip_code = m_zip.group(1) if m_zip else ""

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
        "lat": None,
        "lon": None,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": eligibility_text,
        "phone": phone,
        "source_url": url,
        "source_type": "directory",
        "last_verified": TODAY,
    }


def _scrape_food_city(city_slug: str, city_name: str) -> list:
    city_url = f"https://www.foodpantries.org/ci/mi-{city_slug}"
    print(f"\n  {city_name}: {city_url}")

    try:
        soup = fetch(city_url)
    except Exception as e:
        print(f"    city page failed: {e}")
        return []

    # Links are full URLs like https://www.foodpantries.org/li/slug
    seen = set()
    listing_urls = []
    for a in soup.select("a[href*='/li/']"):
        href = a["href"]
        if "/li/" in href and href not in seen:
            seen.add(href)
            listing_urls.append(href)

    print(f"    found {len(listing_urls)} listings")

    records = []
    for i, url in enumerate(listing_urls, start=1):
        rec = _scrape_food_listing(url, city_name, i, city_slug)
        if rec:
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Shelter helpers (shelterlistings.org)
# ---------------------------------------------------------------------------

SHELTER_STATE_URL = "https://www.shelterlistings.org/state/michigan.html"
SHELTER_BASE_URL = "https://www.shelterlistings.org"

HOUSING_KEYWORDS = [
    "transitional housing", "housing assistance", "section 8", "rapid rehousing",
    "hud", "affordable housing", "rental assistance", "permanent supportive",
]
SHELTER_KEYWORDS = [
    "shelter", "overnight", "emergency", "bed", "beds", "night", "sleep",
    "homeless", "transitional",
]


def _shelter_infer_category(text: str) -> list:
    t = text.lower()
    cats = []
    if any(k in t for k in HOUSING_KEYWORDS):
        cats.append("housing_assistance")
    if any(k in t for k in SHELTER_KEYWORDS):
        cats.append("shelter")
    return cats or ["shelter"]


def _shelter_best_address(soup: BeautifulSoup, city_name: str) -> str:
    city_lc = city_name.lower()
    for tag in soup.select("p, div, span, td, li"):
        text = tag.get_text(" ", strip=True)
        if ZIP_RE.search(text) and city_lc in text.lower() and len(text) < 200:
            return text
    return ""


def _shelter_best_hours(soup: BeautifulSoup) -> str:
    candidates = []
    for tag in soup.select("p, li, td, div"):
        text = tag.get_text(" ", strip=True)
        if HOURS_RE.search(text) and 10 < len(text) < 300:
            candidates.append(text)
    candidates.sort(key=lambda t: (len(t), -len(HOURS_RE.findall(t))))
    return candidates[0] if candidates else ""


def _shelter_best_description(soup: BeautifulSoup) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for p in soup.select("p"):
        text = p.get_text(strip=True)
        if len(text) > 50:
            return text
    return ""


def _shelter_extract_eligibility(soup: BeautifulSoup) -> str:
    keywords = ("eligib", "who we serve", "requirements", "must be", "adults only",
                 "families", "veterans", "18+", "women", "men only")
    for tag in soup.select("p, li, td"):
        text = tag.get_text(strip=True)
        if any(k in text.lower() for k in keywords) and len(text) < 300:
            return text
    return ""


def _shelter_city_name_from_url(url: str) -> tuple:
    """Extract display name and slug from a city URL like /city/ann_arbor-mi.html."""
    segment = url.rstrip("/").split("/")[-1]
    segment = re.sub(r'\.html$', '', segment)   # strip .html
    slug = re.sub(r'-mi$', '', segment)          # strip trailing -mi
    display = slug.replace("_", " ").replace("-", " ").title()
    return display, slug


def _shelter_get_city_urls() -> list:
    print(f"Discovering city pages from {SHELTER_STATE_URL}")
    try:
        soup = fetch(SHELTER_STATE_URL)
    except Exception as e:
        print(f"  Failed to fetch state page: {e}")
        return []

    city_urls = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/city/" in href and "-mi" in href and href not in seen:
            full = urljoin(SHELTER_BASE_URL, href)
            city_urls.append(full)
            seen.add(href)

    print(f"  Found {len(city_urls)} city pages")
    return city_urls


def _shelter_get_listing_urls(city_url: str) -> list:
    try:
        soup = fetch(city_url)
    except Exception as e:
        print(f"    city page failed: {e}")
        return []

    listing_urls = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/details/" in href and href not in seen:
            listing_urls.append(urljoin(SHELTER_BASE_URL, href))
            seen.add(href)

    return listing_urls


def _scrape_shelter_listing(url: str, city_name: str, idx: int, city_slug: str) -> Optional[dict]:
    print(f"      {url}")
    try:
        soup = fetch(url, delay=1.0)
    except Exception as e:
        print(f"        skip ({e})")
        return None

    # shelterlistings.org uses h2 for the org name
    h2 = soup.find("h2")
    org_name = h2.get_text(strip=True) if h2 else ""
    if not org_name:
        return None

    page_text = soup.get_text(" ", strip=True)
    address_text = _shelter_best_address(soup, city_name)
    hours_text = _shelter_best_hours(soup)
    description = _shelter_best_description(soup)
    eligibility_text = _shelter_extract_eligibility(soup)

    m = PHONE_RE.search(page_text)
    phone = m.group(1) if m else ""

    mz = ZIP_RE.search(address_text)
    zip_code = mz.group(1) if mz else ""

    service_category = _shelter_infer_category(page_text)

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
        "lat": None,
        "lon": None,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": eligibility_text,
        "phone": phone,
        "source_url": url,
        "source_type": "directory",
        "last_verified": TODAY,
    }


def _scrape_shelter_city(city_url: str) -> list:
    city_name, city_slug = _shelter_city_name_from_url(city_url)
    print(f"\n  {city_name}: {city_url}")

    listing_urls = _shelter_get_listing_urls(city_url)
    print(f"    found {len(listing_urls)} listings")

    records = []
    for i, lurl in enumerate(listing_urls, start=1):
        rec = _scrape_shelter_listing(lurl, city_name, i, city_slug)
        if rec:
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# OSM helpers (OpenStreetMap via Overpass API)
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:60];
area["name"="Michigan"]["admin_level"="4"]->.mi;
(
  node["amenity"="social_facility"](area.mi);
  node["amenity"="food_bank"](area.mi);
  way["amenity"="social_facility"](area.mi);
  way["amenity"="food_bank"](area.mi);
);
out center body;
"""

OSM_CATEGORY_MAP = {
    "food_bank":          ["food_pantry"],
    "soup_kitchen":       ["food_pantry"],
    "shelter":            ["shelter"],
    "homeless":           ["shelter"],
    "housing":            ["housing_assistance"],
    "community_centre":   ["shelter"],
    "outreach":           ["shelter"],
    "day_centre":         ["shelter"],
    "advice":             ["housing_assistance"],
}

OSM_SKIP_TYPES = {
    "nursing_home", "assisted_living", "group_home", "orphanage",
    "day_care", "childrens_centre", "treatment", "hospice",
    "ambulatory_care", "senior_center", "social_club", "clubhouse",
    "equine_assisted_centre",
}


def _osm_infer_category(tags: dict) -> list:
    facility_type = tags.get("social_facility", "")
    amenity = tags.get("amenity", "")

    if facility_type in OSM_SKIP_TYPES:
        return []

    if facility_type in OSM_CATEGORY_MAP:
        return OSM_CATEGORY_MAP[facility_type]

    name = (tags.get("name", "") + " " + tags.get("description", "")).lower()
    cats = []
    if any(k in name for k in ("food", "pantry", "meal", "soup", "hunger", "grocery")):
        cats.append("food_pantry")
    if any(k in name for k in ("shelter", "homeless", "overnight", "emergency")):
        cats.append("shelter")
    if any(k in name for k in ("housing", "rent", "voucher", "section 8")):
        cats.append("housing_assistance")

    if amenity == "food_bank" and not cats:
        cats.append("food_pantry")

    return cats or ["shelter"]


def _osm_map_element(el: dict, idx: int) -> Optional[dict]:
    tags = el.get("tags", {})
    org_name = tags.get("name", "").strip()
    if not org_name:
        return None

    # For ways, coordinates come from the "center" field
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")

    service_category = _osm_infer_category(tags)
    if not service_category:
        return None

    house  = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    city   = tags.get("addr:city", "")
    state  = tags.get("addr:state", "MI")
    zip_   = tags.get("addr:postcode", "")

    address = " ".join(filter(None, [house, street, city, state, zip_]))

    phone = tags.get("phone", tags.get("contact:phone", ""))
    phone = phone.replace("+1-", "").replace("+1 ", "").strip()

    hours_text = tags.get("opening_hours", "")
    description = tags.get("description", "")
    eligibility = tags.get("social_facility:for", "")
    source_url = tags.get("website", tags.get("contact:website", ""))

    city_slug = city.lower().replace(" ", "_") if city else "mi"
    resource_id = f"mi_{city_slug}_osm_{idx:04d}"

    return {
        "resource_id": resource_id,
        "org_name": org_name,
        "service_category": service_category,
        "description": description,
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_,
        "lat": lat,
        "lon": lon,
        "hours_text": hours_text,
        "hours_normalized": {},
        "eligibility_text": eligibility,
        "phone": phone,
        "source_url": source_url,
        "source_type": "osm",
        "last_verified": TODAY,
    }


# ---------------------------------------------------------------------------
# Collection functions (public API)
# ---------------------------------------------------------------------------

def collect_food_pantries(city_slugs: Optional[list] = None) -> list:
    """Scrape foodpantries.org for Michigan cities. Returns list of raw records."""
    cities = MICHIGAN_CITIES
    if city_slugs:
        slug_set = set(city_slugs)
        cities = [(s, n) for s, n in MICHIGAN_CITIES if s in slug_set]
        if not cities:
            print(f"No matching cities. Available slugs: {[s for s, _ in MICHIGAN_CITIES]}")
            return []

    print(f"\n=== Food Pantries (foodpantries.org) ===")
    all_records = []
    for city_slug, city_name in cities:
        records = _scrape_food_city(city_slug, city_name)
        all_records.extend(records)
        print(f"    collected {len(records)} records from {city_name}")

    return all_records


def collect_shelters(max_cities: Optional[int] = None) -> list:
    """Scrape shelterlistings.org for Michigan shelters. Returns list of raw records."""
    print(f"\n=== Shelters (shelterlistings.org) ===")
    city_urls = _shelter_get_city_urls()
    if max_cities:
        city_urls = city_urls[:max_cities]

    all_records = []
    for city_url in city_urls:
        records = _scrape_shelter_city(city_url)
        all_records.extend(records)
        city_name, _ = _shelter_city_name_from_url(city_url)
        print(f"    collected {len(records)} records from {city_name}")

    return all_records


def collect_osm() -> list:
    """Fetch Michigan social service resources from OpenStreetMap. Returns list of raw records."""
    print(f"\n=== OpenStreetMap ===")
    print("Querying Overpass API...")
    resp = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, timeout=90)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    print(f"  {len(elements)} raw elements returned")

    records = []
    for idx, el in enumerate(elements, start=1):
        rec = _osm_map_element(el, idx)
        if rec:
            records.append(rec)

    skipped = len(elements) - len(records)
    print(f"  {len(records)} records kept ({skipped} skipped — unnamed or irrelevant type)")
    return records


# ---------------------------------------------------------------------------
# Geocoding pass
# ---------------------------------------------------------------------------

def geocode_missing(records: list) -> list:
    """
    Fill in lat/lon for any records where it is None.
    Modifies records in place and returns them.
    """
    missing = [r for r in records if r.get("lat") is None or r.get("lon") is None]
    print(f"  Geocoding: {len(missing)}/{len(records)} records missing coordinates")

    updated = 0
    for rec in records:
        if rec.get("lat") is not None and rec.get("lon") is not None:
            continue

        city  = rec.get("city", "")
        state = rec.get("state", "MI")
        zip_  = rec.get("zip", "")

        if not zip_:
            m = ZIP_RE.search(rec.get("address", ""))
            if m:
                zip_ = m.group(1)

        lat, lon = geocode_record(city, state, zip_)
        time.sleep(1.1)  # Nominatim rate limit

        if lat is not None:
            rec["lat"] = lat
            rec["lon"] = lon
            updated += 1
            print(f"    [{updated}] {rec.get('org_name', '?')} -> {lat:.4f}, {lon:.4f}")
        else:
            print(f"    [skip] {rec.get('org_name', '?')} ({city}, {state} {zip_})")

    print(f"  Geocoded {updated}/{len(missing)} missing records")
    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Collect Michigan social service resources from web sources and OSM."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["food", "shelters", "osm", "geocode"],
        default=["food", "shelters", "osm"],
        help="Which sources to collect (default: all three). Use 'geocode' to fill in "
             "missing coordinates in existing raw_*.jsonl files without re-scraping.",
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        metavar="SLUG",
        help="Limit food pantry collection to specific city slugs (e.g. ann_arbor ypsilanti)",
    )
    parser.add_argument(
        "--max-shelter-cities",
        type=int,
        default=None,
        metavar="N",
        help="Limit shelter collection to first N cities (useful for testing)",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip the geocoding step",
    )
    args = parser.parse_args()

    from pathlib import Path
    DATA_DIR = Path(__file__).parent.parent / "data"

    sources = set(args.sources)

    if "food" in sources:
        food_records = collect_food_pantries(city_slugs=args.cities)
        if not args.skip_geocode:
            food_records = geocode_missing(food_records)
        out = "../data/raw_food.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for rec in food_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(food_records)} food pantry records -> {out}")

    if "shelters" in sources:
        shelter_records = collect_shelters(max_cities=args.max_shelter_cities)
        if not args.skip_geocode:
            shelter_records = geocode_missing(shelter_records)
        out = "../data/raw_shelters.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for rec in shelter_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(shelter_records)} shelter records -> {out}")

    if "osm" in sources:
        osm_records = collect_osm()
        if not args.skip_geocode:
            osm_records = geocode_missing(osm_records)
        out = "../data/raw_osm.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for rec in osm_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(osm_records)} OSM records -> {out}")

    if "geocode" in sources:
        raw_files = sorted(DATA_DIR.glob("raw_*.jsonl"))
        print(f"\n=== Geocoding existing raw files ===")
        for path in raw_files:
            with open(path, encoding="utf-8") as f:
                records = [json.loads(l) for l in f if l.strip()]
            missing = sum(1 for r in records if r.get("lat") is None)
            if missing == 0:
                print(f"  {path.name}: all {len(records)} records already geocoded, skipping")
                continue
            print(f"  {path.name}: {missing}/{len(records)} need geocoding")
            records = geocode_missing(records)
            with open(path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  Updated {path.name}")

    print("\nDone. Run build_index.py to merge, normalize, and build the search index.")


if __name__ == "__main__":
    main()

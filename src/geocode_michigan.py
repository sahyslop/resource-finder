"""
Michigan-only address geocoding.

Primary: Photon (Komoot) — OpenStreetMap-based, map-style autocomplete; no API key.
https://github.com/komoot/photon

Fallback: Nominatim — used when Photon returns nothing; respect usage policy.
https://operations.osmfoundation.org/policies/nominatim/

Optional: Google Places Autocomplete — set RESOURCE_FINDER_GOOGLE_PLACES_API_KEY for
Google-style predictions (Michigan-only via components filter).
"""

from __future__ import annotations

import os
from typing import Any

import requests

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
PHOTON_API = "https://photon.komoot.io/api/"
PHOTON_REVERSE = "https://photon.komoot.io/reverse"
GOOGLE_AUTOCOMPLETE = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
GOOGLE_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"

# Rough Michigan viewport for Photon bbox bias (minLon,minLat,maxLon,maxLat).
# Results are still filtered by state == Michigan so nearby states in the box are dropped.
_MI_BBOX = "-90.5,41.7,-82.0,48.5"

# Required by Nominatim; override in production with your contact URL or email.
_DEFAULT_UA = "ResourceFinder/1.0 (local development; Michigan resource search)"


def _headers() -> dict[str, str]:
    ua = os.environ.get("RESOURCE_FINDER_NOMINATIM_USER_AGENT", _DEFAULT_UA).strip()
    return {"User-Agent": ua or _DEFAULT_UA}


def _state_is_michigan(addr: dict[str, Any]) -> bool:
    if not addr:
        return False
    state = (addr.get("state") or "").strip().lower()
    if state in ("michigan", "mi"):
        return True
    code = (addr.get("state_code") or "").strip().upper()
    if code == "MI":
        return True
    iso = (addr.get("ISO3166-2-lvl4") or "").upper()
    if iso == "US-MI":
        return True
    return False


def _photon_props_is_michigan(props: dict[str, Any]) -> bool:
    if (props.get("countrycode") or "").upper() not in ("US", ""):
        return False
    state = (props.get("state") or "").strip().lower()
    return state == "michigan"


def _michigan_search_query(q: str) -> str:
    q = (q or "").strip()
    if len(q) < 3:
        return q
    low = q.lower()
    if "michigan" in low:
        return q
    if ", mi," in low or low.endswith(", mi") or low.endswith(" mi"):
        return q
    if low.endswith(",mi"):
        return q
    return f"{q}, Michigan, USA"


def _item_is_michigan(item: dict[str, Any]) -> bool:
    addr = item.get("address") or {}
    return _state_is_michigan(addr)


def _format_nominatim_label(item: dict[str, Any]) -> str:
    return (item.get("display_name") or "").strip()


def _format_photon_label(props: dict[str, Any]) -> str:
    """Single-line label similar to map apps: street / place + city, MI + ZIP."""
    hn = (props.get("housenumber") or "").strip()
    street = (props.get("street") or "").strip()
    name = (props.get("name") or "").strip()
    locality = (
        props.get("city")
        or props.get("town")
        or props.get("village")
        or props.get("municipality")
        or ""
    )
    locality = str(locality).strip()
    state = (props.get("state") or "").strip()
    pc = (props.get("postcode") or "").strip()
    county = (props.get("county") or "").strip()

    line1 = ""
    if hn and street:
        line1 = f"{hn} {street}"
    elif street:
        line1 = street
    elif name:
        line1 = name

    tail_parts: list[str] = []
    if locality:
        tail_parts.append(locality)
    if state:
        tail_parts.append(state)
    if pc:
        tail_parts.append(pc)

    if line1 and tail_parts:
        return f"{line1}, {', '.join(tail_parts)}"
    if line1 and county and state:
        return f"{line1}, {county}, {state}"
    if line1:
        return line1
    if name and locality:
        return f"{name}, {locality}, {state}" if state else f"{name}, {locality}"
    return name or ""


def nominatim_search(q: str, *, limit: int = 10) -> list[dict[str, Any]]:
    q = _michigan_search_query(q)
    params = {
        "q": q,
        "format": "json",
        "addressdetails": 1,
        "limit": limit,
        "countrycodes": "us",
    }
    r = requests.get(
        NOMINATIM_SEARCH,
        params=params,
        headers=_headers(),
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def photon_suggest_michigan(q: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Forward search via Photon; bbox + state filter → Michigan-only suggestions."""
    q = (q or "").strip()
    if len(q) < 3:
        return []
    params = {
        "q": q,
        "limit": max(limit * 3, 15),
        "bbox": _MI_BBOX,
        "lang": "en",
    }
    r = requests.get(
        PHOTON_API,
        params=params,
        headers=_headers(),
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for feat in features:
        props = feat.get("properties") or {}
        if not _photon_props_is_michigan(props):
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        label = _format_photon_label(props)
        if not label:
            continue
        key = (f"{lat:.5f}", f"{lon:.5f}")
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "lat": lat, "lon": lon, "source": "photon"})
        if len(out) >= limit:
            break
    return out


def google_places_suggest_michigan(q: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """
    Google Places Autocomplete — Michigan administrative area only.
    Returns label + place_id; lat/lon require a follow-up details call.
    """
    key = os.environ.get("RESOURCE_FINDER_GOOGLE_PLACES_API_KEY", "").strip()
    if not key:
        return []
    q = (q or "").strip()
    if len(q) < 3:
        return []
    params = {
        "input": q,
        "types": "address",
        "components": "country:us|administrative_area:MI",
        "key": key,
    }
    r = requests.get(GOOGLE_AUTOCOMPLETE, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        return []
    out: list[dict[str, Any]] = []
    for p in (data.get("predictions") or [])[:limit]:
        desc = (p.get("description") or "").strip()
        pid = p.get("place_id")
        if not desc or not pid:
            continue
        out.append(
            {
                "label": desc,
                "place_id": pid,
                "source": "google",
            }
        )
    return out


def google_place_details(place_id: str) -> dict[str, Any] | None:
    """Resolve place_id to lat/lon + formatted address (Michigan-only key)."""
    key = os.environ.get("RESOURCE_FINDER_GOOGLE_PLACES_API_KEY", "").strip()
    if not key or not place_id:
        return None
    params = {
        "place_id": place_id,
        "fields": "geometry,formatted_address,address_components",
        "key": key,
    }
    r = requests.get(GOOGLE_DETAILS, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        return None
    res = data.get("result") or {}
    loc = (res.get("geometry") or {}).get("location") or {}
    try:
        lat = float(loc["lat"])
        lon = float(loc["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    label = (res.get("formatted_address") or "").strip()
    if not label:
        return None
    # Confirm MI in address components
    for comp in res.get("address_components") or []:
        types = comp.get("types") or []
        if "administrative_area_level_1" in types:
            short = (comp.get("short_name") or "").upper()
            long = (comp.get("long_name") or "").lower()
            if short == "MI" or long == "michigan":
                return {"lat": lat, "lon": lon, "label": label, "source": "google"}
    return None


def suggest_michigan(q: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """
    Map-style suggestions: Google (if API key set), else Photon, else Nominatim.
    """
    q = (q or "").strip()
    if len(q) < 3:
        return []

    if os.environ.get("RESOURCE_FINDER_GOOGLE_PLACES_API_KEY", "").strip():
        g = google_places_suggest_michigan(q, limit=limit)
        if g:
            return g

    raw = photon_suggest_michigan(q, limit=limit)
    if raw:
        return raw

    raw_n = nominatim_search(q, limit=limit * 3)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_n:
        if not _item_is_michigan(item):
            continue
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = _format_nominatim_label(item)
        if not label:
            continue
        key = (f"{lat:.5f}", f"{lon:.5f}")
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "lat": lat, "lon": lon, "source": "nominatim"})
        if len(out) >= limit:
            break
    return out


def resolve_first_michigan(q: str) -> dict[str, Any] | None:
    rows = suggest_michigan(q, limit=1)
    if not rows:
        return None
    row = rows[0]
    if row.get("place_id"):
        return google_place_details(row["place_id"])
    return row


def reverse_photon_michigan(lat: float, lon: float) -> dict[str, Any] | None:
    r = requests.get(
        PHOTON_REVERSE,
        params={"lat": lat, "lon": lon, "lang": "en"},
        headers=_headers(),
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") if isinstance(data, dict) else None
    if not feats:
        return None
    feat = feats[0]
    props = feat.get("properties") or {}
    if not _photon_props_is_michigan(props):
        return None
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    try:
        flon, flat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    label = _format_photon_label(props)
    if not label:
        return None
    return {"lat": flat, "lon": flon, "label": label}


def reverse_nominatim_michigan(lat: float, lon: float) -> dict[str, Any] | None:
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
    }
    r = requests.get(
        NOMINATIM_REVERSE,
        params=params,
        headers=_headers(),
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or "lat" not in data:
        return None
    if not _item_is_michigan(data):
        return None
    try:
        flat = float(data["lat"])
        flon = float(data["lon"])
    except (TypeError, ValueError):
        return None
    label = _format_nominatim_label(data)
    if not label:
        return None
    return {"lat": flat, "lon": flon, "label": label}


def reverse_michigan(lat: float, lon: float) -> dict[str, Any] | None:
    """Reverse-geocode; Photon first, then Nominatim."""
    row = reverse_photon_michigan(lat, lon)
    if row:
        return row
    return reverse_nominatim_michigan(lat, lon)

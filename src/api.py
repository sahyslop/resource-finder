"""
Flask API for the Local Resource Finder. Loads the hybrid index once at startup.

Run from repo root:
    python src/api.py

Or from src/:
    cd src && python api.py

CORS: RESOURCE_FINDER_CORS_ORIGINS (comma-separated, default *). Tighten for production.
"""

from __future__ import annotations

import os
import warnings

from flask import Flask, jsonify, request
from flask_cors import CORS

from search import (
    DEFAULT_LAT,
    DEFAULT_LON,
    default_data_path,
    load_search_index,
    run_search_with_index,
)

import requests

from geocode_michigan import (
    google_place_details,
    resolve_first_michigan,
    reverse_michigan,
    suggest_michigan,
)

warnings.filterwarnings("ignore")

MAX_TOP = 20
# Optional hard cap on "within X miles" (client-supplied); avoids abuse.
MAX_MILES_CAP = 250.0

_CONSTRAINT_KEYS = frozenset(
    {"open_now", "near_me", "family_friendly", "senior_only", "veterans_only"}
)

_data_path = os.environ.get("RESOURCE_FINDER_DATA", default_data_path())

print("Loading search index (this may take a minute)...", flush=True)
_docs, _bm25, _model, _doc_embeddings = load_search_index(
    _data_path,
    quiet_embeddings=True,
)
print(f"Index ready: {len(_docs)} resources.", flush=True)
print(
    "API routes include geocode: GET /api/geocode/suggest, /api/geocode/resolve, /api/geocode/reverse",
    flush=True,
)

app = Flask(__name__)

# Comma-separated list, or "*" for any origin (fine for local dev; tighten in production).
_cors_raw = os.environ.get(
    "RESOURCE_FINDER_CORS_ORIGINS",
    "*",
).strip()
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "indexed_count": len(_docs)})


@app.get("/api/geocode/suggest")
def geocode_suggest():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify({"suggestions": []})
    try:
        suggestions = suggest_michigan(q)
        return jsonify({"suggestions": suggestions})
    except requests.RequestException:
        return jsonify({"error": "geocoding_unavailable"}), 503


@app.get("/api/geocode/resolve")
def geocode_resolve():
    q = (request.args.get("q") or "").strip()
    if len(q) < 3:
        return jsonify({"error": "query_too_short"}), 400
    try:
        row = resolve_first_michigan(q)
    except requests.RequestException:
        return jsonify({"error": "geocoding_unavailable"}), 503
    if not row:
        return jsonify({"error": "not_in_michigan"}), 404
    return jsonify(row)


@app.get("/api/geocode/google-place")
def geocode_google_place():
    """Resolve Google Places place_id → lat/lon (requires RESOURCE_FINDER_GOOGLE_PLACES_API_KEY)."""
    place_id = (request.args.get("place_id") or "").strip()
    if not place_id:
        return jsonify({"error": "place_id is required"}), 400
    try:
        row = google_place_details(place_id)
    except requests.RequestException:
        return jsonify({"error": "geocoding_unavailable"}), 503
    if not row:
        return jsonify({"error": "not_found_or_not_michigan"}), 404
    return jsonify(row)


@app.get("/api/geocode/reverse")
def geocode_reverse():
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon must be numbers"}), 400
    try:
        row = reverse_michigan(lat, lon)
    except requests.RequestException:
        return jsonify({"error": "geocoding_unavailable"}), 503
    if not row:
        return jsonify({"error": "not_in_michigan"}), 404
    return jsonify(row)


@app.post("/api/search")
def search():
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    try:
        lat = float(body.get("lat", DEFAULT_LAT))
        lon = float(body.get("lon", DEFAULT_LON))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon must be numbers"}), 400

    top = body.get("top", 5)
    try:
        top_k = int(top)
    except (TypeError, ValueError):
        return jsonify({"error": "top must be an integer"}), 400

    if top_k < 1:
        return jsonify({"error": "top must be at least 1"}), 400
    if top_k > MAX_TOP:
        top_k = MAX_TOP

    max_miles = None
    if "max_miles" in body and body.get("max_miles") is not None:
        try:
            max_miles = float(body["max_miles"])
        except (TypeError, ValueError):
            return jsonify({"error": "max_miles must be a number"}), 400
        if max_miles <= 0:
            return jsonify({"error": "max_miles must be greater than 0"}), 400
        if max_miles > MAX_MILES_CAP:
            max_miles = MAX_MILES_CAP

    constraint_overrides = None
    raw_c = body.get("constraints")
    if isinstance(raw_c, dict):
        constraint_overrides = {
            k: True
            for k, v in raw_c.items()
            if k in _CONSTRAINT_KEYS and v is True
        }
        if not constraint_overrides:
            constraint_overrides = None

    payload = run_search_with_index(
        _docs,
        _bm25,
        _model,
        _doc_embeddings,
        query,
        lat=lat,
        lon=lon,
        top_k=top_k,
        max_miles=max_miles,
        constraint_overrides=constraint_overrides,
    )
    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)

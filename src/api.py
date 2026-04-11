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

warnings.filterwarnings("ignore")

MAX_TOP = 20

_data_path = os.environ.get("RESOURCE_FINDER_DATA", default_data_path())

print("Loading search index (this may take a minute)...", flush=True)
_docs, _bm25, _model, _doc_embeddings = load_search_index(
    _data_path,
    quiet_embeddings=True,
)
print(f"Index ready: {len(_docs)} resources.", flush=True)

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

    payload = run_search_with_index(
        _docs,
        _bm25,
        _model,
        _doc_embeddings,
        query,
        lat=lat,
        lon=lon,
        top_k=top_k,
    )
    return jsonify(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)

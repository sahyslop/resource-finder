"""
User-facing CLI for the Local Resource Finder.
Accepts a natural-language query and prints formatted resource cards.

Programmatic use: load_search_index() once, then run_search_with_index()
for a JSON-serializable response dict.

Usage:
    python search.py "food pantry open tonight near me for families"
    python search.py "emergency shelter near ann arbor"
    python search.py "housing help for veterans"

Optional location override (defaults to Ann Arbor):
    python search.py "food pantry near me" --lat 42.2808 --lon -83.7430
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

from build_bm25 import load_docs, build_bm25
from build_embeddings import build_embeddings
from hybrid_retrieve import hybrid_search
from rerank import haversine_miles

# Default location: Ann Arbor, MI
DEFAULT_LAT = 42.2808
DEFAULT_LON = -83.7430

DIVIDER = "─" * 62

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = _REPO_ROOT / "data" / "normalized_resources.jsonl"


def default_data_path() -> str:
    return str(DEFAULT_DATA_PATH)


def load_search_index(
    data_path: str | None = None,
    *,
    quiet_embeddings: bool = True,
    show_progress_bar: bool | None = None,
):
    """
    Load documents, BM25 index, embedding model, and document embeddings.
    Call once per process for API servers.

    Returns:
        (docs, bm25, model, doc_embeddings)
    """
    path = data_path or default_data_path()
    docs = load_docs(path)
    bm25 = build_bm25(docs)

    if show_progress_bar is None:
        show_progress_bar = not quiet_embeddings

    if quiet_embeddings:
        devnull = open(os.devnull, "w")
        try:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(
                devnull
            ):
                model, doc_embeddings = build_embeddings(
                    docs, show_progress_bar=show_progress_bar
                )
        finally:
            devnull.close()
    else:
        model, doc_embeddings = build_embeddings(
            docs, show_progress_bar=show_progress_bar
        )

    return docs, bm25, model, doc_embeddings


def distance_miles(resource: dict, user_lat: float, user_lon: float) -> float | None:
    lat, lon = resource.get("lat"), resource.get("lon")
    if lat is None or lon is None:
        return None
    return round(haversine_miles(user_lat, user_lon, lat, lon), 2)


def format_distance(resource, user_lat, user_lon) -> str:
    miles = distance_miles(resource, user_lat, user_lon)
    if miles is None:
        return "distance unknown"
    return f"{miles:.1f} mi away"


def format_status(resource) -> str:
    hours = resource.get("hours_normalized", {})
    if not hours:
        return "hours unknown"

    now = datetime.now()
    day = now.strftime("%a").lower()  # mon, tue, etc.
    current_time = now.strftime("%H:%M")

    slots = hours.get(day, [])
    for start, end in slots:
        if start <= current_time <= end:
            return f"OPEN NOW  (closes {end})"
    return f"CLOSED today"


def hybrid_result_to_json_item(
    rank: int,
    result: dict,
    user_lat: float,
    user_lon: float,
) -> dict:
    doc = result["doc"]
    eligibility = (doc.get("eligibility_text") or "").strip()
    clean_eligibility = (
        eligibility[:200] if eligibility and " " in eligibility else ""
    )
    return {
        "rank": rank,
        "final_score": float(result["final_score"]),
        "lex_score": float(result.get("lex_score", 0.0)),
        "sem_score": float(result.get("sem_score", 0.0)),
        "dist_score": float(result.get("dist_score", 0.0)),
        "avail_score": float(result.get("avail_score", 0.0)),
        "distance_miles": distance_miles(doc, user_lat, user_lon),
        "distance_label": format_distance(doc, user_lat, user_lon),
        "status": format_status(doc),
        "eligibility_preview": clean_eligibility,
        "resource": doc,
    }


def run_search_with_index(
    docs,
    bm25,
    model,
    doc_embeddings,
    query: str,
    *,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    top_k: int = 5,
) -> dict:
    """
    Run hybrid search using a pre-built index. Returns a JSON-serializable dict.
    """
    q = (query or "").strip()
    results = hybrid_search(
        docs,
        bm25,
        model,
        doc_embeddings,
        q,
        user_lat=lat,
        user_lon=lon,
        top_k=top_k,
    )
    items = [
        hybrid_result_to_json_item(i, r, lat, lon)
        for i, r in enumerate(results, start=1)
    ]
    return {
        "query": q,
        "lat": lat,
        "lon": lon,
        "top_k": top_k,
        "indexed_count": len(docs),
        "results": items,
    }


def run_search(
    query: str,
    *,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    top_k: int = 5,
    data_path: str | None = None,
    quiet_embeddings: bool = True,
) -> dict:
    """Load index from disk and run one search (convenience for scripts / tests)."""
    docs, bm25, model, doc_embeddings = load_search_index(
        data_path, quiet_embeddings=quiet_embeddings
    )
    return run_search_with_index(
        docs, bm25, model, doc_embeddings, query, lat=lat, lon=lon, top_k=top_k
    )


def format_card(rank: int, result: dict, user_lat: float, user_lon: float) -> str:
    doc = result["doc"]
    score = result["final_score"]

    name = doc.get("org_name", "Unknown")
    categories = ", ".join(
        c.replace("_", " ").title() for c in doc.get("service_category", [])
    )
    address = (doc.get("address") or "").strip()
    city = doc.get("city") or ""
    state = doc.get("state") or ""
    zip_ = doc.get("zip") or ""
    full_address = address or f"{city}, {state} {zip_}".strip()

    distance = format_distance(doc, user_lat, user_lon)
    status = format_status(doc)
    hours_text = (doc.get("hours_text") or "").strip()
    eligibility = (doc.get("eligibility_text") or "").strip()
    phone = (doc.get("phone") or "").strip()
    source = (doc.get("source_url") or "").strip()

    # Header line: name left-aligned, score right-aligned
    header = f"{rank}. {name}"
    score_str = f"score: {score:.2f}"
    pad = max(1, 62 - len(header) - len(score_str))
    lines = [
        DIVIDER,
        f"{header}{' ' * pad}{score_str}",
        DIVIDER,
    ]

    def row(label, value):
        if value:
            lines.append(f"   {label:<14}{value}")

    row("Type:", categories)
    row("Address:", full_address)
    row("Distance:", distance)
    row("Hours:", hours_text[:80] if hours_text else "")
    row("Status:", status)
    # Skip eligibility text that looks like nav boilerplate (no spaces = likely junk)
    clean_eligibility = eligibility[:80] if eligibility and " " in eligibility else ""
    row("Eligibility:", clean_eligibility)
    row("Phone:", phone)
    row("Source:", source[:60] if source else "")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search for local social service resources."
    )
    parser.add_argument("query", nargs="?", help="Your search query")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT, help="Your latitude")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON, help="Your longitude")
    parser.add_argument("--top", type=int, default=5, help="Number of results to show")
    parser.add_argument(
        "--data",
        default=default_data_path(),
        help="Path to normalized resources file",
    )
    args = parser.parse_args()

    # Accept query from argument or interactive prompt
    query = args.query
    if not query:
        try:
            query = input("Search: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
    if not query:
        print("No query provided.")
        sys.exit(1)

    warnings.filterwarnings("ignore")

    print("\nLoading index...", end="\r")
    docs, bm25, model, doc_embeddings = load_search_index(
        args.data,
        quiet_embeddings=True,
    )

    results = hybrid_search(
        docs,
        bm25,
        model,
        doc_embeddings,
        query,
        user_lat=args.lat,
        user_lon=args.lon,
        top_k=args.top,
    )

    # Print results
    print(f"\nResults for: \"{query}\"")
    if not results:
        print(DIVIDER)
        print("  No results found. Try a broader query or remove constraints.")
        print(DIVIDER)
        return

    for i, result in enumerate(results, start=1):
        print(format_card(i, result, args.lat, args.lon))

    print(DIVIDER)
    print(f"  {len(results)} result(s) shown  |  data: {len(docs)} records indexed")
    print(DIVIDER)


if __name__ == "__main__":
    main()

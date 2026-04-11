"""
User-facing CLI for the Local Resource Finder.
Accepts a natural-language query and prints formatted resource cards.

Usage:
    python search.py "food pantry open tonight near me for families"
    python search.py "emergency shelter near ann arbor"
    python search.py "housing help for veterans"

Optional location override (defaults to Ann Arbor):
    python search.py "food pantry near me" --lat 42.2808 --lon -83.7430
"""

import argparse
import sys
from datetime import datetime

from build_bm25 import load_docs, build_bm25
from build_embeddings import build_embeddings
from hybrid_retrieve import hybrid_search
from rerank import haversine_miles

# Default location: Ann Arbor, MI
DEFAULT_LAT = 42.2808
DEFAULT_LON = -83.7430

DIVIDER = "─" * 62


def format_distance(resource, user_lat, user_lon) -> str:
    lat, lon = resource.get("lat"), resource.get("lon")
    if lat is None or lon is None:
        return "distance unknown"
    miles = haversine_miles(user_lat, user_lon, lat, lon)
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
        default="../data/normalized_resources.jsonl",
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

    import io, os, contextlib, warnings
    warnings.filterwarnings("ignore")

    print("\nLoading index...", end="\r")
    docs = load_docs(args.data)
    bm25 = build_bm25(docs, jsonl_path=args.data)

    # Suppress model/tqdm output. If embeddings are cached this block is near-instant.
    devnull = open(os.devnull, "w")
    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        model, doc_embeddings = build_embeddings(docs, jsonl_path=args.data)
    devnull.close()

    results = hybrid_search(
        docs, bm25, model, doc_embeddings, query,
        user_lat=args.lat, user_lon=args.lon,
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

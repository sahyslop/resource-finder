"""
Run all benchmark queries through the search system and write results for annotation.

Usage:
    python run_benchmark.py

Outputs:
    data/run_results_raw.json   — ranked results with org names, for manual annotation
    data/run_results.json       — skeleton with null labels; fill in 0/1/2, then run evaluate.py

Relevance scale:
    2 = directly usable (right service type, right area, actionable)
    1 = partially useful (related service or wrong area)
    0 = irrelevant
"""

import json
import sys
import io
import os
import contextlib
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))

from build_bm25 import load_docs, build_bm25
from build_embeddings import build_embeddings
from hybrid_retrieve import hybrid_search
from rerank import haversine_miles, resource_coords

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
QUERIES_FILE = os.path.join(DATA_DIR, "benchmark_queries.json")
RAW_OUT = os.path.join(DATA_DIR, "run_results_raw.json")
LABELS_OUT = os.path.join(DATA_DIR, "run_results.json")

# Default location: Ann Arbor, MI
USER_LAT = 42.2808
USER_LON = -83.7430
TOP_K = 10


def main():
    with open(QUERIES_FILE, encoding="utf-8") as f:
        queries = json.load(f)

    print("Loading index...")
    jsonl = os.path.join(DATA_DIR, "normalized_resources.jsonl")
    docs = load_docs(jsonl)
    bm25 = build_bm25(docs, jsonl_path=jsonl)

    devnull = open(os.devnull, "w")
    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        model, doc_embeddings = build_embeddings(docs, jsonl_path=jsonl)
    devnull.close()

    print(f"Running {len(queries)} benchmark queries...\n")

    raw_results = {}   # for human review
    label_skeleton = {}  # for evaluate.py

    for item in queries:
        qid = item["query_id"]
        query = item["query"]

        results = hybrid_search(
            docs, bm25, model, doc_embeddings, query,
            user_lat=USER_LAT, user_lon=USER_LON,
            top_k=TOP_K,
        )

        ranked = []
        for r in results:
            doc = r["doc"]
            rlat, rlon = resource_coords(doc)
            if rlat is not None:
                dist_mi = round(haversine_miles(USER_LAT, USER_LON, rlat, rlon), 1)
                coord_source = "exact" if doc.get("lat") else "city"
            else:
                dist_mi = None
                coord_source = "unknown"
            ranked.append({
                "org_name": doc.get("org_name", ""),
                "city": doc.get("city", ""),
                "service_category": doc.get("service_category", []),
                "distance_mi": dist_mi,
                "coord_source": coord_source,
                "final_score": round(r["final_score"], 3),
                "label": None,   # fill in: 0, 1, or 2
            })

        raw_results[qid] = {
            "query": query,
            "results": ranked,
        }

        label_skeleton[qid] = {
            "ranked_labels": [None] * len(ranked),
        }

        # Print summary to terminal
        print(f"[{qid}] \"{query}\"")
        for i, r in enumerate(ranked, 1):
            cats = ", ".join(r["service_category"])
            print(f"  {i:2}. {r['org_name']} ({r['city']}) [{cats}]  score={r['final_score']}")
        print()

    with open(RAW_OUT, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, indent=2, ensure_ascii=False)
    print(f"Saved ranked results -> {RAW_OUT}")

    with open(LABELS_OUT, "w", encoding="utf-8") as f:
        json.dump(label_skeleton, f, indent=2)
    print(f"Saved label skeleton -> {LABELS_OUT}")
    print("\nNext: open run_results.json and replace each null with 0, 1, or 2.")
    print("Then run:  python evaluate.py")


if __name__ == "__main__":
    main()

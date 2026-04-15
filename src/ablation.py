"""
Ablation runner — compares four retrieval conditions on the benchmark queries.

Conditions
----------
1. bm25_only       — lexical retrieval only, no embeddings, no constraint reranking
2. semantic_only   — embedding retrieval only, no BM25, no constraint reranking
3. hybrid_no_rerank — BM25 + embeddings fused equally, no constraint-aware reranking
4. full_pipeline   — current system: hybrid retrieval + constraint-aware reranking

All conditions use the same geographic pre-filtering so we're comparing scoring
methods, not data scope.  Results are pooled across conditions so a single pass
of human annotation covers all four at once.

Outputs
-------
data/ablation_results_raw.json  — ranked lists per condition per query (for review)
data/ablation_pool.json         — unique (query, doc) pairs with null labels to fill in
                                   Replace each null with 0, 1, or 2 then run ablation_eval.py

Usage
-----
    python ablation.py
"""

import json
import os
import sys
import contextlib
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))

from build_bm25 import load_docs, build_bm25, bm25_search
from build_embeddings import build_embeddings, embedding_search
from hybrid_retrieve import normalize_scores, _local_docs, hybrid_search
from rerank import rerank_candidates, resource_coords, haversine_miles
from query_parser import parse_query

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
QUERIES_FILE = os.path.join(DATA_DIR, "benchmark_queries.json")
RAW_OUT = os.path.join(DATA_DIR, "ablation_results_raw.json")
POOL_OUT = os.path.join(DATA_DIR, "ablation_pool.json")

# Same location as the main benchmark
USER_LAT = 42.2808
USER_LON = -83.7430
TOP_K = 10


# ---------------------------------------------------------------------------
# Condition implementations
# ---------------------------------------------------------------------------

def run_bm25_only(local_docs, local_bm25, query, top_k=TOP_K):
    results = normalize_scores(bm25_search(local_bm25, local_docs, query, top_k=100))
    return [{"doc": doc, "final_score": round(score, 4)} for doc, score in results[:top_k]]


def run_semantic_only(model, local_embeddings, local_docs, query, top_k=TOP_K):
    results = normalize_scores(embedding_search(model, local_embeddings, local_docs, query, top_k=100))
    return [{"doc": doc, "final_score": round(score, 4)} for doc, score in results[:top_k]]


def run_hybrid_no_rerank(local_docs, local_bm25, model, local_embeddings, query, top_k=TOP_K):
    bm25_results = normalize_scores(bm25_search(local_bm25, local_docs, query, top_k=100))
    emb_results = normalize_scores(embedding_search(model, local_embeddings, local_docs, query, top_k=100))

    merged = defaultdict(lambda: {"doc": None, "lex": 0.0, "sem": 0.0})
    for doc, score in bm25_results:
        rid = doc["resource_id"]
        merged[rid]["doc"] = doc
        merged[rid]["lex"] = score
    for doc, score in emb_results:
        rid = doc["resource_id"]
        merged[rid]["doc"] = doc
        merged[rid]["sem"] = score

    ranked = sorted(merged.values(), key=lambda x: 0.5 * x["lex"] + 0.5 * x["sem"], reverse=True)
    return [
        {"doc": c["doc"], "final_score": round(0.5 * c["lex"] + 0.5 * c["sem"], 4)}
        for c in ranked[:top_k]
    ]


def run_full_pipeline(docs, bm25, model, doc_embeddings, query, top_k=TOP_K):
    return hybrid_search(
        docs, bm25, model, doc_embeddings, query,
        user_lat=USER_LAT, user_lon=USER_LON,
        top_k=top_k,
    )


# ---------------------------------------------------------------------------
# Result formatting helpers
# ---------------------------------------------------------------------------

def _format_result_list(results):
    """Convert result dicts to a compact list for JSON output."""
    out = []
    for r in results:
        doc = r["doc"]
        rlat, rlon = resource_coords(doc)
        if rlat is not None:
            dist_mi = round(haversine_miles(USER_LAT, USER_LON, rlat, rlon), 1)
        else:
            dist_mi = None
        out.append({
            "resource_id": doc.get("resource_id", ""),
            "org_name": doc.get("org_name", ""),
            "city": doc.get("city", ""),
            "service_category": doc.get("service_category", []),
            "distance_mi": dist_mi,
            "final_score": r.get("final_score"),
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    # Pre-compute local subset (same for all conditions — fair comparison)
    local_docs = _local_docs(docs, USER_LAT, USER_LON)
    if not local_docs:
        print("ERROR: no local docs found for given coordinates.")
        sys.exit(1)

    # Build a local BM25 index and local embeddings for the local subset
    local_bm25 = build_bm25(local_docs)
    doc_ids = {doc["resource_id"] for doc in local_docs}
    import numpy as np
    local_indices = [i for i, doc in enumerate(docs) if doc["resource_id"] in doc_ids]
    local_embeddings = doc_embeddings[local_indices]

    print(f"Local pool: {len(local_docs)} docs within dynamic radius of Ann Arbor")
    print(f"Running {len(queries)} queries × 4 conditions...\n")

    CONDITIONS = ["bm25_only", "semantic_only", "hybrid_no_rerank", "full_pipeline"]

    raw_output = {}   # per-query, per-condition ranked lists
    pool = {}         # per-query: {resource_id: {org_name, label}}

    for item in queries:
        qid = item["query_id"]
        query = item["query"]
        print(f"[{qid}] \"{query}\"")

        results = {
            "bm25_only": run_bm25_only(local_docs, local_bm25, query),
            "semantic_only": run_semantic_only(model, local_embeddings, local_docs, query),
            "hybrid_no_rerank": run_hybrid_no_rerank(local_docs, local_bm25, model, local_embeddings, query),
            "full_pipeline": run_full_pipeline(docs, bm25, model, doc_embeddings, query),
        }

        # Show a quick preview
        for cond in CONDITIONS:
            top3 = results[cond][:3]
            names = [r["doc"].get("org_name", "?") for r in top3]
            print(f"  {cond:<20} → {', '.join(names)}")
        print()

        # Build pooled annotation set: union of top-K docs across all conditions
        pool_entry = {}
        for cond in CONDITIONS:
            for r in results[cond]:
                doc = r["doc"]
                rid = doc.get("resource_id", "")
                if rid and rid not in pool_entry:
                    pool_entry[rid] = {
                        "resource_id": rid,
                        "org_name": doc.get("org_name", ""),
                        "city": doc.get("city", ""),
                        "service_category": doc.get("service_category", []),
                        "label": None,  # fill in: 0, 1, or 2
                    }

        pool[qid] = {
            "query": query,
            "docs": pool_entry,
        }

        raw_output[qid] = {
            "query": query,
            "conditions": {
                cond: _format_result_list(results[cond])
                for cond in CONDITIONS
            },
        }

    # Write outputs
    with open(RAW_OUT, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, indent=2, ensure_ascii=False)
    print(f"Saved ranked results  → {RAW_OUT}")

    with open(POOL_OUT, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)
    print(f"Saved annotation pool → {POOL_OUT}")
    print()
    print("Next steps:")
    print("  1. Open ablation_pool.json")
    print("  2. For each query, set each doc's \"label\" to 0, 1, or 2")
    print("     (use ablation_results_raw.json to see what each system returned and in what order)")
    print("  3. Run:  python ablation_eval.py")


if __name__ == "__main__":
    main()

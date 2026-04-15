"""
Evaluate all four ablation conditions from a single annotated pool.

Usage
-----
    python ablation_eval.py

Input
-----
    data/ablation_pool.json       — pool with labels filled in (0/1/2 per doc)
    data/ablation_results_raw.json — ranked lists per condition (written by ablation.py)

Output
------
    Prints a comparison table of P@3, MRR, nDCG@5 for each condition.
    Optionally writes data/ablation_metrics.json for the paper.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from evaluate import precision_at_k, reciprocal_rank, ndcg_at_k

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
POOL_FILE = os.path.join(DATA_DIR, "ablation_pool.json")
RAW_FILE = os.path.join(DATA_DIR, "ablation_results_raw.json")
METRICS_OUT = os.path.join(DATA_DIR, "ablation_metrics.json")

CONDITIONS = ["bm25_only", "semantic_only", "hybrid_no_rerank", "full_pipeline"]
CONDITION_LABELS = {
    "bm25_only":          "BM25 only",
    "semantic_only":      "Semantic only",
    "hybrid_no_rerank":   "Hybrid (no rerank)",
    "full_pipeline":      "Full pipeline",
}


def main():
    with open(POOL_FILE, encoding="utf-8") as f:
        pool = json.load(f)
    with open(RAW_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    # Validate that all labels have been filled in
    missing = []
    for qid, entry in pool.items():
        for rid, doc in entry["docs"].items():
            if doc["label"] is None:
                missing.append((qid, doc.get("org_name", rid)))
    if missing:
        print(f"ERROR: {len(missing)} labels still null in ablation_pool.json.")
        print("Fill them in first, then re-run this script.")
        for qid, name in missing[:10]:
            print(f"  [{qid}] {name}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
        sys.exit(1)

    # Build lookup: qid → resource_id → label
    label_lookup = {}
    for qid, entry in pool.items():
        label_lookup[qid] = {rid: doc["label"] for rid, doc in entry["docs"].items()}

    # Compute metrics per condition
    condition_metrics = {cond: {"P@3": [], "MRR": [], "nDCG@5": []} for cond in CONDITIONS}

    for qid, entry in raw.items():
        for cond in CONDITIONS:
            ranked_docs = entry["conditions"][cond]
            labels = []
            for r in ranked_docs:
                rid = r["resource_id"]
                # Docs not in the pool (shouldn't happen) default to 0
                label = label_lookup.get(qid, {}).get(rid, 0)
                labels.append(label)

            condition_metrics[cond]["P@3"].append(precision_at_k(labels, 3))
            condition_metrics[cond]["MRR"].append(reciprocal_rank(labels))
            condition_metrics[cond]["nDCG@5"].append(ndcg_at_k(labels, 5))

    # Average across queries
    averaged = {}
    for cond in CONDITIONS:
        m = condition_metrics[cond]
        averaged[cond] = {k: round(sum(v) / len(v), 4) for k, v in m.items()}

    # Pretty-print the table
    col_w = 20
    metric_cols = ["P@3", "MRR", "nDCG@5"]
    header = f"{'Condition':<{col_w}}" + "".join(f"{m:>10}" for m in metric_cols)
    sep = "-" * len(header)

    print()
    print("Ablation Results")
    print(sep)
    print(header)
    print(sep)
    for cond in CONDITIONS:
        row = f"{CONDITION_LABELS[cond]:<{col_w}}"
        for m in metric_cols:
            row += f"{averaged[cond][m]:>10.4f}"
        print(row)
    print(sep)
    print(f"Queries evaluated: {len(raw)}")
    print()

    # Save JSON for paper
    with open(METRICS_OUT, "w", encoding="utf-8") as f:
        json.dump(averaged, f, indent=2)
    print(f"Saved metrics → {METRICS_OUT}")


if __name__ == "__main__":
    main()

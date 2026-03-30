import json
import math
from collections import defaultdict


def precision_at_k(labels, k):
    top = labels[:k]
    if not top:
        return 0.0
    return sum(1 for x in top if x > 0) / len(top)


def recall_at_k(labels, total_relevant, k):
    if total_relevant == 0:
        return 0.0
    return sum(1 for x in labels[:k] if x > 0) / total_relevant


def reciprocal_rank(labels):
    for i, rel in enumerate(labels, start=1):
        if rel > 0:
            return 1.0 / i
    return 0.0


def ndcg_at_k(labels, k):
    dcg = 0.0
    for i, rel in enumerate(labels[:k], start=1):
        dcg += (2 ** rel - 1) / math.log2(i + 1)

    ideal = sorted(labels, reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(ideal, start=1):
        idcg += (2 ** rel - 1) / math.log2(i + 1)

    return dcg / idcg if idcg > 0 else 0.0


def evaluate_run(run_file: str):
    with open(run_file, "r", encoding="utf-8") as f:
        runs = json.load(f)

    metrics = defaultdict(list)

    for qid, row in runs.items():
        labels = row["ranked_labels"]
        total_relevant = sum(1 for x in labels if x > 0)

        metrics["P@3"].append(precision_at_k(labels, 3))
        metrics["P@5"].append(precision_at_k(labels, 5))
        metrics["Recall@10"].append(recall_at_k(labels, total_relevant, 10))
        metrics["MRR"].append(reciprocal_rank(labels))
        metrics["nDCG@5"].append(ndcg_at_k(labels, 5))

    return {k: round(sum(v) / len(v), 4) for k, v in metrics.items()}


if __name__ == "__main__":
    scores = evaluate_run("../data/run_results.json")
    print(scores)

import json
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi


def tokenize(text: str):
    return text.lower().split()


def doc_text(doc):
    return " ".join([
        doc.get("org_name", ""),
        " ".join(doc.get("service_category", [])),
        doc.get("description", ""),
        doc.get("eligibility_text", "")
    ])


def load_docs(path: str):
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line))
    return docs


def build_bm25(docs, jsonl_path: str = None):
    """
    Build or load a BM25 index.

    If `jsonl_path` is provided, a pickle cache is kept next to it and
    reloaded on subsequent runs as long as the JSONL hasn't changed.
    """
    cache = Path(jsonl_path).with_suffix(".bm25.pkl") if jsonl_path else None
    jsonl = Path(jsonl_path) if jsonl_path else None

    if cache and cache.exists() and cache.stat().st_mtime >= jsonl.stat().st_mtime:
        with open(cache, "rb") as f:
            return pickle.load(f)

    corpus = [tokenize(doc_text(doc)) for doc in docs]
    bm25 = BM25Okapi(corpus)

    if cache:
        with open(cache, "wb") as f:
            pickle.dump(bm25, f)

    return bm25


def bm25_search(bm25, docs, query, top_k=20):
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(
        zip(docs, scores),
        key=lambda x: x[1],
        reverse=True
    )[:top_k]
    return [(doc, float(score)) for doc, score in ranked]


if __name__ == "__main__":
    docs = load_docs("../data/normalized_resources.jsonl")
    bm25 = build_bm25(docs)
    results = bm25_search(bm25, docs, "food pantry open tonight near me", top_k=5)
    for doc, score in results:
        print(score, doc["org_name"])

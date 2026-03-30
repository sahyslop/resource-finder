import json
from collections import defaultdict

from query_parser import parse_query
from build_bm25 import load_docs, build_bm25, bm25_search
from build_embeddings import build_embeddings, embedding_search
from rerank import rerank_candidates


def normalize_scores(results):
    if not results:
        return []
    scores = [score for _, score in results]
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [(doc, 1.0) for doc, _ in results]
    return [(doc, (score - lo) / (hi - lo)) for doc, score in results]


def hybrid_search(docs, bm25, model, doc_embeddings, query, user_lat=None, user_lon=None, top_k=10):
    parsed = parse_query(query)

    bm25_results = normalize_scores(bm25_search(bm25, docs, query, top_k=30))
    emb_results = normalize_scores(embedding_search(model, doc_embeddings, docs, query, top_k=30))

    merged = defaultdict(lambda: {"doc": None, "lex_score": 0.0, "sem_score": 0.0})

    for doc, score in bm25_results:
        rid = doc["resource_id"]
        merged[rid]["doc"] = doc
        merged[rid]["lex_score"] = score

    for doc, score in emb_results:
        rid = doc["resource_id"]
        merged[rid]["doc"] = doc
        merged[rid]["sem_score"] = score

    candidates = list(merged.values())
    ranked = rerank_candidates(candidates, parsed, user_lat=user_lat, user_lon=user_lon)
    return ranked[:top_k]


if __name__ == "__main__":
    docs = load_docs("../data/normalized_resources.jsonl")
    bm25 = build_bm25(docs)
    model, doc_embeddings = build_embeddings(docs)

    query = "food pantry open tonight near me for families"
    results = hybrid_search(docs, bm25, model, doc_embeddings, query, user_lat=42.2808, user_lon=-83.7430)

    for r in results:
        print(r["final_score"], r["doc"]["org_name"])

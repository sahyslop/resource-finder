import json
from collections import defaultdict

from query_parser import parse_query
from build_bm25 import load_docs, build_bm25, bm25_search
from build_embeddings import build_embeddings, embedding_search
from rerank import rerank_candidates, resource_coords, haversine_miles

RADIUS_TIERS = [10, 20, 30]   # miles — expand outward until enough results found
MIN_RESULTS = 5                # minimum results before stopping expansion

# Cache BM25 indexes by the exact set of resource_ids they were built from.
# Within a session (e.g. repeated queries at the same location) this avoids
# rebuilding the lexical index from scratch on every call.
_bm25_cache: dict = {}


def _get_cached_bm25(search_docs):
    key = frozenset(doc["resource_id"] for doc in search_docs)
    if key not in _bm25_cache:
        _bm25_cache[key] = build_bm25(search_docs)
    return _bm25_cache[key]


def normalize_scores(results):
    if not results:
        return []
    scores = [score for _, score in results]
    lo = min(scores)
    # Clip the ceiling at the 95th percentile so one very strong BM25 or
    # embedding match doesn't compress every other score toward zero.
    if len(scores) >= 5:
        sorted_scores = sorted(scores)
        hi = sorted_scores[int(len(sorted_scores) * 0.95)]
    else:
        hi = max(scores)
    if hi <= lo:
        return [(doc, 1.0) for doc, _ in results]
    return [(doc, min((score - lo) / (hi - lo), 1.0)) for doc, score in results]


def _local_docs(docs, user_lat, user_lon, max_radius_miles=None):
    """
    Return docs within a dynamic radius, expanding through RADIUS_TIERS until
    at least MIN_RESULTS docs with known coordinates are found.
    Docs with no resolvable location are always included.

    If max_radius_miles is set, only docs with a known location within that
    radius are returned (strict filter; unknown locations are excluded).
    """
    if max_radius_miles is not None:
        return [
            doc
            for doc in docs
            if resource_coords(doc)[0] is not None
            and haversine_miles(user_lat, user_lon, *resource_coords(doc))
            <= max_radius_miles
        ]

    unknown_loc = [doc for doc in docs if resource_coords(doc)[0] is None]

    for radius in RADIUS_TIERS:
        within = [
            doc for doc in docs
            if resource_coords(doc)[0] is not None
            and haversine_miles(user_lat, user_lon, *resource_coords(doc)) <= radius
        ]
        if len(within) >= MIN_RESULTS:
            return within + unknown_loc

    # Exhausted all tiers — return everything from the widest radius + unknowns
    widest = [
        doc for doc in docs
        if resource_coords(doc)[0] is not None
        and haversine_miles(user_lat, user_lon, *resource_coords(doc)) <= RADIUS_TIERS[-1]
    ]
    return widest + unknown_loc


def hybrid_search(
    docs,
    bm25,
    model,
    doc_embeddings,
    query,
    user_lat=None,
    user_lon=None,
    top_k=10,
    max_radius_miles=None,
):
    parsed = parse_query(query)

    # When we have a user location, restrict BM25 + embedding search to local docs only.
    # This prevents globally-popular text matches (e.g. every "Food Pantry" in Michigan)
    # from crowding out nearby results that score equally on text.
    if user_lat is not None and user_lon is not None:
        search_docs = _local_docs(
            docs, user_lat, user_lon, max_radius_miles=max_radius_miles
        )
        if not search_docs:
            return []
        # Reuse a cached BM25 index if this exact doc set was seen before.
        local_bm25 = _get_cached_bm25(search_docs)
        # Embeddings: filter to the local subset by index position
        doc_ids = {doc["resource_id"] for doc in search_docs}
        local_indices = [i for i, doc in enumerate(docs) if doc["resource_id"] in doc_ids]
        import numpy as np
        local_embeddings = doc_embeddings[local_indices]
    else:
        search_docs = docs
        local_bm25 = bm25
        local_embeddings = doc_embeddings

    bm25_results = normalize_scores(bm25_search(local_bm25, search_docs, query, top_k=100))
    emb_results = normalize_scores(embedding_search(model, local_embeddings, search_docs, query, top_k=100))

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

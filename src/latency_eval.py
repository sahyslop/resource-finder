import time
from statistics import mean

from build_bm25 import load_docs, build_bm25, bm25_search
from build_embeddings import build_embeddings, embedding_search
from hybrid_retrieve import hybrid_search, _local_docs

QUERIES = [
    "food pantry near me",
    "food pantry open tonight for families",
    "somewhere to sleep tonight",
    "housing help near me",
    "rent help for families"
]

USER_LAT, USER_LON = 42.2808, -83.7430


def benchmark():
    docs = load_docs("../data/normalized_resources.jsonl")
    bm25 = build_bm25(docs)
    model, doc_embeddings = build_embeddings(docs)

    # Build local index once — same subset used during real queries
    local_docs = _local_docs(docs, USER_LAT, USER_LON)
    local_bm25 = build_bm25(local_docs)
    doc_ids = {doc["resource_id"] for doc in local_docs}
    local_indices = [i for i, doc in enumerate(docs) if doc["resource_id"] in doc_ids]
    local_embeddings = doc_embeddings[local_indices]

    print(f"Index size: {len(docs)} total docs, {len(local_docs)} local docs\n")

    bm25_times = []
    emb_times = []
    hybrid_times = []

    for q in QUERIES:
        t0 = time.perf_counter()
        bm25_search(local_bm25, local_docs, q, top_k=10)
        bm25_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        embedding_search(model, local_embeddings, local_docs, q, top_k=10)
        emb_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        hybrid_search(docs, bm25, model, doc_embeddings, q, user_lat=USER_LAT, user_lon=USER_LON, top_k=10)
        hybrid_times.append((time.perf_counter() - t0) * 1000)

    print(f"{'Component':<20} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10}")
    print("-" * 52)
    for label, times in [("BM25 (local)", bm25_times), ("Embedding (local)", emb_times), ("Hybrid (full)", hybrid_times)]:
        print(f"{label:<20} {round(mean(times), 2):>10} {round(min(times), 2):>10} {round(max(times), 2):>10}")


if __name__ == "__main__":
    benchmark()

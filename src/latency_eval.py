import time
from statistics import mean

from build_bm25 import load_docs, build_bm25, bm25_search
from build_embeddings import build_embeddings, embedding_search
from hybrid_retrieve import hybrid_search

QUERIES = [
    "food pantry near me",
    "food pantry open tonight for families",
    "somewhere to sleep tonight",
    "housing help near me",
    "rent help for families"
]


def benchmark():
    docs = load_docs("../data/normalized_resources.jsonl")
    bm25 = build_bm25(docs)
    model, doc_embeddings = build_embeddings(docs)

    bm25_times = []
    emb_times = []
    hybrid_times = []

    for q in QUERIES:
        t0 = time.perf_counter()
        bm25_search(bm25, docs, q, top_k=10)
        bm25_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        embedding_search(model, doc_embeddings, docs, q, top_k=10)
        emb_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        hybrid_search(docs, bm25, model, doc_embeddings, q, user_lat=42.2808, user_lon=-83.7430, top_k=10)
        hybrid_times.append((time.perf_counter() - t0) * 1000)

    print("BM25 avg ms:", round(mean(bm25_times), 2))
    print("Embedding avg ms:", round(mean(emb_times), 2))
    print("Hybrid avg ms:", round(mean(hybrid_times), 2))


if __name__ == "__main__":
    benchmark()

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_docs(path: str):
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            docs.append(json.loads(line))
    return docs


def doc_text(doc):
    return " ".join([
        doc.get("org_name", ""),
        " ".join(doc.get("service_category", [])),
        doc.get("description", ""),
        doc.get("eligibility_text", "")
    ])


def build_embeddings(docs, jsonl_path: str = None, show_progress_bar=True):
    """
    Load or compute document embeddings.

    If `jsonl_path` is provided, a .npy cache file is kept next to it.
    The cache is reused as long as the JSONL hasn't been modified since
    the cache was written — no recomputation needed between runs.
    """
    model = SentenceTransformer(MODEL_NAME)

    cache = Path(jsonl_path).with_suffix(".embeddings.npy") if jsonl_path else None
    jsonl = Path(jsonl_path) if jsonl_path else None

    if cache and cache.exists() and cache.stat().st_mtime >= jsonl.stat().st_mtime:
        embeddings = np.load(cache)
        return model, embeddings

    texts = [doc_text(doc) for doc in docs]
    embeddings = np.array(
        model.encode(texts, normalize_embeddings=True, show_progress_bar=show_progress_bar)
    )

    if cache:
        np.save(cache, embeddings)

    return model, embeddings


def embedding_search(model, doc_embeddings, docs, query, top_k=20):
    q_emb = model.encode([query], normalize_embeddings=True)[0]
    scores = doc_embeddings @ q_emb
    idx = np.argsort(-scores)[:top_k]
    return [(docs[i], float(scores[i])) for i in idx]


if __name__ == "__main__":
    docs = load_docs("../data/normalized_resources.jsonl")
    model, embs = build_embeddings(docs)
    results = embedding_search(model, embs, docs, "somewhere to sleep tonight", top_k=5)
    for doc, score in results:
        print(score, doc["org_name"])

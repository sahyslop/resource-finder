import json
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


def build_bm25(docs):
    corpus = [tokenize(doc_text(doc)) for doc in docs]
    return BM25Okapi(corpus)


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

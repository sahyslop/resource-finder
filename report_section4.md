# 6. Results and Discussion

## 6.1 Retrieval Quality

We evaluated the system using 10 benchmark queries representative of real user needs, run against a normalized index of 1,629 records with a default user location of Ann Arbor, MI. Each query retrieved up to 10 results, which were manually annotated on a 3-point scale: 2 (directly usable), 1 (partially useful), 0 (irrelevant).

| Metric | Score |
|--------|-------|
| P@3 | 0.833 |
| P@5 | 0.820 |
| Recall@10 | 0.900 |
| MRR | 0.850 |
| nDCG@5 | 0.802 |

The system achieves strong precision at shallow cutoffs, with 83% of top-3 results judged relevant. Mean Reciprocal Rank (MRR) of 0.85 indicates the first relevant result appears at rank 1 or 2 in most queries, meaning users rarely need to scroll past the first result before finding something useful. Recall@10 of 0.90 suggests the system surfaces nearly all relevant resources within the top 10. The nDCG@5 score of 0.80, while still strong, is the weakest metric, indicating occasional cases where partially relevant results rank above highly relevant ones.

## 6.2 System Design Iterations

Several design decisions were revised significantly during development after observing system failures in practice.

**Candidate pool size.** The initial pipeline fetched only the top 30 candidates from BM25 and top 30 from embeddings before reranking. Because distance is applied at reranking time, any local record that ranked outside the top 30 on text relevance alone was silently dropped. Increasing the candidate pool to 100 per source improved local recall but did not fully resolve the problem.

**Global vs. local retrieval.** The more impactful fix was pre-filtering by geography before running BM25 and embedding search at all. Running BM25 over all 1,629 records caused terms like "Food Pantry" to match equally across Michigan, leaving the distance signal with insufficient leverage to distinguish a 2-mile result from a 26-mile one. Restricting retrieval to geographically local documents first reduced the search pool from 1,629 to approximately 53 documents for an Ann Arbor query, after which text-based ranking became meaningful and local results consistently surfaced at the top.

**Hard distance cutoff vs. dynamic radius.** An initial hard cap of 30 miles was replaced with a dynamic radius expansion (10 → 20 → 30 miles), which stops expanding once at least 5 results with known coordinates are found. This prevents distant results from appearing when local options exist, while gracefully degrading in areas with sparse coverage.

**Distance decay function.** The original scoring divided 1 by (1 + distance), which is a relatively gentle decay — a 5-mile result scored only 4 times better than a 26-mile result. Replacing the exponent with 1.5 steepened the penalty considerably, making a 5-mile result roughly 20 times better than a 26-mile one. Combined with increased distance weights (0.30 base, 0.40 when the query contains "near me"), this meaningfully separated local and distant candidates in the final ranking.

## 6.3 Data Quality Issues

A significant portion of the development effort was spent addressing data quality problems that directly degraded retrieval accuracy.

**Missing coordinates.** Records scraped from directory sites (foodpantries.org, shelterlistings.org) were initially collected without geocoding, leaving latitude and longitude as null for 388 of 1,629 records (24%). These records bypassed the distance filter entirely, causing cities like Lansing (~65 miles away) to appear in Ann Arbor queries with a displayed distance of 0.0 miles. This was resolved in two stages: a geocoding pass using the Nominatim API to fill in coordinates from addresses, and a fallback lookup table of Michigan city centroids for records where full geocoding failed.

**Bad coordinates.** Several records contained coordinates placing them in other states, including a food pantry geocoded to Seattle, WA and one resolved to Jackson, MS rather than Jackson, MI. Because BM25 is location-agnostic, these records competed on text relevance and appeared in results until the geographic pre-filter was introduced.

**Missing street addresses.** Shelter records from shelterlistings.org had empty address fields in 99% of cases, as the scraper extracted only city-level information. Distance calculations for these records are approximated to the city centroid, introducing error on the order of 2–5 miles for larger cities.

**Eligibility boilerplate.** Scraped eligibility text frequently contained site navigation boilerplate (e.g., "About Us · Partner With Us · Add A New Listing") rather than actual service eligibility. A fallback of "Open to all" was applied when no meaningful eligibility text was detected, preventing records from being falsely excluded by eligibility hard filters.

**Duplicate records.** Multiple raw data files from different collection runs were inadvertently included in the index build process, resulting in stale null-coordinate versions of records taking precedence over newly geocoded ones during deduplication. Cleanup of these intermediate artifact files was required before producing a reliable index.

## 6.4 Efficiency and Scalability

We measured per-component query latency averaged over 5 benchmark queries, with all components operating over the geographically filtered local document set (~53 docs for Ann Arbor):

| Component | Avg (ms) | Min (ms) | Max (ms) |
|-----------|----------|----------|----------|
| BM25 (local) | 1.26 | 0.11 | 5.67 |
| Embedding (local) | 67.69 | 14.53 | 188.16 |
| Hybrid (full pipeline) | 19.19 | 18.11 | 21.28 |

BM25 is nearly instant at 1.26ms on average. Embedding search is the most expensive component at 67.69ms, with high variance (14–188ms) caused by model cold-start on the first query. The full hybrid pipeline runs in a consistent ~19ms because the geographic pre-filter reduces the embedding search space from 1,626 total documents to ~53 local ones — a 30x reduction. Index load and initial embedding inference take approximately 2–3 seconds on cold start (MacBook Air M1); subsequent queries within the same session run well under 100ms.

The primary scalability constraint is the embedding matrix, which is recomputed on each script invocation. Persisting embeddings to disk would eliminate this overhead. For a production system serving a statewide dataset, a dedicated vector similarity library such as FAISS (Facebook AI Similarity Search) would be required in place of the exhaustive cosine similarity used here.

## 6.5 Failure Analysis

The most common failure mode observed was distance errors caused by missing or incorrect coordinates, which was the single largest source of irrelevant results before the geocoding and pre-filtering fixes described above. A secondary failure mode was over-filtering: records with no eligibility text were sometimes excluded from family or veteran queries because the eligibility flags defaulted to false, causing the hard filter to reject otherwise valid resources. The "Open to all" fallback mitigated this but introduced false positives in the opposite direction. Hours data was missing for approximately 70% of records, which prevented the "open now" constraint from meaningfully filtering results in most cases. Finally, the dynamic radius expansion occasionally returned a mix of very close and moderately distant results within the same query when local coverage was sparse, producing result sets that were harder to interpret.

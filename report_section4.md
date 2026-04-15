# 6. Results and Discussion

## 6.1 Retrieval Quality

We evaluated the system using 30 benchmark queries representative of real user needs, run against a normalized index of 1,629 records with a default user location of Ann Arbor, MI. Queries cover a range of resource types (food, housing, shelter, utilities, mental health), geographic references across Michigan, eligibility-constrained requests, and urgent or time-sensitive framing. Each query retrieved up to 10 results, which were manually annotated on a 3-point scale: 2 (directly usable), 1 (partially useful), 0 (irrelevant).

| Metric | Score |
|--------|-------|
| P@3 | 0.689 |
| P@5 | 0.693 |
| Recall@10 | 0.833 |
| MRR | 0.778 |
| nDCG@5 | 0.688 |

The system achieves solid precision at shallow cutoffs, with 69% of top-3 results judged relevant across a diverse 30-query set. MRR of 0.778 indicates the first relevant result typically appears within the top two ranks. Recall@10 of 0.833 suggests the system surfaces the majority of relevant resources within the top 10. The nDCG@5 score reflects occasional cases where partially relevant results rank above highly relevant ones. Compared to our earlier 10-query evaluation, these numbers are lower but represent a more realistic estimate: the expanded benchmark includes harder queries, out-of-area geographic references, and resource types with sparse coverage in the dataset.

## 6.2 System Design Iterations

Several design decisions were revised significantly during development after observing system failures in practice.

**Candidate pool size.** The initial pipeline fetched only the top 30 candidates from BM25 and top 30 from embeddings before reranking. Because distance is applied at reranking time, any local record that ranked outside the top 30 on text relevance alone was silently dropped. Increasing the candidate pool to 100 per source improved local recall but did not fully resolve the problem.

**Global vs. local retrieval.** The more impactful fix was pre-filtering by geography before running BM25 and embedding search at all. Running BM25 over all 1,629 records caused terms like "Food Pantry" to match equally across Michigan, leaving the distance signal with insufficient leverage to distinguish a 2-mile result from a 26-mile one. Restricting retrieval to geographically local documents first reduced the search pool from 1,629 to approximately 53 documents for an Ann Arbor query, after which text-based ranking became meaningful and local results consistently surfaced at the top.

**Hard distance cutoff vs. dynamic radius.** An initial hard cap of 30 miles was replaced with a dynamic radius expansion (10 → 20 → 30 miles), which stops expanding once at least 5 results with known coordinates are found. This prevents distant results from appearing when local options exist, while gracefully degrading in areas with sparse coverage.

**Distance decay function.** The original scoring divided 1 by (1 + distance), which is a relatively gentle decay — a 5-mile result scored only 4 times better than a 26-mile result. Replacing the exponent with 1.5 steepened the penalty considerably, making a 5-mile result roughly 20 times better than a 26-mile one. Combined with increased distance weights (0.30 base, 0.40 when the query contains "near me"), this meaningfully separated local and distant candidates in the final ranking.

**Runtime caching.** Initial query latency was dominated by two expensive operations: building the BM25 index from the full JSONL (~2–3 seconds) and encoding all 1,629 documents with the sentence transformer (~5–6 seconds) on every cold start. Both were eliminated with disk-level caches — the BM25 index is pickled alongside the data file and reloaded when the JSONL modification time is unchanged; embeddings are persisted as a `.npy` file under the same invalidation policy. This reduced cold-start time from approximately 8 seconds to 2–3 seconds (MacBook Air M1). A third caching layer was added at the session level: because the geographic pre-filter produces the same local document subset for repeated queries at the same location, the BM25 index built over that subset is kept in memory keyed by its document set. Without this, every query rebuilt a new local BM25 index from scratch, adding ~200ms per call.

**Score normalization fix.** The original min-max normalization for BM25 and embedding scores used the true maximum as the ceiling, which caused a single very strong match to compress all other scores toward zero. This made the hybrid fusion unstable — one outlier document would dominate the merged score list regardless of the other signals. The fix clips the normalization ceiling at the 95th percentile score rather than the maximum, ensuring the relative spread of the remaining candidates is preserved.

## 6.3 Data Quality Iterations

A significant portion of the development effort was spent identifying and fixing data quality problems that directly degraded retrieval accuracy. Each issue below was discovered through observed failures in query results, not anticipated in advance.

**Missing coordinates → geocoding pass + city centroid fallback.** Records scraped from directory sites (foodpantries.org, shelterlistings.org) were initially collected without geocoding, leaving latitude and longitude as null for 388 of 1,629 records (24%). These records bypassed the distance filter entirely, causing cities like Lansing (~65 miles away) to appear in Ann Arbor queries with a displayed distance of 0.0 miles. We first ran a geocoding pass using the Nominatim API to fill in coordinates from street addresses. For records where full geocoding failed, we added a lookup table of Michigan city centroids (19 cities) as a fallback. Together these two steps resolved coordinates for the majority of previously unlocatable records.

**Bad coordinates → geographic pre-filter.** Several records contained coordinates placing them outside Michigan entirely, including a food pantry geocoded to Seattle, WA and one resolved to Jackson, MS rather than Jackson, MI. These records competed on text relevance and appeared in results regardless of user location. The geographic pre-filter introduced in Section 6.2 eliminated this class of error by restricting retrieval to the local pool before any text scoring occurs.

**Missing street addresses → city-level approximation.** Shelter records from shelterlistings.org had empty address fields in 99% of cases — the scraper extracted only city-level information. Distance calculations for these records are approximated to the city centroid, introducing error on the order of 2–5 miles for larger cities. This remains an unresolved limitation; precise shelter addresses would require a secondary data source or manual curation.

**Eligibility boilerplate → "Open to all" fallback.** Scraped eligibility text frequently contained site navigation boilerplate (e.g., "About Us · Partner With Us · Add A New Listing") rather than actual eligibility criteria. An earlier version of the pipeline used a hard eligibility filter that excluded records failing to match constraint flags, which caused valid resources to be dropped when their eligibility text was garbage. We replaced the hard filter with a soft multiplier: confirmed matches score 1.0, missing flags score 0.75 (penalized but not excluded), and penalties stack across multiple unmet constraints. This change recovered previously excluded resources at the cost of some precision on eligibility-constrained queries.

**Duplicate records → index cleanup.** Multiple raw data files from different collection runs were inadvertently included in the index build, resulting in stale null-coordinate versions of records taking precedence over newly geocoded ones during deduplication. Cleanup of these artifact files was required before producing a reliable index, and the issue reinforced the importance of treating the index build as a reproducible pipeline rather than an ad hoc process.

## 6.4 Ablation Study

To evaluate the contribution of each retrieval component, we compared four conditions on the full 30-query benchmark. All conditions use the same geographic pre-filter so we are comparing scoring mechanisms, not data scope.

| Condition | P@3 | MRR | nDCG@5 |
|---|---|---|---|
| BM25 only | 0.633 | 0.761 | 0.537 |
| Hybrid (no rerank) | 0.778 | 0.873 | 0.651 |
| Full pipeline | 0.789 | 0.833 | 0.739 |
| Semantic only | 0.900 | 0.933 | 0.760 |

BM25 alone performs worst across all metrics, particularly on nDCG@5 (0.537). This is expected: crisis-oriented queries like "somewhere to sleep tonight" or "I need food" use natural language that maps poorly to keyword overlap with document text. Moving from BM25 to hybrid retrieval (adding embeddings with no reranking) improves P@3 by 14 points and nDCG@5 by 11 points, confirming that the embedding model captures semantic intent that BM25 misses.

The most notable finding is that semantic-only retrieval outperforms the full pipeline on P@3 and MRR. This is likely explained by the sparse hours data: approximately 70% of records have no hours information, which means the availability signal in the constraint reranker defaults to a penalty of 0.0 for most records whenever a time-sensitive query is made. Rather than helping, the availability weight redistributes scores in a way that occasionally demotes relevant results. The constraint reranker does improve nDCG@5 over hybrid-no-rerank (0.739 vs. 0.651), suggesting it improves ranked list quality even when it slightly delays the first relevant hit. This trade-off would likely reverse in favor of the full pipeline if hours data coverage were improved.

## 6.5 Efficiency and Scalability

We measured per-component query latency averaged over 5 benchmark queries, with all components operating over the geographically filtered local document set (~53 docs for Ann Arbor):

| Component | Avg (ms) | Min (ms) | Max (ms) |
|-----------|----------|----------|----------|
| BM25 (local) | 1.26 | 0.11 | 5.67 |
| Embedding (local) | 67.69 | 14.53 | 188.16 |
| Hybrid (full pipeline) | 19.19 | 18.11 | 21.28 |

BM25 is nearly instant at 1.26ms on average. Embedding search is the most expensive component at 67.69ms, with high variance (14–188ms) caused by model cold-start on the first query. The full hybrid pipeline runs in a consistent ~19ms because the geographic pre-filter reduces the embedding search space from 1,629 total documents to ~53 local ones — roughly a 30x reduction. Index load and initial embedding inference take approximately 2–3 seconds on cold start (MacBook Air M1); subsequent queries within the same session run well under 100ms.

The primary remaining scalability constraint is the exhaustive cosine similarity over the embedding matrix. For a production system serving a statewide dataset, a dedicated vector similarity library such as FAISS would be required. The geographic pre-filter mitigates this at current scale but would not scale to a national index without an additional spatial indexing layer.

## 6.6 Failure Analysis

**Out-of-area queries.** Queries referencing cities outside the local pool (e.g., "food assistance near Flint," "veterans food assistance near Grand Rapids") fall back to Ann Arbor results because the dataset has no indexed records from those areas. This is a coverage gap, not a retrieval error, and it affects all four ablation conditions equally.

**Ypsilanti result saturation.** Even for Ann Arbor queries, Ypsilanti results appear frequently in the top ranks despite the user location being set to Ann Arbor (~8 miles away). This is not a distance scoring error — Ypsilanti is genuinely close and the resources are actionable. The more meaningful explanation is that Ypsilanti has significantly denser resource coverage in the dataset, reflecting the real-world pattern that lower-income areas tend to have more documented social services. The system's results are therefore shaped by where need and infrastructure are concentrated, not just where the user is located. A user in Ann Arbor may receive results that are geographically valid but not representative of what exists in their immediate neighborhood.

**Availability scoring.** The "open now" constraint produces no meaningful signal for ~70% of records due to missing hours data. This caused the full pipeline to occasionally demote highly relevant results that lacked hours information, which the ablation results confirm: semantic-only retrieval, which ignores availability entirely, outperforms the constrained pipeline on P@3 and MRR. The availability signal would need substantially better hours coverage to function as intended.

**Eligibility filtering.** False negatives remain on queries with specific constraints (e.g., "veterans only," "seniors only") because eligibility flags are sparsely populated and often absent from scraped records. A record with no veterans flag is penalized even if it genuinely serves veterans — the flag simply was not present in the source data. The soft multiplier introduced in Section 6.3 mitigated the worst cases but did not resolve the underlying data gap.

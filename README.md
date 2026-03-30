# Local Resource Finder for Housing and Food Insecurity

A constraint-aware local resource finder that combines a structured service index with hybrid lexical-semantic retrieval. Accepts conversational queries like *"food pantry open tonight near me for families"* and returns ranked resource cards surfacing the most decision-critical information up front.

**Team:** Emily Wang, Rhys Burman, Seth Hyslop, Caleb Lee, Tarun Uppuluri

---

## How it works

Queries are mapped to structured intent and constraints (service type, open now, near me, eligibility), then retrieved via BM25 + sentence embeddings, and reranked using a weighted combination of lexical relevance, semantic relevance, proximity, and availability.

```
Query → parse_query → BM25 + Embeddings → merge → rerank → ranked results
```

---

## Project structure

```
resource-finder/
├── data/
│   ├── raw_resources.jsonl              # Seed records (3 examples)
│   ├── normalized_resources.jsonl       # Cleaned, geocoded records for search
│   ├── benchmark_queries.json           # 10 evaluation queries
│   ├── run_results.json                 # Example annotated results
│   ├── annotations_template.json        # Template for relevance annotations
│   └── schema_example.json             # Record schema reference
└── src/
    ├── hybrid_retrieve.py               # Main search entry point
    ├── query_parser.py                  # Intent + constraint extraction
    ├── rerank.py                        # Multi-factor scoring and ranking
    ├── build_bm25.py                    # BM25 lexical index
    ├── build_embeddings.py              # Sentence-transformer embeddings
    ├── normalize_records.py             # Raw → normalized JSONL
    ├── scrape_foodpantries.py           # Scraper: foodpantries.org (Michigan)
    ├── scrape_shelters.py               # Scraper: shelterlistings.org (Michigan)
    ├── fetch_api_resources.py           # API fetcher: 211.org + HUD
    ├── merge_raw.py                     # Merge + deduplicate JSONL sources
    ├── evaluate.py                      # IR metrics (P@K, Recall, MRR, nDCG)
    └── latency_eval.py                  # Retrieval latency benchmarks
```

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Verify the pipeline with seed data

```bash
cd src
python hybrid_retrieve.py
```

Runs a sample query against the 3 included seed records. If results print, the pipeline works.

### 3. Collect real data

**Web scraping (no API keys needed):**

```bash
# Quick test
python scrape_foodpantries.py --cities ann_arbor ypsilanti
python scrape_shelters.py --max-cities 3

# Full Michigan run
python scrape_foodpantries.py
python scrape_shelters.py
```

**API fetching (optional, higher quality):**

Register for free keys first:
- 211 API: https://api.211.org/ → "Request Access"
- HUD API: https://www.huduser.gov/portal/dataset/apidescription.html → "Request a Token"

```bash
export API_211_KEY="your_key"
export HUD_API_KEY="your_key"
python fetch_api_resources.py
```

### 4. Merge and normalize

```bash
python merge_raw.py

python -c "
from normalize_records import normalize_jsonl
normalize_jsonl('../data/raw_resources_merged.jsonl', '../data/normalized_resources.jsonl')
"
```

### 5. Run the search

```bash
python hybrid_retrieve.py
```

Edit the query and coordinates in `hybrid_retrieve.py` lines 48–49 to try different searches.

### 6. Evaluate

```bash
python evaluate.py     # P@3, P@5, Recall@10, MRR, nDCG@5
python latency_eval.py # BM25 / embedding / hybrid latency
```

---

## Data pipeline

```
scrape_foodpantries.py ──┐
scrape_shelters.py       ├──► merge_raw.py ──► normalize_records.py ──► hybrid_retrieve.py
fetch_api_resources.py ──┘                                                      │
raw_resources.jsonl ─────┘                                               evaluate.py
```

Data sources target Michigan cities (Ann Arbor, Ypsilanti, Detroit, Lansing, and more). Each record is normalized into a standard schema with geocoded coordinates, hours, eligibility flags, and source metadata.

---

## Record schema

| Field | Description |
|---|---|
| `resource_id` | Unique identifier |
| `org_name` | Organization name |
| `service_category` | `food_pantry`, `shelter`, and/or `housing_assistance` |
| `description` | Free-text description |
| `address`, `city`, `state`, `zip` | Location fields |
| `lat`, `lon` | Geocoded coordinates |
| `hours_text` | Raw hours string |
| `hours_normalized` | Structured hours by day: `{"mon": [["09:00","17:00"]]}` |
| `eligibility_text` | Raw eligibility description |
| `eligibility_flags` | `family_friendly`, `senior_only`, `veterans_only`, `appointment_required` |
| `phone` | Contact number |
| `source_url` | Original source page |
| `source_type` | `nonprofit_site`, `directory`, `211_api`, `hud_api` |
| `last_verified` | ISO date of last verification |

---

## Ranking

The final score combines four signals:

```
Score = 0.35 · Sem + 0.35 · Lex + 0.20 · Dist + 0.10 · Avail
```

Weights shift when the query includes explicit constraints — `"near me"` increases the distance weight, `"open now"` increases the availability weight. Eligibility constraints (family, seniors, veterans) are applied as hard filters before scoring.

---

## Evaluation

Metrics reported: **P@3**, **P@5**, **Recall@10**, **MRR**, **nDCG@5**

Baselines compared:
1. BM25 only
2. Embeddings only
3. Hybrid (BM25 + embeddings)
4. Hybrid + constraint-aware reranking (full system)

Relevance is annotated on a 3-point scale: `2` = directly usable, `1` = partially useful, `0` = irrelevant.

---

## Dependencies

| Package | Purpose |
|---|---|
| `rank-bm25` | Lexical retrieval |
| `sentence-transformers` | Semantic embeddings (`all-MiniLM-L6-v2`) |
| `geopy` | Address geocoding |
| `beautifulsoup4` + `requests` | Web scraping |
| `scikit-learn`, `numpy` | Score normalization |
| `python-dateutil` | Date/time parsing |

# Local Resource Finder

A constraint-aware local resource finder for food and housing insecurity in Michigan. It builds a structured index of food pantries, emergency shelters, and housing assistance programs from web scraping and OpenStreetMap, then answers conversational queries like *"food pantry open tonight near me for families"* using hybrid BM25 + semantic retrieval with constraint-aware reranking.

**Team:** Emily Wang, Rhys Burman, Seth Hyslop, Caleb Lee, Tarun Uppuluri

---

## Project structure

```
src/
  collect_data.py        # scrape + OSM + geocode
  build_index.py         # merge + normalize -> search index
  search.py              # CLI + load_search_index() + run_search_with_index()
  api.py                 # Flask API server (POST /api/search, GET /api/health)
  hybrid_retrieve.py     # hybrid BM25 + embedding search (with geographic pre-filter)
  rerank.py              # constraint-aware scoring with dynamic radius + distance decay
  query_parser.py        # intent + constraint extraction
  build_bm25.py          # lexical index (with .pkl cache)
  build_embeddings.py    # semantic embeddings (with .npy cache)
  normalize_records.py   # record normalization
  run_benchmark.py       # run all benchmark queries, output results for annotation
  evaluate.py            # IR metrics from annotated run_results.json
  latency_eval.py        # per-component latency benchmarks
  ablation.py            # run 4 retrieval conditions, produce pooled annotation file
  ablation_eval.py       # compute per-condition metrics from annotated ablation pool
web/
  app/page.tsx           # Next.js search UI (proxies /api/* to Flask)
data/
  raw_resources_scraped.jsonl  # scraped food pantry records (foodpantries.org)
  raw_resources_shelters.jsonl # scraped shelter records (shelterlistings.org)
  raw_osm.jsonl                # OpenStreetMap social facilities
  normalized_resources.jsonl   # built index (search reads this)
  benchmark_queries.json       # 30 benchmark queries
  run_results_raw.json         # ranked results with org names, for annotation
  run_results.json             # annotated relevance labels (0/1/2), read by evaluate.py
  ablation_results_raw.json    # ranked lists per condition per query
  ablation_pool.json           # pooled relevance judgments for ablation conditions
  ablation_metrics.json        # per-condition P@3, MRR, nDCG@5
```

---

## Quickstart

**1. Install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Collect data**

```bash
cd src

# All sources (food pantries + shelters + OSM)
python collect_data.py

# Subset of sources for faster testing
python collect_data.py --sources food --cities ann_arbor ypsilanti
python collect_data.py --sources shelters --max-shelter-cities 5
python collect_data.py --sources osm

# Geocode missing coordinates in existing raw files without re-scraping
python collect_data.py --sources geocode

# Skip geocoding (faster, coordinates will be missing for scraped records)
python collect_data.py --skip-geocode
```

**3. Build the index**

```bash
python build_index.py
```

**4. Search (CLI)**

```bash
python search.py "food pantry near me"
python search.py "emergency shelter open tonight"
python search.py "housing help for veterans near ann arbor"
```

**5. Run the web UI**

Start the Flask API and Next.js frontend in separate terminals:

```bash
# Terminal 1 — API (loads index once at startup, ~30s first run)
cd src
python api.py

# Terminal 2 — frontend
cd web
npm install   # first time only
npm run dev
```

Open **http://localhost:3000**. Next.js proxies `/api/*` to the Flask server at `127.0.0.1:5000` automatically — no extra config needed.

---

## Search examples

```bash
python search.py "food pantry open tonight near me for families"
python search.py "emergency shelter near detroit"
python search.py "housing assistance for seniors"
python search.py "free food ypsilanti"
python search.py "somewhere to sleep tonight"
```

Results include organization name, address, distance, hours, eligibility, and phone number.

Optional location override (defaults to Ann Arbor):

```bash
python search.py "food pantry near me" --lat 42.3314 --lon -83.0458  # Detroit
python search.py "food pantry near me" --lat 42.2411 --lon -83.6130  # Ypsilanti
```

---

## How it works

```
Query -> parse_query -> geographic pre-filter -> BM25 + Embeddings -> merge -> rerank -> ranked results
```

1. **parse_query** extracts service intent (`food_pantry`, `shelter`, `housing_assistance`) and constraints (`open_now`, `near_me`, `family_friendly`, `senior_only`, `veterans_only`).
2. **Geographic pre-filter** narrows the document pool to records within a dynamic radius (10 → 20 → 30 miles) before retrieval. Expands outward only if fewer than 5 local results are found, ensuring dense areas return only nearby results.
3. **BM25** scores documents lexically; **sentence-transformers** (`all-MiniLM-L6-v2`) scores them semantically. Both result sets are normalized to [0, 1].
4. **rerank** combines four signals with adaptive weights:

| Signal | Base weight | With `near me` | With `open now` |
|--------|-------------|----------------|-----------------|
| Semantic (sem) | 0.25 | 0.25 | 0.25 |
| Lexical (lex) | 0.25 | 0.25 | 0.25 |
| Distance (dist) | 0.30 | 0.40 | 0.30 |
| Availability (avail) | 0.05 | 0.05 | 0.10 |

Distance uses a steepened decay of `1 / (1 + miles^1.5)`, making a 5-mile result roughly 20× better scored than a 26-mile result. Records without precise coordinates fall back to city-centroid lookup. Eligibility constraints (family, seniors, veterans) are applied as soft multipliers: confirmed matches score 1.0, missing flags score 0.75 (penalized but not excluded — eligibility flag coverage is too sparse to hard-drop results).

---

## Record schema

| Field | Description |
|---|---|
| `resource_id` | Unique identifier |
| `org_name` | Organization name |
| `service_category` | `food_pantry`, `shelter`, and/or `housing_assistance` |
| `description` | Free-text description |
| `address`, `city`, `state`, `zip` | Location fields |
| `lat`, `lon` | Geocoded coordinates (precise or city-centroid fallback) |
| `hours_text` | Raw hours string |
| `hours_normalized` | Structured hours by day: `{"mon": [["09:00", "17:00"]]}` |
| `eligibility_text` | Raw eligibility description |
| `eligibility_flags` | `family_friendly`, `senior_only`, `veterans_only`, `appointment_required` |
| `phone` | Contact number |
| `source_url` | Original source page |
| `source_type` | `directory` or `osm` |
| `last_verified` | ISO date of last verification |

---

## Evaluation

Metrics: **P@3**, **P@5**, **Recall@10**, **MRR**, **nDCG@5**

Relevance is annotated on a 3-point scale: `2` = directly usable, `1` = partially useful, `0` = irrelevant.

```bash
# Run all benchmark queries and generate results for annotation
python run_benchmark.py

# After filling in labels in data/run_results.json:
python evaluate.py     # computes all IR metrics

# Ablation study — compare BM25-only, semantic-only, hybrid, full pipeline
python ablation.py            # runs all 4 conditions, writes ablation_pool.json
# (fill in labels in data/ablation_pool.json)
python ablation_eval.py       # prints per-condition comparison table

# Latency benchmarks (per-component, over local document set)
python latency_eval.py
```

Latest results (Ann Arbor, 30 queries):

| Metric | Score |
|--------|-------|
| P@3 | 0.689 |
| P@5 | 0.693 |
| Recall@10 | 0.833 |
| MRR | 0.778 |
| nDCG@5 | 0.688 |

Ablation (30 queries, same geographic pre-filter across all conditions):

| Condition | P@3 | MRR | nDCG@5 |
|---|---|---|---|
| BM25 only | 0.633 | 0.761 | 0.537 |
| Hybrid (no rerank) | 0.778 | 0.873 | 0.651 |
| Full pipeline | 0.789 | 0.833 | 0.739 |
| Semantic only | 0.900 | 0.933 | 0.760 |

Latency (local doc set, ~53 docs for Ann Arbor):

| Component | Avg (ms) |
|-----------|----------|
| BM25 | 1.26 |
| Embedding | 67.69 |
| Hybrid pipeline | 19.19 |

---

## Dependencies

| Package | Purpose |
|---|---|
| `rank-bm25` | Lexical retrieval |
| `sentence-transformers` | Semantic embeddings (`all-MiniLM-L6-v2`) |
| `flask` + `flask-cors` | REST API server |
| `geopy` | Address geocoding via Nominatim |
| `beautifulsoup4` + `requests` | Web scraping |
| `numpy` | Score normalization and vector ops |
| `scikit-learn` | Utility math |
| `python-dateutil` | Date/time parsing |

"""
Merge all raw JSONL files, deduplicate by resource_id, normalize each record,
and write the search index to data/normalized_resources.jsonl.

No arguments needed — just run it:
    python build_index.py
"""

import difflib
import json
import re
from collections import defaultdict
from pathlib import Path

from normalize_records import normalize_record


def _normalize_name(name: str) -> str:
    """Lowercase and strip punctuation/common suffixes for fuzzy comparison."""
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(
        r'\b(the|of|a|an|inc|llc|ltd|corp|association|assoc|'
        r'church|ministry|ministries|center|centre)\b',
        ' ', name,
    )
    return re.sub(r'\s+', ' ', name).strip()


def _field_count(rec: dict) -> int:
    """Count non-empty fields — used to pick the richer record when merging."""
    return sum(1 for v in rec.values() if v not in (None, "", [], {}))


def _merge_records(primary: dict, secondary: dict) -> dict:
    """Fill any empty fields in primary from secondary. Primary wins on conflicts."""
    merged = dict(primary)
    for key, val in secondary.items():
        if not merged.get(key) and val:
            merged[key] = val
    return merged


def fuzzy_dedup(records: list, threshold: float = 0.85) -> list:
    """
    Within each city, merge records whose normalized org names are at least
    `threshold` similar (SequenceMatcher ratio). The record with more populated
    fields is kept as primary; the other fills in any gaps it has.
    """
    by_city = defaultdict(list)
    for rec in records:
        city = (rec.get("city") or "unknown").lower().strip()
        by_city[city].append(rec)

    result = []
    total_merged = 0
    for group in by_city.values():
        absorbed = set()
        kept = []
        for i, rec_a in enumerate(group):
            if i in absorbed:
                continue
            name_a = _normalize_name(rec_a.get("org_name", ""))
            for j, rec_b in enumerate(group[i + 1:], start=i + 1):
                if j in absorbed:
                    continue
                name_b = _normalize_name(rec_b.get("org_name", ""))
                ratio = difflib.SequenceMatcher(None, name_a, name_b).ratio()
                if ratio >= threshold:
                    absorbed.add(j)
                    total_merged += 1
                    # Keep whichever record has more data as primary
                    if _field_count(rec_b) > _field_count(rec_a):
                        rec_a = _merge_records(rec_b, rec_a)
                    else:
                        rec_a = _merge_records(rec_a, rec_b)
            kept.append(rec_a)
        result.extend(kept)

    if total_merged:
        print(f"  Fuzzy dedup merged {total_merged} near-duplicate record(s)")
    return result

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT = DATA_DIR / "normalized_resources.jsonl"


def main():
    raw_files = sorted(DATA_DIR.glob("raw_*.jsonl"))

    if not raw_files:
        print(f"No raw_*.jsonl files found in {DATA_DIR}")
        print("Run collect_data.py first to generate raw data files.")
        return

    # Merge and deduplicate (first occurrence wins)
    seen = {}  # resource_id -> record
    for path in raw_files:
        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rid = rec.get("resource_id")
                if rid and rid not in seen:
                    seen[rid] = rec
                    count += 1
        print(f"  {path.name}: {count} unique records loaded")

    print(f"\n  Total unique records after resource_id dedup: {len(seen)}")

    # Fuzzy dedup: merge records from different sources that refer to the same org
    records = fuzzy_dedup(list(seen.values()))
    print(f"  Total records after fuzzy dedup: {len(records)}")

    # Normalize and write
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for rec in records:
            norm = normalize_record(rec)
            f.write(json.dumps(norm, ensure_ascii=False) + "\n")

    print(f"  Wrote {len(records)} normalized records -> {OUTPUT}")
    print("\nDone. Run search.py to query the index.")


if __name__ == "__main__":
    main()

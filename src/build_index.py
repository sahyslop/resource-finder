"""
Merge all raw JSONL files, deduplicate by resource_id, normalize each record,
and write the search index to data/normalized_resources.jsonl.

No arguments needed — just run it:
    python build_index.py
"""

import json
from pathlib import Path

from normalize_records import normalize_record

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

    print(f"\n  Total unique records after deduplication: {len(seen)}")

    # Normalize and write
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for rec in seen.values():
            norm = normalize_record(rec)
            f.write(json.dumps(norm, ensure_ascii=False) + "\n")

    print(f"  Wrote {len(seen)} normalized records -> {OUTPUT}")
    print("\nDone. Run search.py to query the index.")


if __name__ == "__main__":
    main()

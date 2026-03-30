"""
Merge multiple raw JSONL files into one, deduplicating by resource_id.

Usage:
    python merge_raw.py                          # uses defaults
    python merge_raw.py --inputs a.jsonl b.jsonl --output merged.jsonl
"""

import argparse
import json

DEFAULT_INPUTS = [
    "../data/raw_resources.jsonl",
    "../data/raw_resources_scraped.jsonl",
    "../data/raw_resources_shelters.jsonl",
    "../data/raw_resources_api.jsonl",
]
DEFAULT_OUTPUT = "../data/raw_resources_merged.jsonl"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=DEFAULT_INPUTS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    seen = {}  # resource_id → record (first occurrence wins)
    for path in args.inputs:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    rid = rec.get("resource_id")
                    if rid and rid not in seen:
                        seen[rid] = rec
        except FileNotFoundError:
            print(f"  skipping missing file: {path}")

    with open(args.output, "w", encoding="utf-8") as f:
        for rec in seen.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Merged {len(seen)} unique records → {args.output}")


if __name__ == "__main__":
    main()

import json

example = {
    "q1": {"ranked_labels": [2, 2, 1, 0, 0]},
    "q2": {"ranked_labels": [2, 1, 0, 0, 0]},
    "q3": {"ranked_labels": [1, 2, 0, 0, 0]},
    "q4": {"ranked_labels": [2, 0, 0, 0, 0]}
}

with open("../data/run_results.json", "w", encoding="utf-8") as f:
    json.dump(example, f, indent=2)

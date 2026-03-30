import re

SERVICE_KEYWORDS = {
    "food_pantry": [
        "food pantry", "food bank", "free food", "groceries", "meal site"
    ],
    "shelter": [
        "shelter", "somewhere to sleep", "place to stay", "overnight shelter", "emergency shelter"
    ],
    "housing_assistance": [
        "housing help", "rent help", "section 8", "voucher", "housing assistance"
    ]
}


def infer_service_categories(query: str):
    q = query.lower()
    labels = []
    for label, phrases in SERVICE_KEYWORDS.items():
        for phrase in phrases:
            if phrase in q:
                labels.append(label)
                break
    return labels


def parse_constraints(query: str):
    q = query.lower()
    return {
        "open_now": any(x in q for x in ["open now", "open tonight", "right now", "tonight"]),
        "near_me": any(x in q for x in ["near me", "nearby", "close"]),
        "family_friendly": any(x in q for x in ["family", "families", "kids", "children"]),
        "senior_only": any(x in q for x in ["senior", "seniors"]),
        "veterans_only": any(x in q for x in ["veteran", "veterans"])
    }


def parse_query(query: str):
    return {
        "raw_query": query,
        "service_categories": infer_service_categories(query),
        "constraints": parse_constraints(query)
    }


if __name__ == "__main__":
    q = "food pantry open tonight near me for families"
    print(parse_query(q))

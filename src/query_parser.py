import re

SERVICE_KEYWORDS = {
    "food_pantry": [
        # direct names
        "food pantry", "food bank", "food shelf", "food closet", "food depot",
        "food distribution", "food cabinet", "community fridge", "little free pantry",
        # descriptive
        "free food", "free groceries", "free meals", "free produce",
        "low cost food", "discounted food",
        # meal programs
        "meal site", "meal program", "soup kitchen", "community kitchen",
        "hot meal", "warm meal", "free meal", "prepared meal",
        "free breakfast", "free lunch", "free dinner", "free supper",
        "breakfast program", "lunch program", "dinner program", "supper program",
        "brown bag", "bag lunch",
        # assistance framing
        "food assistance", "food help", "food support", "food resources",
        "food insecurity", "nutrition assistance", "grocery assistance",
        # natural / conversational
        "hungry", "i'm hungry", "need a meal", "need food", "need something to eat",
        "get food", "find food", "looking for food", "looking for meals",
        "something to eat", "feed my family", "feed myself",
        "can't afford food", "cant afford food", "no food",
        # standalone
        "pantry", "feeding program", "groceries",
    ],
    "shelter": [
        # direct names
        "shelter", "emergency shelter", "overnight shelter", "homeless shelter",
        "warming center", "cooling center", "transitional shelter", "night shelter",
        "drop-in shelter", "low barrier shelter",
        # descriptive
        "place to stay", "place to sleep", "place for the night", "place to go",
        "somewhere to sleep", "somewhere to stay", "somewhere to go",
        "safe place to sleep", "safe place to stay",
        # conversational / urgent
        "need a bed", "need a place", "need somewhere to go",
        "nowhere to sleep", "nowhere to go", "no place to sleep", "no place to stay",
        "sleep tonight", "bed tonight", "overnight stay", "stay tonight",
        "sleeping outside", "living outside", "living on the street",
        "on the street", "unhoused", "unsheltered", "homeless",
        "couch surfing",
    ],
    "housing_assistance": [
        # direct names
        "housing assistance", "housing help", "housing support", "housing program",
        "housing resources", "housing services", "housing aid",
        "rental assistance", "rent assistance", "rent help", "rent relief",
        "emergency rental assistance", "era program",
        "section 8", "housing voucher", "voucher",
        "rapid rehousing", "rapid re-housing",
        "permanent supportive housing", "affordable housing",
        "transitional housing",
        # bills / utilities
        "utility assistance", "utility help", "utility relief",
        "electric bill help", "gas bill help", "water bill help",
        "can't pay rent", "cant pay rent", "behind on rent",
        "cant pay bills", "can't pay bills", "help paying rent",
        "help with rent", "help with bills",
        # eviction / crisis
        "eviction", "eviction help", "eviction prevention", "facing eviction",
        "about to be evicted", "eviction notice",
        "housing crisis", "housing emergency",
        "homelessness prevention", "prevent homelessness",
        # conversational
        "losing my home", "lost my home", "about to lose my home",
        "need a place to live", "finding housing", "find housing",
        "deposit help", "first month rent", "move-in costs",
    ],
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
        "open_now": any(x in q for x in [
            "open now", "open tonight", "right now", "tonight",
            "currently open", "open today", "open right now",
            "open late", "open early", "open this morning",
            "open this afternoon", "open this evening",
            "is it open", "is there one open",
        ]),
        "near_me": any(x in q for x in [
            "near me", "nearby", "close", "closest", "nearest",
            "near here", "around here", "in my area", "in the area",
            "walking distance", "close by", "close to me",
        ]),
        "family_friendly": any(x in q for x in [
            "family", "families", "kids", "children", "child",
            "with kids", "my kids", "my children", "my family",
            "for families", "for kids", "for children",
            "baby", "infant", "toddler",
        ]),
        "senior_only": any(x in q for x in [
            "senior", "seniors", "senior citizen", "senior citizens",
            "elderly", "elders", "older adult", "older adults",
            "for seniors", "for elderly",
            "aging", "aged",
        ]),
        "veterans_only": any(x in q for x in [
            "veteran", "veterans", "vet", "vets",
            "military", "former military", "ex military",
            "armed forces", "service member", "servicemember",
            "for veterans", "for vets",
        ]),
    }


CONSTRAINT_KEYS = (
    "open_now",
    "near_me",
    "family_friendly",
    "senior_only",
    "veterans_only",
)


def merge_ui_constraints(text_constraints: dict, ui: dict | None) -> dict:
    """
    OR-in UI toggles: if the user checks a chip, that constraint is True even
    when their typed query does not mention it.
    """
    if not ui:
        return text_constraints
    out = {**text_constraints}
    for k in CONSTRAINT_KEYS:
        if ui.get(k) is True:
            out[k] = True
    return out


def parse_query(query: str):
    return {
        "raw_query": query,
        "service_categories": infer_service_categories(query),
        "constraints": parse_constraints(query),
    }


if __name__ == "__main__":
    q = "food pantry open tonight near me for families"
    print(parse_query(q))

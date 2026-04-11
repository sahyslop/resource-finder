from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

# Approximate city centroids for Michigan cities commonly in the dataset.
# Used as a fallback when a record has no lat/lon.
MICHIGAN_CITY_COORDS = {
    "ann arbor":       (42.2808, -83.7430),
    "ypsilanti":       (42.2411, -83.6130),
    "detroit":         (42.3314, -83.0458),
    "lansing":         (42.7325, -84.5555),
    "flint":           (43.0125, -83.6875),
    "grand rapids":    (42.9634, -85.6681),
    "kalamazoo":       (42.2917, -85.5872),
    "saginaw":         (43.4195, -83.9508),
    "pontiac":         (42.6389, -83.2910),
    "dearborn":        (42.3223, -83.1763),
    "sterling heights":(42.5803, -83.0302),
    "warren":          (42.5145, -83.0146),
    "muskegon":        (43.2342, -86.2484),
    "battle creek":    (42.3212, -85.1797),
    "jackson":         (42.2459, -84.4013),
    "chelsea":         (42.3181, -84.0194),
    "saline":          (42.1667, -83.7816),
    "dexter":          (42.3375, -83.8863),
    "milan":           (42.0856, -83.6785),
}


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def resource_coords(resource):
    """
    Return (lat, lon) for a resource, falling back to city centroid if the
    record has no precise coordinates.  Returns (None, None) if unknown.
    """
    lat, lon = resource.get("lat"), resource.get("lon")
    if lat is not None and lon is not None:
        return lat, lon
    city = (resource.get("city") or "").lower().strip()
    return MICHIGAN_CITY_COORDS.get(city, (None, None))


def distance_score(resource, user_lat, user_lon):
    lat, lon = resource_coords(resource)
    if lat is None:
        return 0.0
    dist = haversine_miles(user_lat, user_lon, lat, lon)
    return 1.0 / (1.0 + dist ** 1.5)


def is_open_now(resource) -> bool:
    hours = resource.get("hours_normalized", {})
    if not hours:
        return False
    now = datetime.now()
    day = now.strftime("%a").lower()  # mon, tue, wed, thu, fri, sat, sun
    current_time = now.strftime("%H:%M")
    slots = hours.get(day, [])
    return any(start <= current_time <= end for start, end in slots)


def availability_score(resource, parsed_query) -> float:
    if not parsed_query["constraints"].get("open_now"):
        return 0.5
    hours = resource.get("hours_normalized", {})
    if not hours:
        return 0.0  # no hours data — can't confirm open
    return 1.0 if is_open_now(resource) else 0.0


def eligibility_multiplier(resource, parsed_query) -> float:
    """
    Soft eligibility scoring. A confirmed match scores 1.0; a missing flag
    scores 0.75 (penalized but not excluded — flag coverage is too sparse to
    hard-drop results). Penalties stack if multiple constraints are unmet.
    """
    flags = resource.get("eligibility_flags", {})
    constraints = parsed_query["constraints"]
    multiplier = 1.0

    if constraints.get("family_friendly") and not flags.get("family_friendly", False):
        multiplier *= 0.75
    if constraints.get("senior_only") and not flags.get("senior_only", False):
        multiplier *= 0.75
    if constraints.get("veterans_only") and not flags.get("veterans_only", False):
        multiplier *= 0.75

    return multiplier


def staleness_factor(resource) -> float:
    """
    Multiplicative confidence factor based on how recently the record was verified.
    Fresh data scores 1.0; records older than a year are scaled down to 0.7.
    Records with no date get a mild penalty (0.85) for uncertainty.
    """
    last_verified = resource.get("last_verified", "")
    if not last_verified:
        return 0.85
    try:
        verified_date = datetime.fromisoformat(last_verified)
        age_days = (datetime.now() - verified_date).days
        if age_days <= 90:
            return 1.0
        elif age_days <= 180:
            return 0.9
        elif age_days <= 365:
            return 0.8
        else:
            return 0.7
    except (ValueError, TypeError):
        return 0.85


def rerank_candidates(candidates, parsed_query, user_lat=None, user_lon=None):
    reranked = []
    near_me = parsed_query["constraints"].get("near_me", False)
    open_now = parsed_query["constraints"].get("open_now", False)
    has_location = user_lat is not None and user_lon is not None

    for cand in candidates:
        resource = cand["doc"]
        lex = cand.get("lex_score", 0.0)
        sem = cand.get("sem_score", 0.0)

        # For near_me queries, skip records with no resolvable location.
        if has_location and near_me:
            rlat, rlon = resource_coords(resource)
            if rlat is None:
                continue

        # Distance is always a meaningful signal for local services,
        # boosted further when the user explicitly says "near me".
        dist = 0.0
        if has_location:
            dist = distance_score(resource, user_lat, user_lon)

        avail = availability_score(resource, parsed_query)

        w_lex  = 0.25
        w_sem  = 0.25
        w_dist = 0.40 if near_me else 0.30
        w_avail = 0.10 if open_now else 0.05

        base_score = (w_lex * lex) + (w_sem * sem) + (w_dist * dist) + (w_avail * avail)
        final_score = base_score * staleness_factor(resource) * eligibility_multiplier(resource, parsed_query)

        reranked.append({
            "doc": resource,
            "final_score": final_score,
            "lex_score": lex,
            "sem_score": sem,
            "dist_score": dist,
            "avail_score": avail
        })

    reranked.sort(key=lambda x: x["final_score"], reverse=True)
    return reranked

from math import radians, sin, cos, sqrt, atan2
from datetime import datetime


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def distance_score(resource, user_lat, user_lon):
    if resource.get("lat") is None or resource.get("lon") is None:
        return 0.0
    dist = haversine_miles(user_lat, user_lon, resource["lat"], resource["lon"])
    return 1.0 / (1.0 + dist)


def availability_score(resource, parsed_query):
    if not parsed_query["constraints"].get("open_now"):
        return 0.5
    if resource.get("hours_normalized"):
        return 1.0
    return 0.0


def eligibility_filter(resource, parsed_query):
    flags = resource.get("eligibility_flags", {})
    constraints = parsed_query["constraints"]

    if constraints.get("family_friendly") and not flags.get("family_friendly", False):
        return False
    if constraints.get("senior_only") and not flags.get("senior_only", False):
        return False
    if constraints.get("veterans_only") and not flags.get("veterans_only", False):
        return False
    return True


MAX_DISTANCE_MILES = 30


def rerank_candidates(candidates, parsed_query, user_lat=None, user_lon=None):
    reranked = []
    near_me = parsed_query["constraints"].get("near_me", False)
    open_now = parsed_query["constraints"].get("open_now", False)
    has_location = user_lat is not None and user_lon is not None

    for cand in candidates:
        resource = cand["doc"]
        lex = cand.get("lex_score", 0.0)
        sem = cand.get("sem_score", 0.0)

        if not eligibility_filter(resource, parsed_query):
            continue

        # Distance filtering — requires user location to be set.
        resource_has_coords = resource.get("lat") and resource.get("lon")
        if has_location:
            if resource_has_coords:
                # Drop anything beyond 30 miles.
                miles = haversine_miles(user_lat, user_lon, resource["lat"], resource["lon"])
                if miles > MAX_DISTANCE_MILES:
                    continue
            elif near_me:
                # "near me" query but coordinates unknown — can't verify proximity, skip.
                continue

        # Distance is always a meaningful signal for local services,
        # boosted further when the user explicitly says "near me".
        dist = 0.0
        if has_location:
            dist = distance_score(resource, user_lat, user_lon)

        avail = availability_score(resource, parsed_query)

        w_lex  = 0.30
        w_sem  = 0.30
        w_dist = 0.30 if near_me else 0.20
        w_avail = 0.10 if open_now else 0.05

        final_score = (w_lex * lex) + (w_sem * sem) + (w_dist * dist) + (w_avail * avail)

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

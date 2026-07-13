"""India location helpers shared by search, recommendations, and aggregation."""

from __future__ import annotations

import re

REMOTE_INDIA_TERMS = (
    "remote india",
    "india remote",
    "pan india",
    "pan-india",
    "anywhere in india",
    "work from anywhere in india",
)

GLOBAL_REMOTE_TERMS = (
    "worldwide",
    "anywhere",
    "global",
    "remote",
    "fully remote",
    "work from anywhere",
)

FOREIGN_ONLY_TERMS = (
    "united states", "usa", "u.s.", "u.s.a", "us", "us only", "u.s. only",
    "canada", "united kingdom", "u.k.", "uk only", "europe", "emea",
    "singapore", "australia", "germany", "france", "netherlands", "ireland",
    "poland", "spain", "portugal", "brazil", "mexico", "argentina",
    "philippines", "vietnam", "indonesia", "malaysia", "thailand", "japan",
    "china", "korea", "dubai", "uae", "abu dhabi", "saudi", "qatar",
    "nigeria", "kenya", "south africa", "new zealand", "latam", "north america",
)

INDIA_MARKERS = (
    "india", "bharat", "andaman", "andhra pradesh", "arunachal pradesh",
    "assam", "bihar", "chhattisgarh", "delhi", "goa", "gujarat", "haryana",
    "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh",
    "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha",
    "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
    "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "ncr",
    "gurgaon", "gurugram", "noida", "hyderabad", "chennai", "pune",
    "kolkata", "ahmedabad", "jaipur", "kochi", "coimbatore", "indore",
    "chandigarh", "nagpur", "lucknow", "bhubaneswar", "vadodara", "surat",
    "mohali", "mysuru", "visakhapatnam", "vijayawada", "nashik", "rajkot",
    "patna", "bhopal", "madurai", "mangaluru", "varanasi", "jodhpur",
    "raipur", "guwahati", "dehradun", "kanpur", "ludhiana", "agra",
    "meerut", "ranchi", "jabalpur", "gwalior", "vapi", "anand", "jamnagar",
    "aurangabad", "bareilly", "belagavi", "bhavnagar", "bhilai", "cuttack",
    "dhanbad", "durgapur", "faridabad", "gandhinagar", "goa", "gorakhpur",
    "greater noida", "hubballi", "jalandhar", "jamshedpur", "kolhapur",
    "kota", "kozhikode", "navi mumbai", "panipat", "prayagraj", "salem",
    "solapur", "thane", "tiruchirappalli", "udaipur", "vellore", "warangal",
)

UNKNOWN_LOCATION_RE = re.compile(r"\b(unknown|not specified|not disclosed|n/?a)\b", re.I)

CITY_CANON = {
    "bangalore": "Bengaluru",
    "bombay": "Mumbai",
    "madras": "Chennai",
    "calcutta": "Kolkata",
    "gurgaon": "Gurugram",
    "cochin": "Kochi",
    "trivandrum": "Thiruvananthapuram",
    "mysore": "Mysuru",
    "vizag": "Visakhapatnam",
    "mangalore": "Mangaluru",
    "new delhi": "Delhi",
    "allahabad": "Prayagraj",
    "hubli": "Hubballi",
    "tiruchi": "Tiruchirappalli",
}


def _low(value: str | None) -> str:
    return f" {' '.join(str(value or '').strip().lower().split())} "


def _has_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(
        re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text)
        for term in phrases
    )


def is_remote_india(location: str | None, work_arrangement: str | None = None) -> bool:
    text = _low(location)
    if _has_phrase(text, REMOTE_INDIA_TERMS):
        return True
    return (work_arrangement or "").lower() == "remote" and " india " in text


def is_foreign_only(location: str | None) -> bool:
    text = _low(location)
    if not text.strip():
        return False
    has_india = _has_phrase(text, INDIA_MARKERS) or _has_phrase(text, REMOTE_INDIA_TERMS)
    return not has_india and _has_phrase(text, FOREIGN_ONLY_TERMS)


def is_india_or_remote_location(location: str | None, *, allow_named_city: bool = True) -> bool:
    text = _low(location)
    if not text.strip() or UNKNOWN_LOCATION_RE.search(text):
        return False
    if is_foreign_only(location):
        return False
    if _has_phrase(text, REMOTE_INDIA_TERMS):
        return True
    if _has_phrase(text, INDIA_MARKERS):
        return True
    return False


def normalize_india_location(location: str | None) -> str | None:
    if not location:
        return location
    cleaned = " ".join(str(location).split())
    low = cleaned.lower()
    for raw, canon in CITY_CANON.items():
        if re.search(r"\b" + re.escape(raw) + r"\b", low):
            cleaned = re.sub(r"\b" + re.escape(raw) + r"\b", canon, cleaned, flags=re.I)
            low = cleaned.lower()
    return cleaned


def location_matches_preference(
    job_location: str | None,
    desired_locations: list[str],
    *,
    work_arrangement: str | None = None,
) -> bool:
    if is_remote_india(job_location, work_arrangement):
        return True
    text = _low(job_location)
    if not text.strip() or UNKNOWN_LOCATION_RE.search(text):
        return False
    for desired in desired_locations:
        d = _low(desired).strip()
        if not d:
            continue
        if d in {"remote", "remote india", "pan india", "pan-india"}:
            if _has_phrase(text, REMOTE_INDIA_TERMS):
                return True
            continue
        if d in text:
            return True
    return False

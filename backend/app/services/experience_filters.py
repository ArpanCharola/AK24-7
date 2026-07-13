"""Experience-level helpers for job search and recommendations."""

from __future__ import annotations

import re

FRESHER_TERMS = (
    "fresher", "freshers", "entry level", "entry-level", "new grad", "new graduate",
    "graduate engineer", "graduate trainee", "trainee", "associate software",
    "junior", "0-1", "0 - 1", "0 to 1", "0-2", "0 - 2", "0 to 2",
)

ROLE_QUERY_ALIASES = {
    "software developer": [
        "Software Developer",
        "Software Engineer",
        "SDE",
        "Associate Software Engineer",
        "Application Developer",
    ],
    "software engineer": [
        "Software Engineer",
        "Software Developer",
        "SDE",
        "Associate Software Engineer",
        "Graduate Software Engineer",
    ],
    "frontend developer": [
        "Frontend Developer",
        "Front End Developer",
        "React Developer",
        "JavaScript Developer",
        "UI Developer",
    ],
    "front end developer": [
        "Frontend Developer",
        "Front End Developer",
        "React Developer",
        "JavaScript Developer",
        "UI Developer",
    ],
    "fullstack developer": [
        "Fullstack Developer",
        "Full Stack Developer",
        "Full Stack Engineer",
        "MERN Stack Developer",
        "MEAN Stack Developer",
    ],
    "full stack developer": [
        "Full Stack Developer",
        "Fullstack Developer",
        "Full Stack Engineer",
        "MERN Stack Developer",
        "MEAN Stack Developer",
    ],
    "java developer": [
        "Java Developer",
        "Java Software Engineer",
        "Java Backend Developer",
        "Spring Boot Developer",
        "J2EE Developer",
    ],
    "web developer": [
        "Web Developer",
        "Frontend Developer",
        "React Developer",
        "JavaScript Developer",
        "PHP Developer",
    ],
    "ai/ml engineer": [
        "AI ML Engineer",
        "AI Engineer",
        "Machine Learning Engineer",
        "ML Engineer",
        "Generative AI Engineer",
    ],
    "ai engineer": [
        "AI Engineer",
        "AI ML Engineer",
        "Machine Learning Engineer",
        "ML Engineer",
        "Generative AI Engineer",
    ],
    "machine learning engineer": [
        "Machine Learning Engineer",
        "ML Engineer",
        "AI ML Engineer",
        "AI Engineer",
    ],
}

MID_SENIOR_TERMS = (
    "senior", "sr.", "sr ", "lead", "principal", "staff engineer", "architect",
    "manager", "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "smts", "lmts", "senior member of technical staff", "lead member of technical staff",
)

EXPLICIT_EXP_RE = re.compile(
    r"\b([3-9]|1[0-9])\s*\+?\s*(?:years?|yrs?)\b|"
    r"\b([3-9]|1[0-9])\s*(?:to|-)\s*([4-9]|1[0-9])\s*(?:years?|yrs?)\b",
    re.I,
)


def normalize_experience(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if text in {"fresher", "freshers", "entry", "entry_level", "entry-level", "0", "0-1", "0-2"}:
        return "fresher"
    if text in {"junior", "1-2", "1-3", "early"}:
        return "junior"
    if text in {"mid", "midlevel", "mid-level", "3-5"}:
        return "mid"
    if text in {"senior", "lead", "5+"}:
        return "senior"
    return None


def experience_from_months(months: int | None) -> str:
    value = months or 0
    if value <= 12:
        return "fresher"
    if value <= 36:
        return "junior"
    if value <= 72:
        return "mid"
    return "senior"


def experience_from_user(user) -> str:
    months = (user.experience_years or 0) * 12 + (user.experience_months or 0)
    return experience_from_months(months)


def is_experience_match(title: str | None, description: str | None, experience: str | None) -> bool:
    level = normalize_experience(experience)
    if not level:
        return True
    text = f"{title or ''} {description or ''}".lower()
    if level == "fresher":
        if any(term in text for term in MID_SENIOR_TERMS) or EXPLICIT_EXP_RE.search(text):
            return False
        return True
    if level == "junior":
        if any(term in text for term in ("lead", "principal", "staff engineer", "architect", "manager")):
            return False
        if re.search(r"\b([5-9]|1[0-9])\s*\+?\s*(?:years?|yrs?)\b", text, re.I):
            return False
        return True
    if level == "mid":
        return not any(term in text for term in ("principal", "staff engineer", "architect"))
    return True


def fresher_search_roles(role: str, experience: str | None) -> list[str]:
    """Return search-query variants instead of one over-constrained query.

    Google Jobs/JobSpy behave much better with a few normal queries than with
    a single "role fresher entry level junior graduate trainee" string.
    """
    cleaned = role.strip()
    if not cleaned:
        return []
    aliases = ROLE_QUERY_ALIASES.get(cleaned.lower(), [cleaned])
    if normalize_experience(experience) != "fresher":
        return list(dict.fromkeys(aliases))
    if any(term in cleaned.lower() for term in ("fresher", "entry", "graduate", "trainee", "junior")):
        return [cleaned]
    variants: list[str] = [*aliases]
    for alias in aliases:
        variants.append(f"{alias} fresher")
    for alias in aliases:
        variants.append(f"{alias} entry level")
    for alias in aliases:
        variants.append(f"{alias} junior")
    for alias in aliases:
        variants.append(f"{alias} graduate trainee")
    return list(dict.fromkeys(variants))


def fresher_search_role(role: str, experience: str | None) -> str:
    roles = fresher_search_roles(role, experience)
    return roles[0] if roles else role

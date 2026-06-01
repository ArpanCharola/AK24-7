import re
from app.services.resume_tailor import _generate, _parse_json

_SKILLS = [
    "python", "javascript", "typescript", "java", "golang", "go", "rust",
    "c++", "c#", "ruby", "php", "scala", "kotlin", "swift", "r", "matlab",
    "react", "vue", "angular", "next.js", "node.js", "express", "fastapi",
    "django", "flask", "spring", "rails", "laravel", "asp.net", "svelte",
    "machine learning", "deep learning", "nlp", "natural language processing",
    "computer vision", "pytorch", "tensorflow", "keras", "pandas", "numpy",
    "scikit-learn", "spark", "hadoop", "kafka", "airflow", "dbt",
    "llm", "generative ai", "langchain", "openai", "hugging face", "transformers",
    "data science", "data engineering", "data analysis", "business intelligence",
    "prompt engineering", "rag", "fine-tuning", "embeddings", "vector database",
    "pinecone", "weaviate", "chromadb", "qdrant",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "cassandra", "dynamodb", "snowflake", "bigquery", "redshift", "clickhouse",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
    "ci/cd", "jenkins", "github actions", "gitlab ci", "linux", "bash",
    "rest", "graphql", "grpc", "microservices", "serverless", "event-driven",
    "distributed systems", "system design",
    "product management", "project management", "agile", "scrum",
]

_LEVEL_MAP = {"entry": 1, "mid": 2, "senior": 3, "staff": 4}

_EXPERIENCE_RE = [
    (re.compile(r"\b(0[\s\-]+[12]|1[\s\-]+[23])\s*years?\b", re.IGNORECASE), "entry"),
    (re.compile(r"\b(junior|entry[\s-]level|new\s+grad|associate\b|fresher|freshers)", re.IGNORECASE), "entry"),
    (re.compile(r"\b([23][\s\-]+[45]|4[\s\-]+[56])\s*years?\b", re.IGNORECASE), "mid"),
    (re.compile(r"\bmid[\s-]level\b", re.IGNORECASE), "mid"),
    (re.compile(r"\b(5\+?|6\+?|7\+?|8\+?)\s*years?\b", re.IGNORECASE), "senior"),
    (re.compile(r"\b(senior|sr\.?\s|lead\b|principal\b|staff\b)", re.IGNORECASE), "senior"),
    (re.compile(r"\b(director\s+of|vp\s+of|distinguished|fellow\b)", re.IGNORECASE), "staff"),
]

_BUSINESS_ROLE_RE = re.compile(
    r"\b(account executive|sales|presales|marketing|campaign|growth|customer success|recruiter|talent|finance|accounting|legal|hr|human resources)\b",
    re.IGNORECASE,
)
_PRODUCT_ROLE_RE = re.compile(r"\bproduct manager\b", re.IGNORECASE)
_MANAGER_ROLE_RE = re.compile(r"\b(engineering manager|head of|director|vp|vice president|chief)\b", re.IGNORECASE)
_AI_TERMS_RE = re.compile(
    r"\b(ai|a\.i\.|ml|m\.l\.|machine learning|artificial intelligence|llm|genai|generative ai|agentic)\b",
    re.IGNORECASE,
)
_TECH_ROLE_RE = re.compile(
    r"\b(engineer|engineering|developer|scientist|research|architect|platform|infrastructure|software|data)\b",
    re.IGNORECASE,
)


def _extract_skills(text: str) -> set[str]:
    text_lower = text.lower()
    return {
        skill for skill in _SKILLS
        if re.search(r"\b" + re.escape(skill) + r"\b", text_lower)
    }


def _detect_jd_level(jd: str) -> str | None:
    for pattern, level in _EXPERIENCE_RE:
        if pattern.search(jd):
            return level
    return None


def _score_experience(jd_level: str | None, candidate_level: str) -> int:
    if not jd_level or not candidate_level:
        return 10
    diff = abs(_LEVEL_MAP.get(jd_level, 2) - _LEVEL_MAP.get(candidate_level, 2))
    return {0: 20, 1: 12, 2: 4}.get(diff, 0)


class JobScorer:
    async def score(self, job_description: str, user_profile: dict, job_title: str = "") -> dict:
        career = user_profile.get("career_history") or ""
        resume = user_profile.get("resume_text") or ""
        experience_level = (user_profile.get("experience_level") or "").lower().strip()
        target_roles = user_profile.get("target_roles") or ""
        candidate_text = f"{career}\n{resume}".strip()

        if not candidate_text:
            return {
                "score": 0,
                "reason": "No candidate profile to score against.",
                "explanation": "No candidate profile to score against.",
                "missing_skills": [],
            }

        jd_skills = _extract_skills(job_description)
        candidate_skills = _extract_skills(candidate_text)

        if jd_skills:
            matched = jd_skills & candidate_skills
            skills_pts = int((len(matched) / len(jd_skills)) * 40)
        else:
            matched = set()
            skills_pts = 20

        jd_level = _detect_jd_level(job_description)
        exp_pts = _score_experience(jd_level, experience_level)

        llm_explanation = ""
        llm_missing: list[str] = []

        # Skip LLM when there's no job description — scoring on title alone wastes API quota
        # and produces noise. Fall back to title-only heuristics instead.
        if not job_description.strip():
            title_lower = job_title.lower()
            candidate_lower = candidate_text.lower()
            # Simple title word overlap as a proxy for role alignment
            title_words = set(re.findall(r"\b[a-z]{3,}\b", title_lower)) - {
                "the", "and", "for", "with", "this", "that", "are", "has", "have"
            }
            candidate_words = set(re.findall(r"\b[a-z]{3,}\b", candidate_lower))
            overlap = title_words & candidate_words
            llm_pts = min(40, len(overlap) * 4) if title_words else 20
            llm_reason = "Scored on job title only (no job description available)"
            llm_explanation = llm_reason
        else:
            system = (
                "You are a senior ATS expert and technical recruiter. "
                "Score a candidate's overall fit for a role. "
                "Focus on: role alignment, relevant experience, skill depth, industry match. "
                "Be strict - overqualified and underqualified both score lower. "
                "Reply with JSON only: "
                '{"score": <integer 0-40>, '
                '"reason": "<one sentence>", '
                '"explanation": "<2-3 sentences: why this candidate fits the role and the single biggest gap>", '
                '"missing_skills": ["<skill or requirement the candidate is missing>", ...]}'
            )
            prompt = (
                f"JOB TITLE:\n{job_title[:300]}\n\n"
                f"JOB DESCRIPTION:\n{job_description[:1800]}\n\n"
                f"CANDIDATE BACKGROUND:\n{candidate_text[:1800]}\n\n"
                f"Note: skills match already computed as {skills_pts}/40. "
                "Score 0-40 for role alignment, industry fit, and experience depth. "
                "In missing_skills, list concrete skills/requirements from the JD the candidate lacks (empty list if none)."
            )

            raw = await _generate(system, prompt, max_tokens=300)
            parsed = _parse_json(raw)

            try:
                llm_pts = max(0, min(40, int(parsed.get("score", 20))))
            except (TypeError, ValueError):
                llm_pts = 20
            llm_reason = str(parsed.get("reason", ""))
            llm_explanation = str(parsed.get("explanation", "")).strip()
            raw_missing = parsed.get("missing_skills") or []
            if isinstance(raw_missing, list):
                llm_missing = [str(m).strip() for m in raw_missing if str(m).strip()]
            elif raw_missing:
                llm_missing = [str(raw_missing).strip()]

        title = (job_title or "").strip().lower()
        ai_focused = bool(_AI_TERMS_RE.search(target_roles.lower()))
        ai_title = bool(_AI_TERMS_RE.search(title))
        tech_title = bool(_TECH_ROLE_RE.search(title))
        title_penalty = 0
        if ai_focused and ai_title:
            if _BUSINESS_ROLE_RE.search(title) and not tech_title:
                title_penalty += 28
            if _PRODUCT_ROLE_RE.search(title):
                title_penalty += 18
            if _MANAGER_ROLE_RE.search(title) and "manager" not in candidate_text.lower():
                title_penalty += 12

        total = max(0, min(100, skills_pts + exp_pts + llm_pts - title_penalty))

        regex_missing = sorted(jd_skills - candidate_skills) if jd_skills else []
        if jd_skills:
            skill_line = (
                f"Skills: {len(matched)}/{len(jd_skills)} matched"
                + (f" (gaps: {', '.join(regex_missing[:3])})" if regex_missing else " (all covered)")
            )
        else:
            skill_line = "No explicit skills listed in JD"

        reason = f"{skill_line}. {llm_reason}".strip()
        if title_penalty:
            reason += f" Title relevance penalty applied ({title_penalty} pts) due to role-function mismatch."
        if not reason.endswith("."):
            reason += "."

        # Merge regex-derived gaps (from our skill taxonomy) with the LLM's free-form
        # gaps, de-duped case-insensitively, regex skills first.
        missing_skills: list[str] = []
        seen: set[str] = set()
        for skill in [*regex_missing, *llm_missing]:
            key = skill.lower()
            if skill and key not in seen:
                seen.add(key)
                missing_skills.append(skill)
        missing_skills = missing_skills[:8]

        explanation = llm_explanation or reason

        return {
            "score": total,
            "reason": reason,
            "explanation": explanation,
            "missing_skills": missing_skills,
        }

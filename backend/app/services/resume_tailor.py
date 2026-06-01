import asyncio
import json
import logging
import random
import re
import httpx

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
# gpt-4.1: stronger instruction-following + structured-JSON reliability than
# gpt-4o, and vision-capable so the same constant drives the Set-of-Marks
# screenshot fill. Drives scoring, tailoring, cover letters, and form-filling.
_OPENAI_MODEL = "gpt-4.1"

# Shared concurrency cap — protects against discovery loops firing 50+
# parallel scoring calls into OpenAI's rate limit. Applies process-wide.
_LLM_SEMAPHORE = asyncio.Semaphore(5)

_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.5  # seconds; doubled each attempt with jitter


async def _generate(
    system_prompt: str, user_prompt: str, max_tokens: int = 1024, model: str = _OPENAI_MODEL
) -> str:
    from app.config import settings
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    async with _LLM_SEMAPHORE:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(_OPENAI_URL, headers=headers, json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        "OpenAI %s — retrying in %.1fs (attempt %d/%d)",
                        resp.status_code, delay, attempt + 1, _MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    last_exc = RuntimeError(f"OpenAI API returned {resp.status_code}")
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as exc:
                logger.error("OpenAI API error %s: %s", exc.response.status_code, exc.response.text)
                raise RuntimeError(f"OpenAI API returned {exc.response.status_code}") from exc
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "OpenAI network error %s — retrying in %.1fs (attempt %d/%d)",
                    exc, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                last_exc = exc

        raise RuntimeError("OpenAI API exhausted retries") from last_exc


async def _generate_vision(
    system_prompt: str,
    user_prompt: str,
    image_b64: str,
    max_tokens: int = 800,
    detail: str = "high",
) -> str:
    """Like `_generate`, but sends a base64 JPEG/PNG image alongside the text so
    gpt-4o can *see* the page (used for screenshot/Set-of-Marks form filling).

    Shares the same semaphore + retry/backoff envelope as `_generate`.
    """
    from app.config import settings
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _OPENAI_MODEL,  # gpt-4o is vision-capable
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                            "detail": detail,
                        },
                    },
                ],
            },
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    async with _LLM_SEMAPHORE:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(_OPENAI_URL, headers=headers, json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        "OpenAI vision %s — retrying in %.1fs (attempt %d/%d)",
                        resp.status_code, delay, attempt + 1, _MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    last_exc = RuntimeError(f"OpenAI API returned {resp.status_code}")
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as exc:
                logger.error("OpenAI vision error %s: %s", exc.response.status_code, exc.response.text[:300])
                raise RuntimeError(f"OpenAI API returned {exc.response.status_code}") from exc
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "OpenAI vision network error %s — retrying in %.1fs (attempt %d/%d)",
                    exc, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                last_exc = exc

        raise RuntimeError("OpenAI vision API exhausted retries") from last_exc


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"raw": text}


class ResumeTailor:
    async def extract_keywords(self, job_description: str) -> dict:
        system = (
            "You are an ATS expert. Extract structured data from job descriptions. "
            "Respond with a single JSON object containing keys: "
            "required_skills, preferred_skills, years_experience, deal_breakers, keywords. "
            "Output only the JSON — no explanation."
        )
        result = await _generate(system, f"Job Description:\n\n{job_description}", max_tokens=512)
        return _parse_json(result)

    async def tailor_resume(
        self, resume: str, job_description: str, career_history: str
    ) -> str:
        system = (
            "You are an expert resume writer specializing in ATS optimization. Your job is to "
            "TAILOR an existing resume to a target job description — not to rewrite it from "
            "scratch, summarize it, or shorten it.\n\n"
            "Rules:\n"
            "- Preserve ALL of the candidate's real content: every job/employer, job title, "
            "date range, education entry, certification, and project in the original resume "
            "must remain in the output. Never drop, merge, or omit experiences, and never cut "
            "entire sections.\n"
            "- Keep the resume's overall structure, section headings, and approximate length. "
            "The tailored resume should be roughly as long as the original — not a condensed "
            "summary.\n"
            "- Tailor by REFRAMING, not removing: reorder and rephrase bullet points to "
            "emphasize the experience and skills most relevant to the job description, mirror "
            "the job's terminology, and weave in matching keywords naturally where they are "
            "truthful.\n"
            "- You may lightly de-emphasize less-relevant bullets, but do NOT delete the "
            "roles, education, or sections they belong to.\n"
            "- The candidate's resume (and career history, if provided) is the source of "
            "truth. Use only information grounded in it. Never fabricate, exaggerate, or "
            "invent employers, titles, dates, metrics, or skills.\n"
            "- ATS formatting (critical): single-column, plain-text layout only — NO tables, "
            "text boxes, columns, images, icons, or page headers/footers. Use standard, "
            "ATS-recognised section headings (Summary, Skills, Experience, Education, "
            "Projects, Certifications). Spell an acronym out once with the acronym in "
            "parentheses, then reuse the acronym. Keep one consistent date format. Mirror the "
            "job description's exact keyword phrasing wherever it is truthful so the resume "
            "clears keyword screens.\n"
            "- India conventions: this is the Indian market — use Indian English, and express "
            "any compensation, CTC, or salary figures in INR / LPA (lakhs per annum), never "
            "USD. Do not introduce salary figures that are not already in the source.\n"
            "- Output ONLY the finished resume text, preserving a clean, readable layout "
            "(section headings, role headers with company and dates, and bullet points)."
        )
        history_block = (
            f"Additional Career History (supporting context only):\n{career_history}\n\n"
            if career_history and career_history.strip()
            else ""
        )
        user = (
            f"Job Description:\n{job_description}\n\n"
            f"{history_block}"
            "Original Resume — preserve ALL of this content and tailor it to the job above:\n"
            f"{resume}"
        )
        return await _generate(system, user, max_tokens=4096)

    async def draft_custom_answer(self, question: str, career_history: str) -> str:
        system = (
            "You draft concise, honest answers to job application questions based solely "
            "on the candidate's actual career history. Do not invent facts. "
            "Output only the answer text, 2-4 sentences."
        )
        user = f"Career History:\n{career_history}\n\nQuestion:\n{question}"
        return await _generate(system, user, max_tokens=256)

    async def draft_cover_letter(
        self,
        job_description: str,
        company: str,
        role: str,
        career_history: str,
    ) -> str:
        system = (
            "You write tailored, professional cover letters. "
            "Ground every claim in the candidate's actual career history — do not invent "
            "achievements, employers, or skills. "
            "Three to four short paragraphs. Open with genuine interest in the specific role "
            "and company. Middle: two or three concrete examples from career history that map "
            "to the job's requirements. Close with a forward-looking line and a call to talk. "
            "Do not include letterhead, dates, addresses, or 'Dear Hiring Manager' boilerplate — "
            "just the body. Output only the letter text."
        )
        user = (
            f"Company: {company or '(unknown)'}\n"
            f"Role: {role or '(unspecified)'}\n\n"
            f"Job Description:\n{job_description}\n\n"
            f"Candidate Career History:\n{career_history}"
        )
        return await _generate(system, user, max_tokens=900)

    async def tailor_from_profile(self, profile: dict, job_description: str) -> str:
        """Tailor a resume starting from the user's STRUCTURED base profile.

        The profile dict is the shape produced by ``resume_parser`` (contact,
        summary, work_experience, education, skills, projects, certifications).
        We render it into clean resume text, then run it through the same
        grounded, ATS-aware tailoring as ``tailor_resume`` so the base profile is
        the single source of truth and nothing is fabricated.
        """
        base_resume = profile_to_resume_text(profile)
        return await self.tailor_resume(base_resume, job_description, "")

    def score_ats(self, resume: str, keywords: dict) -> dict:
        """Deterministic ATS keyword-coverage score against extracted keywords.

        ``keywords`` is the dict from ``extract_keywords`` (required_skills,
        preferred_skills, keywords). Returns coverage over the union of those
        terms plus the subset of *required* skills still missing — the signal
        that most threatens an ATS pass. No AI call; pure string matching.
        """
        required = _as_terms(keywords.get("required_skills"))
        preferred = _as_terms(keywords.get("preferred_skills"))
        general = _as_terms(keywords.get("keywords"))

        all_terms = _dedupe_terms(required + preferred + general)
        resume_low = (resume or "").lower()

        matched, missing = [], []
        for term in all_terms:
            (matched if _term_present(term, resume_low) else missing).append(term)

        required_missing = [
            t for t in _dedupe_terms(required) if not _term_present(t, resume_low)
        ]
        coverage_pct = round(100 * len(matched) / len(all_terms)) if all_terms else 0
        return {
            "coverage_pct": coverage_pct,
            "matched": matched,
            "missing": missing,
            "required_missing": required_missing,
        }


# ── Structured profile → resume text ──────────────────────────────────────────

def _join_nonempty(parts: list, sep: str = " · ") -> str:
    return sep.join(p for p in (str(x).strip() for x in parts if x) if p)


def profile_to_resume_text(profile: dict) -> str:
    """Render a structured profile dict into clean, ATS-friendly resume text."""
    if not isinstance(profile, dict):
        return ""
    lines: list[str] = []

    contact = profile.get("contact") or {}
    name = contact.get("full_name")
    if name:
        lines.append(str(name).strip())
    contact_line = _join_nonempty([
        contact.get("email"), contact.get("phone"), contact.get("location"),
        contact.get("linkedin_url"), contact.get("github_url"), contact.get("website_url"),
    ])
    if contact_line:
        lines.append(contact_line)

    summary = (profile.get("summary") or "").strip()
    if summary:
        lines += ["", "SUMMARY", summary]

    skills = [s for s in (profile.get("skills") or []) if isinstance(s, str) and s.strip()]
    if skills:
        lines += ["", "SKILLS", ", ".join(s.strip() for s in skills)]

    work = profile.get("work_experience") or []
    if work:
        lines += ["", "EXPERIENCE"]
        for job in work:
            if not isinstance(job, dict):
                continue
            header = _join_nonempty([job.get("title"), job.get("company"), job.get("location")])
            dates = _join_nonempty([job.get("start_date"), job.get("end_date")], sep=" – ")
            if header or dates:
                lines.append(_join_nonempty([header, dates], sep="  |  ") or header)
            for bullet in job.get("bullets") or []:
                if isinstance(bullet, str) and bullet.strip():
                    lines.append(f"- {bullet.strip()}")

    education = profile.get("education") or []
    if education:
        lines += ["", "EDUCATION"]
        for ed in education:
            if not isinstance(ed, dict):
                continue
            degree = _join_nonempty([ed.get("degree"), ed.get("field")], sep=", ")
            header = _join_nonempty([degree, ed.get("institution")], sep=" — ")
            dates = _join_nonempty([ed.get("start_date"), ed.get("end_date")], sep=" – ")
            tail = _join_nonempty([dates, ed.get("grade")])
            line = _join_nonempty([header, tail], sep="  |  ")
            if line:
                lines.append(line)

    projects = profile.get("projects") or []
    if projects:
        lines += ["", "PROJECTS"]
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            tech = proj.get("tech")
            tech_str = ", ".join(t for t in tech if isinstance(t, str)) if isinstance(tech, list) else None
            header = _join_nonempty([proj.get("name"), proj.get("url")], sep="  ")
            if header:
                lines.append(header)
            desc = _join_nonempty([proj.get("description"), tech_str], sep=" | ")
            if desc:
                lines.append(f"- {desc}")

    certs = profile.get("certifications") or []
    if certs:
        lines += ["", "CERTIFICATIONS"]
        for cert in certs:
            if not isinstance(cert, dict):
                continue
            line = _join_nonempty([cert.get("name"), cert.get("issuer"), cert.get("year")], sep=" — ")
            if line:
                lines.append(f"- {line}")

    return "\n".join(lines).strip()


# ── ATS keyword matching helpers ──────────────────────────────────────────────

def _as_terms(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t.strip() for t in value if isinstance(t, str) and t.strip()]


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen, out = set(), []
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _term_present(term: str, resume_low: str) -> bool:
    """True if a keyword is covered by the resume.

    Whole-term substring match first; for multi-word terms, fall back to every
    significant word appearing somewhere (order-independent), which catches
    rephrasings like "REST APIs" vs "RESTful API design".
    """
    t = term.lower().strip()
    if not t:
        return False
    if t in resume_low:
        return True
    words = [w for w in re.split(r"[\s/]+", t) if len(w) > 2]
    if len(words) > 1:
        return all(w in resume_low for w in words)
    return False

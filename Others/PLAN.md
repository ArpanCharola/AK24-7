# AK24/7Jobs — India Job-Search Platform (Free-First, Jobright-class)

## Context

`d:\Code1\aiapply` is a full-stack USA job-application automation system (FastAPI + async SQLAlchemy + Postgres + Celery/Redis backend; React 19 + Vite + Tailwind frontend; OpenAI gpt-4o for all AI). We are **pivoting this same repo to India-only** and rebranding to **AK24/7Jobs** — aiming to be the best single-place job-search product in India, modeled on Jobright.ai (resume → ranked matches with explainable fit → tailored resume → tracking → AI copilot).

The product goes **free-first**: no SerpAPI, no Apify, no paid job APIs. Job links come from (1) free public **company ATS APIs**, (2) **free aggregator APIs / feeds** (TimesJobs RSS, Jooble, remote feeds), and (3) **all-in direct scraping** of the big Indian boards (isolated & best-effort so it never breaks the pipeline). Staffing/recruitment firms are aggressively filtered out.

A **new Google Cloud project "AK24/7Jobs"** (separate from the currently-linked `333124990520-…` project) provides Google Sign-In + Gmail API (read/label/send). Core job-search + resume features need no Google access; Gmail features are gated behind a per-user "Connect Gmail" consent.

**Outcome:** an India-only platform that, from a user's resume, discovers and ranks real job links across many free sources, explains why each fits, produces ATS-optimized tailored resumes (from pasted JD or a job URL), tracks applications via Gmail with accurate lifecycle labeling, and offers an AI career copilot + referral/contact finder.

---

## Confirmed decisions

| Decision | Choice |
|---|---|
| Codebase | Pivot in place — India-only; strip USA discovery, reuse the rest |
| Core product | Resume-driven job-link discovery + ranking (no autonomous submission in v1) |
| Cost model | **Free-first** — no SerpAPI/Apify/Adzuna/paid APIs |
| Sources (triangulated) | **Tier 1** public ATS (Greenhouse/Lever/SmartRecruiters/Ashby/Workday-CXS/…) + **Tier 2** official feeds (TimesJobs RSS, Jooble, remote feeds) + **Tier 3** all-in scraping (Instahyre/Hirist/Cutshort/JobSpy/Naukri/Google, isolated & toggleable) |
| Staffing firms | Aggressively filtered out (blocklist + heuristics) |
| Vertical | **Tech/IT first** (ATS feeds are tech-heavy → fastest great UX) |
| Jobright extras | **Explainable why-fit**, **Orion-style AI copilot chat**, **referral/contact finder** (autofill extension = future stretch) |
| Build phasing | **Everything together** — core + Gmail in one pass |
| Auth | Email/password **and** Google Sign-In |
| Google project | New "AK24/7Jobs" Google Cloud project (Gmail read/label/send) |
| Scale | Build clean for **public SaaS later** (CASA verification + multi-tenant ready) |
| Brand | AK24/7Jobs |
| Prod domain | TBD — localhost for dev now |

---

## Source architecture (free-first — triangulated across 3 research passes, 2025-2026)

Reconciled from deep-research (25 claims verified) + DeepSeek + Gemini reports. The legal, reliable backbone is **public ATS endpoints + official feeds**; scraping the big boards is real but legally risky for a commercial product, so it's an isolated, toggleable tier (user chose all-in).

**TIER 1 — Public ATS endpoints (rely-on; free, no auth, clean direct-employer links, lowest risk). The foundation.**
- **Greenhouse** — `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (Swiggy, Nykaa, Dream11, Ola Electric, CRED).
- **Lever** — `api.lever.co/v0/postings/{company}?mode=json`, native filtering (Zomato, PhonePe, Meesho, Zerodha, Urban Company).
- **SmartRecruiters** — `api.smartrecruiters.com/v1/companies/{id}/postings?country=India` (verified live).
- **Ashby** — `api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` (structured salary; Zepto, startups).
- **Workable** — `workable.com/api/accounts/{subdomain}?details=true`. **Recruitee** — `{company}.recruitee.com/api/offers/`. **Breezy** — `{company}.breezy.hr/json`. **Personio** — `{company}.jobs.personio.de/xml` (XML).
- **Workday CXS** — `POST {tenant}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` + `/siteMap.xml`. No auth. Key for Indian conglomerates/GCCs (Tata, Reliance).
- **Zoho Recruit** — unauthenticated per-employer XML feed.
- **Skip:** Darwinbox (SHA512 client-key gated), Keka (OAuth; only undocumented HTML embed → best-effort), iCIMS (partner-auth), Freshteam (discontinued).

**TIER 2 — Official free feeds/APIs (rely-on; legal, low maintenance).**
- **TimesJobs RSS** — `timesjobs.com/candidate/rssfeed.html?keyword=...&location=...`. Official, pan-India, near-zero maintenance.
- **Jooble** — RapidAPI free tier (~500k req/mo, instant GUID key). Verify traffic-back ToS before making core.
- **Remote roles:** Remotive, RemoteOK (24h delay), Himalayas (`country=IN`, remote-only, backlink + no-repost ToS).
- **Adzuna** — only for **salary benchmarking** within free/14-day window (commercial bulk prohibited).

**TIER 3 — Full scraping, ALL-IN (enabled in production, isolated & best-effort; failures degrade to `[]`).** Max coverage, accepting ToS/anti-bot/legal risk + residential-proxy + stealth-browser infra cost.
- **Cleaner targets:** Instahyre (Algolia POST → clean JSON), Hirist/IIMJobs (internal JSON), Cutshort (JSON-LD), Internshala/Shine (HTML).
- **Library-driven:** JobSpy (`python-jobspy` for Indeed `country_indeed=in` + Google + LinkedIn; `jobspy-node` fork adds Naukri). `ever-jobs` = heavyweight alt.
- **Advanced:** Naukri `/jobapi/v1` (`nkparam` + residential proxies), Google Jobs `udm=8&gl=in` (stealth-Playwright).
- **Avoid:** LinkedIn direct (bans/litigation), Foundit/Wellfound (Cloudflare), Apna (mobile-only).

**Anti-staffing filter (all tiers):** extend `_STAFFING_RE` with Indian staffing/RPO blocklist (TeamLease, Quess, Randstad India, ABC Consultants, IKYA, Adecco India, ManpowerGroup) + heuristics ("consultancy", "staffing", "manpower", "RPO", "hiring for our client", "on behalf of our client"). Tier 1 feeds are direct employers → inherently clean.

**Legal note — ACKNOWLEDGED RISK:** scraping major boards violates ToS (cf. *hiQ v. LinkedIn*); user chose all-in. Mitigations: per-source toggles + circuit-breakers, residential proxy rotation + TLS-impersonation/stealth-Playwright, per-user-search-driven (not mass redistribution), aggressive caching. Tier 1+2 = reliable backbone; Tier 3 = high-yield-but-fragile. Revisit before public launch.

**Tier-3 infra requirement:** residential proxy provider + headless-browser workers (Playwright stealth) for Naukri/Google/LinkedIn — recurring cost + maintenance to budget for.

---

## Feature set

**Core (resume → jobs):** discovery across all tiers (dedupe by canonical URL); AI match score (0–100) via `job_scorer.py`; **explainable why-fit** (why you fit + what's missing); ATS-optimized **tailored resume** from JD or job URL + ATS coverage score; application tracker (manual + Gmail-derived); daily curated digest via Gmail send.

**Jobright-class extras:** **Orion AI copilot chat** (fit breakdown, interview prep, resume advice); **referral/contact finder** (likely contacts + draft outreach, free sources).

**Future stretch:** autofill browser extension.

---

## Implementation phases

### Phase 0 — Google Cloud project "AK24/7Jobs" (user sets up; wire env)
Create project (Gmail API + People API; consent External; scopes `openid`, `userinfo.email`, `userinfo.profile`, `gmail.modify`, `gmail.send`; Web OAuth client; redirect URIs `localhost:8000/api/email/callback` + `/api/auth/google/callback`). Populate `backend/.env`: `GOOGLE_PROJECT_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. ⚠️ Restricted Gmail scopes → CASA before public launch; Testing mode (≤100 users) for dev.

### Phase 1 — India discovery engine (free sources)
- `backend/app/agents/job_discovery_agent.py`: delete USA filters; add `_is_india_location()`, `_normalize_india_location()`, `_parse_lpa()`, `_parse_notice_period()`; extend `_STAFFING_RE`; keep "fresher".
- **Tier 1**: `backend/app/data/india_company_slugs.json` + `_load_india_slugs()`; fetchers in `backend/app/agents/ats_sources.py` (Greenhouse, Lever, SmartRecruiters, Ashby, Workable, Recruitee, Breezy, Personio XML, Workday CXS, Zoho XML). Seed Indian employers; verification script to prune dead slugs.
- **Tier 2**: `backend/app/services/jobs_aggregators.py` — TimesJobs RSS (always-on), Jooble (RapidAPI), remote feeds; Adzuna salary-only.
- Remove SerpAPI (`serpapi_jobs.py`, `SERPAPI_KEY`); drop Careerjet (session-bound).
- **Tier 3**: `backend/app/agents/scrape_sources.py` — Instahyre (Algolia), Hirist/IIMJobs (JSON), Cutshort (JSON-LD), Internshala/Shine (HTML), JobSpy wrapper, Naukri `/jobapi/v1`, Google `udm=8`. `backend/app/agents/proxy_pool.py` + scraping worker queue. Per-source toggle + circuit-breaker.
- `backend/app/services/query_builder.py` — `build_search_queries(profile, resume_text)` via `_generate()`; cache on `JobSearchProfile.generated_queries`.
- Orchestrator `discover()`: fan out, dedupe by URL, India + anti-staffing filters, parse LPA/notice.

### Phase 2 — Data model + migration
- `discovered_job.py`: add `salary_lpa`, `salary_raw`, `notice_period`, `match_explanation`, `missing_skills`. `source` stays free-form String.
- `job_search_profile.py`: add `min_salary_lpa`, `max_notice_period_days`, `generated_queries`; deprecate USA auto-apply columns (leave in place).
- `job_pool.py`: mirror salary/notice. `tailored_resume.py`: add `job_url`.
- Alembic: one revision off current head, `batch_alter_table` add-column, all nullable.

### Phase 3 — Match score + explainable why-fit
- `job_scorer.py`: extend `_generate()` call to also return `{explanation, missing_skills}`; add "fresher" to experience regex. Populate `match_explanation`/`missing_skills` at upsert in `tasks.py`. Dashboard card shows score + why-fit + missing skills + LPA + notice.

### Phase 3b — Rich Profile + resume-import autofill (base resume)
- Structured profile model (extend `user.py` / new profile tables): contact, summary, work experience, education, skills, projects, certifications, links, India fields (current/expected CTC LPA, notice period, preferred locations, work auth). Keep raw `resume_text`/`career_history`.
- `backend/app/services/resume_parser.py`: upload resume → extract text → `_generate()` parse into structured schema → user reviews/edits before save.
- Manual entry: same schema, field-by-field editors.
- API `profile.py`: `POST /profile/import-resume`, `PUT /profile`. Frontend `Profile.jsx`: import + manual editors (TanStack Query).

### Phase 4 — Tailored resume (base profile + JD text OR job URL)
- Start from base profile/resume; customize to JD (pasted) or job link → extracted JD.
- `backend/app/services/jd_extractor.py`: `fetch_url_text` (httpx → Playwright fallback), `extract_jd_from_text` via `_generate()`, `jd_from_url` + cache.
- `resume_tailor.py`: tailor from structured profile; add `score_ats(resume, keywords)`; strengthen ATS formatting + INR/LPA.
- `tailored_resumes.py`: `QuickTailorRequest` + `job_url`; auto-extract; `ats_score` in detail; `POST /tailored-resumes/extract-jd`.
- Frontend `TailoredResumes.jsx`: base-resume picker + "Paste JD | Job link" toggle + Fetch-JD preview + ATS badge + missing-keyword chips + edit-before-render.

### Phase 5 — Gmail / Labels / Applications (build + improve)
- Wire AK24/7Jobs OAuth; add Google Sign-In login route (`/api/auth/google/callback`).
- `email_classifiers.py`: India `_AGGREGATOR_DOMAINS`/`_ASSESSMENT_DOMAINS`/`_ATS_DOMAINS`; Indian-English phrases gated by job-context; India line in verify prompts.
- `application_tracker.py`: add `CTC|notice period|LPA|candidature|in-hand` to `_JOB_CONTEXT`; `EMI|UPI|KYC|PAN|Aadhaar|insurance` to `_NON_JOB_APPLICATION`.
- `gmail_labels.py`: keep `AI Apply/*` label IDs stable (ADD-only). Gate Gmail features behind per-user "Connect Gmail".

### Phase 6 — Orion AI copilot chat
- `backend/app/api/routes/copilot.py` + `backend/app/services/copilot.py`: chat over `_generate()` with context = profile + optional focused `DiscoveredJob` (explain fit, interview prep, skill-gap). Optional `CopilotMessage` persistence.
- Frontend `Copilot.jsx` chat UI + nav.

### Phase 7 — Referral / contact finder
- Repurpose `contact_finder.py` to free sources (drop Apify): domain email patterns + public team/careers pages → likely contacts + draft outreach via `_generate()`. Surface on job detail.

### Phase 8 — Branding, config, scheduling, digest
- `config.py` `APP_NAME` → "AK24/7Jobs"; frontend copy; currency → INR/LPA.
- `backend/.env.example`: add `GOOGLE_PROJECT_ID`, optional `JOOBLE_RAPIDAPI_KEY`, optional `ADZUNA_*` (salary only), Tier-3 toggles (default false), `SCRAPE_PROXIES`, JD-fetch knobs. Remove `SERPAPI_KEY`, `APIFY_*`, `PROXY_*`. Keep `OPENAI_API_KEY`, `ENCRYPTION_KEY`, `EMAIL_SEND_DRYRUN`, `RESUME_FORMATTER_PATH`.
- `CORS_ORIGINS`/`FRONTEND_URL` → localhost now.
- Celery: re-enable `scheduled_discovery` (4h); add `daily_job_digest` (top-N via `gmail_send`, opt-in, ~7:30 IST).

---

## Critical files
- **Discovery:** `agents/job_discovery_agent.py`, `agents/ats_sources.py` (new), `services/jobs_aggregators.py` (new), `agents/scrape_sources.py` (new), `agents/proxy_pool.py` (new), `data/india_company_slugs.json` (new), `services/query_builder.py` (new), `workers/tasks.py`, `workers/celery_app.py`, `requirements.txt`.
- **Match/why-fit:** `services/job_scorer.py`.
- **Profile + base resume:** `models/user.py` (+ profile tables), `services/resume_parser.py` (new), `api/routes/profile.py`, `pages/Profile.jsx`.
- **Tailored resume:** `services/jd_extractor.py` (new), `services/resume_tailor.py`, `api/routes/tailored_resumes.py`, `pages/TailoredResumes.jsx`, `services/api.js`.
- **Gmail/Labels/Apps:** `services/{email_classifiers,application_tracker,gmail_client,gmail_labels}.py`, login route.
- **Copilot:** `api/routes/copilot.py` (new), `services/copilot.py` (new), `pages/Copilot.jsx` (new).
- **Referral:** `services/contact_finder.py`.
- **Models/migration:** `models/{discovered_job,job_search_profile,job_pool,tailored_resume}.py` + Alembic revision.
- **Config:** `config.py`, `.env.example`.

## Reused as-is
`gmail_service.py`/`gmail_send.py`, `gmail_labels.py` (ADD-only), `resume_builder.py` (DOCX→PDF), `core/auth.py` (JWT), `core/encryption.py` (Fernet), Greenhouse/Lever/Ashby fetchers, React/TanStack/Tailwind shell, WebSocket/Redis progress.

## Scale-ready notes
Gmail features opt-in + isolated; begin Google OAuth verification + CASA before public launch; respect free-tier limits (cache + cap); Tier-3 scrapers stay best-effort + toggleable.

## Verification (end-to-end)
1. OAuth/login + Connect-Gmail stores encrypted refresh token; `/api/email/status` shows `can_label`/`can_send`.
2. Discovery: Tech/IT profile + India cities → rows from Tier1/Tier2 (+Tier3), deduped, with LPA/notice, no staffing, ranked.
3. Why-fit on each match. 4. Resume from URL → extract → tailor → ATS score → PDF. 5. Copilot fit breakdown. 6. Referral finder. 7. Lifecycle: Naukri/LinkedIn digests not counted; confirmations advance stage; ADD-only labels. 8. `alembic upgrade head` then `downgrade` clean. 9. Run app + smoke flows.

## Open follow-ups (non-blocking)
Finalize prod domain (https redirect URIs + CORS); CASA timeline; decide copilot conversation persistence; autofill extension (future).
# A1 — Discovery (India job-discovery engine)

Owner: Discovery Engineer. Status file for stream A1. **Last updated: 2026-05-31.**

## Checklist
- [x] Tier 1 `ats_sources.py` — Greenhouse, Lever, SmartRecruiters, Ashby, Workable, Recruitee, Breezy, Personio XML, Workday CXS, Zoho XML
- [x] `india_company_slugs.json` — real Indian employers, LIVE-VERIFIED seed
- [x] Tier 2 `jobs_aggregators.py` — TimesJobs RSS, Jooble, remote feeds (Remotive/RemoteOK/Himalayas)
- [x] Tier 3 `scrape_sources.py` — python-jobspy wrapper (isolated + per-source toggles)
- [x] `query_builder.py` — `build_search_queries(profile, resume_text)` via `_generate`
- [x] `job_discovery_agent.py` — India filters + `discover_for_profile`
- [x] Isolated adapter tests + full `discover()` integration test (invariants hold)

## Current state — DONE (pending Foundation integration)
End-to-end run verified live (2026-05-31): a Tech profile over Bengaluru returned
**216 India-only jobs** from 6 live sources (greenhouse 72, lever 67, workday 51,
remoteok 20, remotive 4, himalayas 2) — `340 raw → 325 deduped → 216 India/clean`.
Invariants asserted green: **0 non-India rows, 0 staffing/excluded rows, 0 duplicate
canonical URLs, 0 out-of-band salaries.** Tier-3 (`TIER3_ENABLED=false`) correctly
returned []. All adapters return the exact contract-#3 dict shape (validated key-set).

## Files delivered (stream A1 only — no other files touched)
- `backend/app/agents/job_discovery_agent.py` (rewritten: India)
- `backend/app/agents/ats_sources.py` (new — Tier 1)
- `backend/app/services/jobs_aggregators.py` (new — Tier 2)
- `backend/app/agents/scrape_sources.py` (new — Tier 3)
- `backend/app/services/query_builder.py` (new)
- `backend/app/data/india_company_slugs.json` (new)

## Contracts honored
- Every adapter returns the normalized job dict (#3): `job_url,title,company,location,
  job_description,source,work_arrangement,posted_at,salary_lpa,salary_raw,notice_period`.
- `discover_for_profile(profile_id, user_id) -> list[dict]` (#4) — loads JobSearchProfile
  + User, builds/caches queries on `generated_queries`, sets `last_run_at`, fans out.
- Imports `_generate` / `_parse_json` from `app.services.resume_tailor` (#1).
- Reads new columns `min_salary_lpa` / `max_notice_period_days` / `generated_queries`
  (already present on the model — Foundation migration landed).

## Live-verified vs assumed (probed 2026-05-31 from build sandbox)
**VERIFIED LIVE (HTTP 200 + correct shape + India roles where noted):**
- **Greenhouse** `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` — seeds
  all live: phonepe (73, 54 India), tekion (46, 39 India), groww (15/15), postman (109),
  druva (27/13), narvar (14), slice (73).
- **Lever** `api.lever.co/v0/postings/{slug}?mode=json` — meesho (50/47 India),
  mindtickle (30/25), fampay (21/21), zeta (25/17), cred (7/7), epifi (4/4). NOTE: Lever
  rate-limits concurrent bursts → adapter sleeps 0.3s between slugs.
- **Ashby** `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` — boards
  resolve 200 for atlan/navi/scaler/sarvam/composio/spotdraft/nirvana (Indian startups);
  **0 open postings at probe time** but endpoints valid (will populate when they hire).
- **SmartRecruiters** `api.smartrecruiters.com/v1/companies/{id}/postings` — endpoint+shape
  verified (Visa → totalFound 16). ⚠️ The `?country=India` filter is unreliable (returns 0
  even for employers with India offices), so the adapter fetches all postings and lets the
  downstream `_is_india_location` filter. Seed IDs (Visa/Bosch/PublicisSapient) are valid IDs
  but India counts vary; **needs better Indian SmartRecruiters company IDs to be high-yield.**
- **Workable** `apply.workable.com/api/v1/widget/accounts/{sub}?details=true` — shape verified
  (`{name,description,jobs}`); seeded Indian accounts (instahyre/whatfix/medibuddy/ultrahuman/
  fitterfly/springworks/invideo) all resolve 200 but had 0 open at probe time.
- **Workday CXS** — VERIFIED LIVE during integration run: nvidia/intel/salesforce tenants all
  POST 200 and returned 82 jobs total (India roles filtered downstream). Seed entries need
  `{subdomain,tenant,site}`; guessed site names 422 (so only confirmed tenants are seeded).
- **Remotive** `remotive.com/api/remote-jobs?search=` — 200, shape verified.
- **RemoteOK** `remoteok.com/api` — 200 (item[0] is a legal notice, skipped), shape verified.
- **Himalayas** `himalayas.app/jobs/api` — 200, shape verified.

**ASSUMED / NOT FULLY VERIFIED (adapter is shape-correct & defensive, seed thin):**
- **Breezy** `{sub}.breezy.hr/json` — squadstack 200 (0 open); several other subdomains
  Cloudflare-403. Adapter works; seed minimal.
- **Recruitee** `{sub}.recruitee.com/api/offers/` — format correct; no Indian customers found
  (all candidates 404). Seed empty — populate if Indian Recruitee employers surface.
- **Personio** `{sub}.jobs.personio.de/xml` — EU-heavy; not probed for India. Adapter parses XML
  defensively. Seed empty.
- **Zoho Recruit** — no single canonical public endpoint; adapter is declarative (reads an
  explicit `feed_url` per seed entry and parses RSS/XML). Seed empty until real feeds collected.
- **TimesJobs RSS** `timesjobs.com/candidate/rssfeed.html?keyword=&location=` — **could NOT be
  reached from the build sandbox (ConnectError — geo/network block, NOT a 404).** Documented URL
  used; adapter is defensive (→ []). **Foundation/integration must re-verify from an India-
  reachable host.**
- **Jooble** `POST jooble.org/api/{key}` — needs `JOOBLE_API_KEY`; not exercisable without a key.
  Adapter returns [] when key is empty.

## Requests for Foundation
**pip packages (DO NOT edit requirements.txt myself):**
- `python-jobspy` — REQUIRED for Tier 3 (naukri/indeed/linkedin/google/glassdoor). Not installed
  in venv; `scrape_sources` imports it lazily and degrades to [] when absent, so nothing breaks
  before it's added — but Tier 3 yields nothing until installed.
- (feedparser NOT needed — RSS/XML parsed with stdlib `xml.etree`.)

**config.py settings (DO NOT edit config.py myself).** Code reads all of these via
`getattr(settings, NAME, default)`, so it runs correctly before they land. Please add:
- `JOOBLE_API_KEY: str = ""`  (empty → Jooble skipped)
- `TIER3_ENABLED: bool = False`  (master gate for all scraping)
- `SCRAPE_INDEED: bool = True`, `SCRAPE_GOOGLE: bool = True`,
  `SCRAPE_NAUKRI: bool = False`, `SCRAPE_LINKEDIN: bool = False`, `SCRAPE_GLASSDOOR: bool = False`
- `SCRAPE_PROXIES: str = ""`  (comma-separated residential proxies for jobspy)

## Heads-up for Foundation / other streams (cross-file fallout of the USA→India rewrite)
Per the plan I deleted the USA discovery surface from `job_discovery_agent.py`
(`_is_usa_location`, the USA `_is_excluded_job` gov logic, SerpAPI/portal/iCIMS/custom-site
paths). All cross-module imports of the *generic* helpers I kept
(`_matches_criteria`, `_detect_work_arrangement`, `_is_within_days`, `_strip_html`,
`_parse_iso`) still resolve, so `serpapi_jobs.py` and `portal_adapters.py` remain importable
and **the app still boots** (their imports are lazy). However:
- `api/routes/public_jobs.py` lazily imports `_is_usa_location` (2 call sites) — those legacy
  USA public-search endpoints will raise ImportError **when called**. They belong to the USA
  product and should be removed/reworked for India by their owner.
- `_is_excluded_job` is kept but is now India-aware (staffing/RPO + internships; no US-gov).
  `public_jobs.py` also imports it — still works, just India-flavored.
- `quick_ats_search` is kept and repurposed to the India slug list (Greenhouse+Lever+Ashby).
- `serpapi_jobs.py` / `portal_adapters.py` are USA-tier files the PLAN says to delete — not mine
  to remove; flagging for Foundation cleanup.

## Notes
- Salary parsing (`_parse_lpa`) only trusts structured `salary_raw` or description text with an
  explicit comp cue (CTC/salary/package/per annum/LPA), and clamps to ₹1L–₹2Cr p.a. — this killed
  a false positive where a loan-recovery "₹60 Cr" was misread as 6000 LPA.
- Remote feeds are global; `_is_india_location` keeps India + global-remote ("worldwide/anywhere/
  remote") and drops region-locked foreign roles ("US only", "EU only", "Remote, US", etc.).

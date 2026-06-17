"""Live smoke test for every Tier-3 job source.

Runs each enabled adapter once for a sample role + Indian city and prints the
job count + one sample row per source, so you can confirm at a glance which
boards are returning data and which are blocked/dormant. Does NOT touch the DB.

Usage (from backend/):
    venv/Scripts/python.exe scripts/verify_sources.py "Software Engineer" "Bengaluru"

Tier-3 must be enabled (TIER3_ENABLED=true in .env, or the script forces it on
in-process so you can test without editing .env).
"""

import asyncio
import os
import sys

# Make the `app` package importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

# Force the master gate on for the duration of this test run only.
settings.TIER3_ENABLED = True


def _sample(jobs: list[dict]) -> str:
    if not jobs:
        return "—"
    j = jobs[0]
    return f"{j.get('title')} @ {j.get('company') or '?'} | {j.get('location') or '?'} | {j.get('salary_raw') or 'salary n/a'}"


async def main(query: str, location: str) -> None:
    from app.agents.india_board_sources import fetch_instahyre, fetch_cutshort
    from app.agents.wellfound_source import fetch_all_wellfound
    from app.agents.hirect_source import fetch_all_hirect
    from app.agents.scrape_sources import fetch_all_scraped

    queries, locations = [query], [location]
    print(f"\nVerifying Tier-3 sources for query={query!r} location={location!r}\n" + "=" * 64)

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
        # Custom adapters (run individually so one block doesn't hide the rest).
        checks = [
            ("instahyre", fetch_instahyre(client, queries, locations)),
            ("cutshort", fetch_cutshort(client, queries, locations)),
            ("wellfound", fetch_all_wellfound(queries, locations)),
            ("hirect", fetch_all_hirect(client, queries, locations)),
        ]
        for name, coro in checks:
            try:
                jobs = await coro
                print(f"{name:<11} {len(jobs):>3} jobs   {_sample(jobs)}")
            except Exception as exc:  # noqa: BLE001
                print(f"{name:<11}  ERR        {type(exc).__name__}: {exc}")

    # jobspy boards (Indeed/Google/Naukri/LinkedIn/Glassdoor) — slower, network-heavy.
    print("-" * 64)
    print("jobspy boards (Indeed/Google/Naukri/LinkedIn/Glassdoor) — may take a minute...")
    try:
        jobspy_jobs = await fetch_all_scraped(queries, locations)
        by_src: dict[str, int] = {}
        for j in jobspy_jobs:
            by_src[j["source"]] = by_src.get(j["source"], 0) + 1
        print(f"jobspy total {len(jobspy_jobs)} jobs   by source: {by_src or '—'}")
    except Exception as exc:  # noqa: BLE001
        print(f"jobspy       ERR        {type(exc).__name__}: {exc}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Software Engineer"
    loc = sys.argv[2] if len(sys.argv) > 2 else "Bengaluru"
    asyncio.run(main(q, loc))

"""One-shot smoke test for Tier-2 portal adapters.

Run from the backend/ directory:
    venv\\Scripts\\python.exe smoke_portals.py

Prints the count of jobs each adapter returned for a generic "Software
Engineer" query. 0 from a portal = endpoint is stale or schema drifted —
needs adapter tuning.
"""
import asyncio
import httpx

from app.agents.portal_adapters import PORTAL_ADAPTERS


PROFILE = {
    # With SDE expansions wired into _RAW_SYNONYMS, "Software Engineer"
    # should now also match "Software Development Engineer" titles (Amazon).
    "target_roles": "Software Engineer, Machine Learning Engineer",
    "work_arrangements": "",
    "posted_within_days": None,
}


async def main() -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for adapter in PORTAL_ADAPTERS:
            try:
                jobs = await adapter(client, PROFILE, None)
                preview = jobs[0]["title"] if jobs else "—"
                preview_url = jobs[0]["job_url"] if jobs else "—"
                print(f"{adapter.__name__:25s} {len(jobs):>4d}  | {preview[:60]:60s} | {preview_url[:80]}")
            except Exception as exc:
                print(f"{adapter.__name__:25s} ERR   | {exc}")


if __name__ == "__main__":
    asyncio.run(main())

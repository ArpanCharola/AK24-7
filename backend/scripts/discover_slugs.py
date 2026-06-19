"""CLI for the slug-discovery pipeline.

  python scripts/discover_slugs.py                 # full wave (curated + seed + Common Crawl)
  python scripts/discover_slugs.py --no-cc         # skip Common Crawl (curated + seed only)
  python scripts/discover_slugs.py --max 400       # cap probes this run
  python scripts/discover_slugs.py --revalidate    # re-probe existing registry slugs

Run from the backend/ directory with the venv python so `app` is importable.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# Quiet the per-slug adapter chatter during big probe waves.
logging.getLogger("app.agents.ats_sources").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Discover/validate India ATS slugs.")
    parser.add_argument("--no-cc", action="store_true", help="skip the Common Crawl harvest")
    parser.add_argument("--cc-limit", type=int, default=800, help="CC results per pattern")
    parser.add_argument("--max", type=int, default=1200, help="max (ats,slug) probes this run")
    parser.add_argument("--revalidate", action="store_true", help="re-probe existing registry instead of discovering")
    parser.add_argument("--batch", type=int, default=300, help="revalidation batch size")
    args = parser.parse_args()

    from app.scripts.slug_discovery import run_discovery, revalidate_registry

    if args.revalidate:
        stats = await revalidate_registry(batch=args.batch)
    else:
        stats = await run_discovery(
            use_common_crawl=not args.no_cc,
            cc_limit_per_pattern=args.cc_limit,
            max_validations=args.max,
        )
    print("RESULT:", stats)


if __name__ == "__main__":
    asyncio.run(_main())

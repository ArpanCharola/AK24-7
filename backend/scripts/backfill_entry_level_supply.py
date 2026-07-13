"""Backfill entry-level India tech jobs into JobPool.

Usage from the backend container or backend folder:
    python scripts/backfill_entry_level_supply.py --days 7
    python scripts/backfill_entry_level_supply.py --roles "Software Developer,AI/ML Engineer"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.entry_level_supply import backfill_entry_level_supply  # noqa: E402


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", help="Comma-separated roles. Defaults to core entry-level tech roles.")
    parser.add_argument("--locations", help="Comma-separated locations. Defaults to India, Remote India.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-roles", type=int, default=None)
    parser.add_argument("--stealth", action="store_true", help="Enable browser-backed sources such as Wellfound.")
    args = parser.parse_args()

    result = await backfill_entry_level_supply(
        roles=_split_csv(args.roles),
        locations=_split_csv(args.locations),
        posted_within_days=args.days,
        max_roles=args.max_roles,
        use_stealth=args.stealth,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())

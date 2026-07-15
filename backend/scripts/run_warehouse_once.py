"""Run one authoritative warehouse aggregation from a deployed container.

Usage:
    python scripts/run_warehouse_once.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.aggregation import run_aggregation  # noqa: E402


async def main() -> None:
    result = await run_aggregation(trigger="manual")
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") not in {"succeeded", "partial"}:
        raise SystemExit(1)
    if int(result.get("accepted_unique") or 0) <= 0:
        raise SystemExit("Warehouse run completed without accepting any jobs.")


if __name__ == "__main__":
    asyncio.run(main())

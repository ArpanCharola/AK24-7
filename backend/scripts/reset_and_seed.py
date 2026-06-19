"""One-time: wipe ALL existing users (and their data) and seed the admin.

DESTRUCTIVE. Run from the backend/ directory:

    .\\venv\\Scripts\\python.exe -m scripts.reset_and_seed

`TRUNCATE users ... CASCADE` clears the users table and every table that has a
foreign key referencing it (applications, job searches, discovered jobs,
resumes, cover letters, sent emails, saved applications). The shared job_pool is
left intact. After wiping, ensure_admin() recreates the admin account.
"""
import asyncio

from sqlalchemy import text

from app.core.bootstrap import ensure_admin
from app.core.database import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    print("All users (and their related data) wiped.")
    await ensure_admin()
    print("Admin account seeded.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
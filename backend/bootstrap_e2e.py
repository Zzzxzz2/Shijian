"""Create deterministic users for the extended E2E regression."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import hash_password
from database import engine
from models import User

USERS = [
    ("e2e_user", "TestPass123!", "user"),
    ("e2e_editor", "Pass123!", "user"),
    ("e2e_viewer", "Pass123!", "user"),
    ("e2e_stranger", "Pass123!", "user"),
    ("e2e_admin", "Admin123!", "admin"),
    ("e2e_u2", "Pass123!", "user"),
]

async def main():
    async with AsyncSession(engine) as s:
        for uname, pwd, role in USERS:
            user = (await s.execute(select(User).where(User.username == uname))).scalar_one_or_none()
            if user is None:
                s.add(User(username=uname, password_hash=hash_password(pwd), role=role))
            else:
                user.password_hash = hash_password(pwd)
                user.role = role
        await s.commit()
        print("Users created:", [u[0] for u in USERS])

asyncio.run(main())

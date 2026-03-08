"""Initialize the database tables."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aime.config import settings
from aime.deps import engine
from aime.models import Base


async def init():
    os.makedirs("data", exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库初始化完成。")


if __name__ == "__main__":
    asyncio.run(init())

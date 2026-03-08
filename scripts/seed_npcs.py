"""Seed NPC entities into the database."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aime.config import settings
from aime.core.memory_layer import MemoryLayer
from aime.core.npc_seeds import NPC_SEEDS
from aime.deps import async_session, engine, get_chroma
from aime.models import Base
from aime.models.entity import Entity
from aime.models.feed import Feed
from aime.utils.id_gen import gen_short_id


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    memory = MemoryLayer(get_chroma())

    async with async_session() as db:
        for npc in NPC_SEEDS:
            # Check if already exists
            from sqlalchemy import select
            result = await db.execute(
                select(Entity).where(Entity.name == npc["name"])
            )
            if result.scalar_one_or_none():
                print(f"  跳过 {npc['name']}（已存在）")
                continue

            entity = Entity(
                name=npc["name"],
                core_belief=npc["core_belief"],
                intent=npc["intent"],
                is_npc=True,
            )
            db.add(entity)
            await db.flush()

            # Process feeds
            for i, feed_text in enumerate(npc.get("feeds", [])):
                feed = Feed(
                    entity_id=entity.id,
                    raw_text=feed_text,
                    source_label=f"NPC初始化-{i+1}",
                )
                db.add(feed)
                await db.flush()

                chunk_count = memory.ingest(
                    entity_id=entity.id,
                    feed_id=feed.id,
                    text=feed_text,
                    source_label=f"NPC初始化-{i+1}",
                )
                feed.chunk_count = chunk_count
                feed.processed = True
                entity.total_feeds += 1

            print(f"  创建 NPC：{npc['name']}（{entity.total_feeds} 条投喂）")

        await db.commit()

    print("\nNPC 种子数据已就绪。")


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    asyncio.run(seed())

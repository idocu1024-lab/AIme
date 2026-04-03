import asyncio
import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from aime.api.router import api_router
from aime.config import settings
from aime.deps import engine
from aime.models import Base
from aime.ws.handler import ws_endpoint

logger = logging.getLogger("aime.scheduler")


async def _seed_sages():
    """Auto-seed sage NPCs on startup if they don't exist yet."""
    from sqlalchemy import select

    from aime.core.memory_layer import MemoryLayer
    from aime.core.npc_seeds import NPC_SEEDS, SAGE_SEEDS
    from aime.deps import async_session, get_chroma
    from aime.models.entity import Entity
    from aime.models.feed import Feed

    memory = MemoryLayer(get_chroma())
    all_seeds = NPC_SEEDS + SAGE_SEEDS
    created = 0

    async with async_session() as db:
        for npc in all_seeds:
            result = await db.execute(
                select(Entity).where(Entity.name == npc["name"])
            )
            if result.scalar_one_or_none():
                continue

            entity = Entity(
                name=npc["name"],
                core_belief=npc["core_belief"],
                intent=npc["intent"],
                is_npc=True,
            )
            db.add(entity)
            await db.flush()

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

            created += 1
            logger.info(f"创建圣人 NPC：{npc['name']}")

        await db.commit()

    if created:
        logger.info(f"自动创建了 {created} 个 NPC 念体。")


async def _run_daily_cycle():
    """Scheduled job: run daily cycle for all entities."""
    from aime.core.daily_cycle import DailyCycle
    from aime.core.llm import get_llm
    from aime.core.memory_layer import MemoryLayer
    from aime.deps import async_session, get_chroma

    logger.info("开始每日结算...")
    memory = MemoryLayer(get_chroma())
    cycle = DailyCycle(memory, get_llm())
    async with async_session() as db:
        count = await cycle.run_all(db)
    logger.info(f"每日结算完成，处理 {count} 个念体。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Data dirs are already validated writable by config._pick_data_dir()
    # Just ensure they exist (safe since config already confirmed writability)
    os.makedirs(os.path.dirname(settings.database_url.split(":///", 1)[1]), exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Auto-seed NPC sages
    await _seed_sages()

    # Start scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_daily_cycle,
        "cron",
        hour=settings.daily_cycle_hour_utc,
        id="daily_cycle",
        name="每日结算",
    )
    scheduler.start()
    logger.info(f"调度器已启动。每日结算时间：UTC {settings.daily_cycle_hour_utc}:00")

    yield

    scheduler.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)

# WebSocket
app.add_api_websocket_route("/ws", ws_endpoint)

# Static files (frontend)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aime.main:app", host="0.0.0.0", port=8000, reload=settings.debug)

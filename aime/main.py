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
    # Ensure data directories exist BEFORE DB init
    os.makedirs("data", exist_ok=True)
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

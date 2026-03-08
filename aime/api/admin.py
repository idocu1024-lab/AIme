"""Admin API endpoints for dashboard and manual operations."""

import json

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.daily_cycle import DailyCycle
from aime.core.llm import get_llm
from aime.core.memory_layer import MemoryLayer
from aime.deps import async_session, get_chroma
from aime.models.daily_log import DailyLog
from aime.models.entity import Entity
from aime.models.feed import Feed
from aime.models.fusion import FusionSnapshot
from aime.models.player import Player
from aime.models.social_event import SocialEvent

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _check_key(key: str):
    if key != settings.admin_key:
        raise HTTPException(status_code=403, detail="无效的管理员密钥")


@router.get("/dashboard")
async def dashboard(key: str = Query(...)):
    _check_key(key)
    async with async_session() as db:
        # Counts
        player_count = (await db.execute(select(func.count(Player.id)))).scalar() or 0
        entity_count = (await db.execute(select(func.count(Entity.id)))).scalar() or 0
        npc_count = (await db.execute(
            select(func.count(Entity.id)).where(Entity.is_npc == True)
        )).scalar() or 0

        # All entities with details
        result = await db.execute(
            select(Entity).order_by(Entity.fusion_total.desc())
        )
        entities = []
        for e in result.scalars().all():
            # Recent social events
            social_result = await db.execute(
                select(func.count(SocialEvent.id)).where(
                    or_(
                        SocialEvent.entity_a_id == e.id,
                        SocialEvent.entity_b_id == e.id,
                    )
                )
            )
            social_count = social_result.scalar() or 0

            # Latest log
            log_result = await db.execute(
                select(DailyLog.content, DailyLog.day)
                .where(DailyLog.entity_id == e.id)
                .order_by(DailyLog.day.desc())
                .limit(1)
            )
            latest_log = log_result.first()

            # Player name
            player_name = None
            if e.player_id:
                p = await db.execute(
                    select(Player.display_name).where(Player.id == e.player_id)
                )
                player_name = p.scalar_one_or_none()

            entities.append({
                "id": e.id,
                "name": e.name,
                "player_name": player_name,
                "is_npc": e.is_npc,
                "core_belief": e.core_belief,
                "intent": e.intent,
                "direction": e.current_direction,
                "cultivation_day": e.cultivation_day,
                "fusion": {
                    "alignment": e.fusion_alignment,
                    "depth": e.fusion_depth,
                    "coherence": e.fusion_coherence,
                    "integrity": e.fusion_integrity,
                    "total": e.fusion_total,
                },
                "soul_force": e.soul_force,
                "total_feeds": e.total_feeds,
                "total_dialogues": e.total_dialogues,
                "social_count": social_count,
                "latest_log": {
                    "day": latest_log[1],
                    "content": latest_log[0],
                } if latest_log else None,
            })

        return {
            "stats": {
                "player_count": player_count,
                "entity_count": entity_count,
                "npc_count": npc_count,
            },
            "entities": entities,
        }


@router.get("/entity/{entity_id}")
async def entity_detail(entity_id: str, key: str = Query(...)):
    _check_key(key)
    async with async_session() as db:
        result = await db.execute(select(Entity).where(Entity.id == entity_id))
        entity = result.scalar_one_or_none()
        if not entity:
            raise HTTPException(status_code=404, detail="念体不存在")

        # Fusion history
        fh = await db.execute(
            select(FusionSnapshot)
            .where(FusionSnapshot.entity_id == entity_id)
            .order_by(FusionSnapshot.day)
        )
        fusion_history = [
            {
                "day": s.day,
                "alignment": s.alignment,
                "depth": s.depth,
                "coherence": s.coherence,
                "integrity": s.integrity,
                "total": s.total,
                "soul_force": s.soul_force,
            }
            for s in fh.scalars().all()
        ]

        # Social events
        se = await db.execute(
            select(SocialEvent)
            .where(
                or_(
                    SocialEvent.entity_a_id == entity_id,
                    SocialEvent.entity_b_id == entity_id,
                )
            )
            .order_by(SocialEvent.created_at.desc())
            .limit(20)
        )
        social_events = []
        for evt in se.scalars().all():
            opp_id = evt.entity_b_id if evt.entity_a_id == entity_id else evt.entity_a_id
            opp = await db.execute(select(Entity.name).where(Entity.id == opp_id))
            opp_name = opp.scalar_one_or_none() or "未知"
            outcome = {}
            try:
                outcome = json.loads(evt.outcome) if evt.outcome else {}
            except (json.JSONDecodeError, TypeError):
                pass
            social_events.append({
                "type": evt.event_type,
                "opponent": opp_name,
                "topic": evt.topic,
                "outcome": outcome,
                "day": evt.day,
            })

        # Daily logs
        dl = await db.execute(
            select(DailyLog)
            .where(DailyLog.entity_id == entity_id)
            .order_by(DailyLog.day.desc())
            .limit(10)
        )
        logs = [
            {"day": l.day, "content": l.content, "feeds": l.feeds_digested, "social": l.social_events_count}
            for l in dl.scalars().all()
        ]

        return {
            "entity": {
                "id": entity.id,
                "name": entity.name,
                "core_belief": entity.core_belief,
                "intent": entity.intent,
                "direction": entity.current_direction,
                "cultivation_day": entity.cultivation_day,
                "fusion": {
                    "alignment": entity.fusion_alignment,
                    "depth": entity.fusion_depth,
                    "coherence": entity.fusion_coherence,
                    "integrity": entity.fusion_integrity,
                    "total": entity.fusion_total,
                },
                "soul_force": entity.soul_force,
                "is_npc": entity.is_npc,
                "total_feeds": entity.total_feeds,
                "total_dialogues": entity.total_dialogues,
            },
            "fusion_history": fusion_history,
            "social_events": social_events,
            "daily_logs": logs,
        }


@router.post("/cycle/run")
async def run_cycle(key: str = Query(...)):
    _check_key(key)
    memory = MemoryLayer(get_chroma())
    cycle = DailyCycle(memory, get_llm())
    async with async_session() as db:
        count = await cycle.run_all(db)
    return {"message": f"每日结算完成，处理 {count} 个念体", "count": count}

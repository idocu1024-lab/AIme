import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.llm import LLMClient
from aime.core.fusion_engine import FusionEngine
from aime.core.memory_layer import MemoryLayer
from aime.core.social_engine import SocialEngine
from aime.models.daily_log import DailyLog
from aime.models.entity import Entity
from aime.models.feed import Feed
from aime.models.social_event import SocialEvent
from aime.prompts.daily_log import DAILY_LOG_PROMPT


class DailyCycle:
    def __init__(
        self,
        memory: MemoryLayer,
        llm: LLMClient,
    ):
        self.memory = memory
        self.llm = llm
        self.fusion_engine = FusionEngine(memory, llm)
        self.social_engine = SocialEngine(memory, llm)

    async def run_for_entity(self, entity: Entity, db: AsyncSession) -> DailyLog:
        """Run the full daily cycle for one entity."""
        old_fusion = entity.fusion_total

        # 1. Count today's feeds
        result = await db.execute(
            select(Feed).where(
                Feed.entity_id == entity.id,
                Feed.processed == True,
            )
        )
        feeds_today = len(list(result.scalars().all()))

        # 2. Run social matching (try to find an opponent)
        social_summary = "无社交事件"
        social_count = 0
        opponent = await self.social_engine.find_opponent(entity, db)
        if opponent:
            try:
                event = await self.social_engine.run_lun_dao(entity, opponent, db)
                social_summary = f"与「{opponent.name}」进行了一次论道，话题：{event.topic}"
                social_count = 1
            except Exception:
                social_summary = "尝试社交但未成功"

        # 3. Recalculate fusion
        fusion_result = await self.fusion_engine.calculate(entity, db)
        fusion_delta = round(fusion_result.total - old_fusion, 4)
        delta_str = f"{fusion_delta:+.4f}" if fusion_delta != 0 else "无变化"

        # 4. Generate daily log
        recent_memories = self.memory.get_recent(entity.id, limit=5)
        prompt = DAILY_LOG_PROMPT.format(
            name=entity.name,
            day=entity.cultivation_day,
            core_belief=entity.core_belief,
            feeds_digested=feeds_today,
            social_summary=social_summary,
            fusion_delta=delta_str,
            fusion_total=fusion_result.total,
            recent_memories="\n---\n".join(recent_memories) if recent_memories else "（暂无）",
        )

        log_content = await self.llm.generate(
            system="你是一个修炼日志记录者，以念体的第一人称视角撰写日志。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.max_tokens_daily_log,
        )
        log_content = log_content.strip()

        # 5. Save log
        daily_log = DailyLog(
            entity_id=entity.id,
            day=entity.cultivation_day,
            content=log_content,
            feeds_digested=feeds_today,
            social_events_count=social_count,
            fusion_delta=json.dumps({"total_delta": fusion_delta}),
        )
        db.add(daily_log)

        # 6. Increment cultivation day
        entity.cultivation_day += 1

        await db.commit()
        return daily_log

    async def run_all(self, db: AsyncSession) -> int:
        """Run daily cycle for all active entities. Returns count processed."""
        result = await db.execute(select(Entity))
        entities = list(result.scalars().all())
        count = 0
        for entity in entities:
            try:
                await self.run_for_entity(entity, db)
                count += 1
            except Exception:
                continue
        return count

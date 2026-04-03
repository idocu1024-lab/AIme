import json
import logging
import random

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

logger = logging.getLogger("aime.daily_cycle")


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

    # ──────────────────────────────────────────
    # 社交轮次 — 可独立于每日结算、一天运行多次
    # ──────────────────────────────────────────

    async def run_social_round(self, db: AsyncSession) -> int:
        """Run one round of social matching for ALL entities.

        Pairs entities randomly and runs 论道/切磋 between each pair.
        Returns the number of successful social events.
        """
        result = await db.execute(select(Entity))
        entities = list(result.scalars().all())
        if len(entities) < 2:
            return 0

        random.shuffle(entities)
        events = 0

        # Pair up entities (last one sits out if odd count)
        pairs: list[tuple[Entity, Entity]] = []
        used: set[str] = set()
        for e in entities:
            if e.id in used:
                continue
            # find_opponent picks a random other entity
            opponent = await self.social_engine.find_opponent(e, db)
            if opponent and opponent.id not in used:
                pairs.append((e, opponent))
                used.add(e.id)
                used.add(opponent.id)

        for entity_a, entity_b in pairs:
            try:
                # 70% 论道, 30% 切磋
                if random.random() < 0.7:
                    event = await self.social_engine.run_lun_dao(
                        entity_a, entity_b, db
                    )
                    logger.info(
                        f"论道：{entity_a.name} vs {entity_b.name} — {event.topic}"
                    )
                else:
                    event = await self.social_engine.run_qie_cuo(
                        entity_a, entity_b, db
                    )
                    logger.info(
                        f"切磋：{entity_a.name} vs {entity_b.name} — {event.topic}"
                    )
                events += 1
            except Exception as e:
                logger.warning(
                    f"社交失败：{entity_a.name} vs {entity_b.name}: {e}"
                )
                continue

        return events

    # ──────────────────────────────────────────
    # 每日结算 — 每天一次
    # ──────────────────────────────────────────

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

        # 2. Summarize today's social events (already run by social rounds)
        result = await db.execute(
            select(SocialEvent).where(
                SocialEvent.day == entity.cultivation_day,
                (SocialEvent.entity_a_id == entity.id)
                | (SocialEvent.entity_b_id == entity.id),
            )
        )
        social_events = list(result.scalars().all())
        social_count = len(social_events)

        if social_events:
            summaries = []
            for ev in social_events[:3]:
                summaries.append(
                    f"参与了一次{ev.event_type}，话题：{ev.topic}"
                )
            social_summary = "；".join(summaries)
        else:
            social_summary = "无社交事件"

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

        # 5. Save log & ingest as memory
        daily_log = DailyLog(
            entity_id=entity.id,
            day=entity.cultivation_day,
            content=log_content,
            feeds_digested=feeds_today,
            social_events_count=social_count,
            fusion_delta=json.dumps({"total_delta": fusion_delta}),
        )
        db.add(daily_log)
        await db.flush()

        # Store daily log as memory so entity remembers its cultivation journey
        try:
            self.memory.ingest(
                entity_id=entity.id,
                feed_id=daily_log.id,
                text=f"【修炼日志·第{entity.cultivation_day}天】\n{log_content}",
                source_label=f"日志·day{entity.cultivation_day}",
            )
        except Exception as e:
            logger.warning(f"日志记忆写入失败({entity.name}): {e}")

        # 6. Increment cultivation day
        entity.cultivation_day += 1

        await db.commit()
        logger.info(
            f"结算完成：{entity.name}（第{entity.cultivation_day - 1}天 → "
            f"融合度 {fusion_result.total:.4f}, Δ{delta_str}）"
        )
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
            except Exception as e:
                logger.error(f"每日结算失败({entity.name}): {e}")
                continue
        return count

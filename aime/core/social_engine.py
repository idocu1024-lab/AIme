import json
import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.llm import LLMClient
from aime.core.memory_layer import MemoryLayer
from aime.models.entity import Entity
from aime.models.social_event import SocialEvent
from aime.prompts.lun_dao import LUN_DAO_PROMPT
from aime.prompts.qie_cuo import QIE_CUO_PROMPT

logger = logging.getLogger("aime.social")


class SocialEngine:
    def __init__(self, memory: MemoryLayer, llm: LLMClient):
        self.memory = memory
        self.llm = llm

    async def run_lun_dao(
        self, entity_a: Entity, entity_b: Entity, db: AsyncSession
    ) -> SocialEvent:
        """Generate a 论道 (philosophical debate) between two entities."""
        memories_a = self.memory.get_recent(entity_a.id, limit=5)
        memories_b = self.memory.get_recent(entity_b.id, limit=5)

        prompt = LUN_DAO_PROMPT.format(
            name_a=entity_a.name,
            belief_a=entity_a.core_belief,
            intent_a=entity_a.intent,
            memories_a="\n".join(memories_a) if memories_a else "（暂无记忆）",
            name_b=entity_b.name,
            belief_b=entity_b.core_belief,
            intent_b=entity_b.intent,
            memories_b="\n".join(memories_b) if memories_b else "（暂无记忆）",
        )

        raw = await self.llm.generate(
            system="你是一个修炼世界的论道裁判。请严格返回JSON格式。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.max_tokens_social,
        )

        raw = raw.strip()
        parsed = self._parse_json(raw)

        # Calculate fusion impacts
        chemistry = parsed.get("chemistry", 0.5)
        impact_a = {
            "alignment": round(0.01 * chemistry, 4),
            "depth": round(0.015 * chemistry, 4),
            "coherence": round(0.005, 4),
            "integrity": round(0.01, 4),
        }
        impact_b = impact_a.copy()

        event = SocialEvent(
            event_type="lun_dao",
            entity_a_id=entity_a.id,
            entity_b_id=entity_b.id,
            day=entity_a.cultivation_day,
            topic=parsed.get("topic", "未知话题"),
            transcript=raw,
            outcome=json.dumps(parsed.get("insights", {}), ensure_ascii=False),
            fusion_impact_a=json.dumps(impact_a),
            fusion_impact_b=json.dumps(impact_b),
            status="complete",
        )
        db.add(event)

        # Apply fusion impacts
        self._apply_impact(entity_a, impact_a)
        self._apply_impact(entity_b, impact_b)

        await db.flush()

        # Ingest social dialogue as memory for both entities (learning)
        self._ingest_social_memory(
            entity_a, entity_b, event, parsed, "论道"
        )

        await db.commit()
        return event

    async def run_qie_cuo(
        self, entity_a: Entity, entity_b: Entity, db: AsyncSession
    ) -> SocialEvent:
        """Generate a 切磋 (sparring match) between two entities."""
        memories_a = self.memory.get_recent(entity_a.id, limit=5)
        memories_b = self.memory.get_recent(entity_b.id, limit=5)

        prompt = QIE_CUO_PROMPT.format(
            name_a=entity_a.name,
            belief_a=entity_a.core_belief,
            intent_a=entity_a.intent,
            fusion_a=entity_a.fusion_total,
            memories_a="\n".join(memories_a) if memories_a else "（暂无记忆）",
            name_b=entity_b.name,
            belief_b=entity_b.core_belief,
            intent_b=entity_b.intent,
            fusion_b=entity_b.fusion_total,
            memories_b="\n".join(memories_b) if memories_b else "（暂无记忆）",
        )

        raw = await self.llm.generate(
            system="你是一个修炼世界的切磋裁判。请严格返回JSON格式。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.max_tokens_social,
        )

        raw = raw.strip()
        parsed = self._parse_json(raw)

        winner_name = parsed.get("winner", entity_a.name)
        winner = entity_a if winner_name == entity_a.name else entity_b
        loser = entity_b if winner == entity_a else entity_a

        impact_winner = {
            "alignment": 0.02,
            "depth": 0.02,
            "coherence": 0.025,
            "integrity": 0.01,
        }
        impact_loser = {
            "alignment": -0.005,
            "depth": 0.01,
            "coherence": 0.02,
            "integrity": 0.005,
        }

        event = SocialEvent(
            event_type="qie_cuo",
            entity_a_id=entity_a.id,
            entity_b_id=entity_b.id,
            day=entity_a.cultivation_day,
            topic=parsed.get("topic", "未知领域"),
            transcript=raw,
            outcome=json.dumps({
                "winner": winner.name,
                "analysis": parsed.get("analysis", ""),
            }, ensure_ascii=False),
            fusion_impact_a=json.dumps(
                impact_winner if winner == entity_a else impact_loser
            ),
            fusion_impact_b=json.dumps(
                impact_winner if winner == entity_b else impact_loser
            ),
            status="complete",
        )
        db.add(event)

        self._apply_impact(
            entity_a, impact_winner if winner == entity_a else impact_loser
        )
        self._apply_impact(
            entity_b, impact_winner if winner == entity_b else impact_loser
        )

        await db.flush()

        # Ingest social dialogue as memory for both entities (learning)
        self._ingest_social_memory(
            entity_a, entity_b, event, parsed, "切磋"
        )

        await db.commit()
        return event

    async def find_opponent(
        self, entity: Entity, db: AsyncSession
    ) -> Entity | None:
        """Find a random opponent for social events."""
        result = await db.execute(
            select(Entity).where(
                Entity.id != entity.id,
            )
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None
        return random.choice(candidates)

    def _ingest_social_memory(
        self,
        entity_a: Entity,
        entity_b: Entity,
        event: SocialEvent,
        parsed: dict,
        event_label: str,
    ):
        """Store social event as memory for both entities so they learn."""
        # Build a concise memory text from the parsed dialogue
        topic = parsed.get("topic", "未知")
        dialogue = parsed.get("dialogue", [])

        # Summarize the dialogue into a readable memory
        lines = [f"【{event_label}记忆】与「{{opponent}}」关于「{topic}」的{event_label}"]
        for turn in dialogue[:6]:  # Cap at 6 turns to keep memory concise
            speaker = turn.get("speaker", turn.get("name", "?"))
            content = turn.get("content", turn.get("text", ""))
            if content:
                lines.append(f"{speaker}：{content[:200]}")

        # Add insights/outcome if available
        insights = parsed.get("insights", parsed.get("analysis", ""))
        if isinstance(insights, dict):
            for k, v in insights.items():
                lines.append(f"感悟·{k}：{v}")
        elif isinstance(insights, str) and insights:
            lines.append(f"感悟：{insights[:300]}")

        memory_text_template = "\n".join(lines)

        # Ingest for entity A
        try:
            text_a = memory_text_template.replace("{opponent}", entity_b.name)
            self.memory.ingest(
                entity_id=entity_a.id,
                feed_id=event.id,
                text=text_a,
                source_label=f"{event_label}·{entity_b.name}·day{event.day}",
            )
        except Exception as e:
            logger.warning(f"社交记忆写入失败(A): {e}")

        # Ingest for entity B
        try:
            text_b = memory_text_template.replace("{opponent}", entity_a.name)
            self.memory.ingest(
                entity_id=entity_b.id,
                feed_id=event.id,
                text=text_b,
                source_label=f"{event_label}·{entity_a.name}·day{event.day}",
            )
        except Exception as e:
            logger.warning(f"社交记忆写入失败(B): {e}")

    def _apply_impact(self, entity: Entity, impact: dict):
        """Apply fusion impact deltas to an entity."""
        entity.fusion_alignment = max(
            0.0, min(1.0, entity.fusion_alignment + impact.get("alignment", 0))
        )
        entity.fusion_depth = max(
            0.0, min(1.0, entity.fusion_depth + impact.get("depth", 0))
        )
        entity.fusion_coherence = max(
            0.0, min(1.0, entity.fusion_coherence + impact.get("coherence", 0))
        )
        entity.fusion_integrity = max(
            0.0, min(1.0, entity.fusion_integrity + impact.get("integrity", 0))
        )
        entity.fusion_total = round(
            entity.fusion_alignment * 0.30
            + entity.fusion_depth * 0.25
            + entity.fusion_coherence * 0.25
            + entity.fusion_integrity * 0.20,
            4,
        )

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting from code block
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                cleaned = part.strip()
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
        # Fallback
        return {"topic": "未知", "dialogue": [], "chemistry": 0.5}

import json
import math
import statistics
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.llm import LLMClient
from aime.core.memory_layer import MemoryLayer
from aime.models.entity import Entity
from aime.models.fusion import FusionSnapshot
from aime.prompts.fusion_eval import FUSION_EVAL_PROMPT


@dataclass
class FusionResult:
    alignment: float
    depth: float
    coherence: float
    integrity: float
    total: float
    soul_force: int
    notes: str = ""


def _calculate_soul_force(fusion_total: float) -> int:
    """Non-linear soul force based on fusion score."""
    if fusion_total < 0.01:
        return 10
    # Exponential curve: higher fusion = dramatically more soul force
    base = 100
    exponent = fusion_total * 10
    return int(base * (math.exp(exponent * 0.3) - 0.7))


class FusionEngine:
    def __init__(self, memory: MemoryLayer, llm: LLMClient):
        self.memory = memory
        self.llm = llm

    async def calculate(self, entity: Entity, db: AsyncSession) -> FusionResult:
        """Full fusion calculation: quantitative + semantic."""
        quant = self._quantitative_signals(entity)

        try:
            semantic = await self._semantic_evaluation(entity, quant)
        except Exception:
            # Fallback to pure quantitative if Claude fails
            semantic = quant.copy()

        # Blend: 40% quant, 60% semantic
        w_q = settings.fusion_quant_weight
        w_s = settings.fusion_semantic_weight

        alignment = round(quant["alignment"] * w_q + semantic["alignment"] * w_s, 4)
        depth = round(quant["depth"] * w_q + semantic["depth"] * w_s, 4)
        coherence = round(quant["coherence"] * w_q + semantic["coherence"] * w_s, 4)
        integrity = round(quant["integrity"] * w_q + semantic["integrity"] * w_s, 4)

        total = round(
            alignment * 0.30 + depth * 0.25 + coherence * 0.25 + integrity * 0.20,
            4,
        )

        soul_force = _calculate_soul_force(total)

        result = FusionResult(
            alignment=alignment,
            depth=depth,
            coherence=coherence,
            integrity=integrity,
            total=total,
            soul_force=soul_force,
            notes=semantic.get("reasoning", ""),
        )

        # Save snapshot
        snapshot = FusionSnapshot(
            entity_id=entity.id,
            day=entity.cultivation_day,
            alignment=alignment,
            depth=depth,
            coherence=coherence,
            integrity=integrity,
            total=total,
            soul_force=soul_force,
            evaluation_notes=result.notes,
        )
        db.add(snapshot)

        # Update entity
        entity.fusion_alignment = alignment
        entity.fusion_depth = depth
        entity.fusion_coherence = coherence
        entity.fusion_integrity = integrity
        entity.fusion_total = total
        entity.soul_force = soul_force

        return result

    def _quantitative_signals(self, entity: Entity) -> dict:
        """Fast rule-based metrics."""
        # Alignment: cosine similarity of memories to core_belief
        memories = self.memory.recall(entity.id, entity.core_belief, n_results=20)
        if memories:
            avg_similarity = 1.0 - statistics.mean([m.distance for m in memories])
            distances = [m.distance for m in memories]
            variance = (
                statistics.variance(distances) if len(distances) > 1 else 0.5
            )
        else:
            avg_similarity = 0.1
            variance = 0.5

        # Depth: based on total feeds and dialogues
        depth_raw = min(1.0, entity.total_feeds * 0.04 + entity.total_dialogues * 0.02)

        # Coherence: low variance in distances = high coherence
        coherence_raw = max(0.0, min(1.0, 1.0 - variance * 5))

        # Integrity: memory count as proxy
        stats = self.memory.get_stats(entity.id)
        integrity_raw = min(1.0, stats["total_entries"] * 0.02)

        return {
            "alignment": round(avg_similarity, 4),
            "depth": round(depth_raw, 4),
            "coherence": round(coherence_raw, 4),
            "integrity": round(integrity_raw, 4),
        }

    async def _semantic_evaluation(self, entity: Entity, quant: dict) -> dict:
        """Claude-powered semantic evaluation."""
        recent_memories = self.memory.get_recent(entity.id, limit=10)
        if not recent_memories:
            return {**quant, "reasoning": "记忆为空，使用量化基准"}

        memory_text = "\n---\n".join(recent_memories)
        prompt = FUSION_EVAL_PROMPT.format(
            name=entity.name,
            core_belief=entity.core_belief,
            intent=entity.intent,
            direction=entity.current_direction or "未设定",
            cultivation_day=entity.cultivation_day,
            memories=memory_text,
            quant_alignment=quant["alignment"],
            quant_depth=quant["depth"],
            quant_coherence=quant["coherence"],
            quant_integrity=quant["integrity"],
        )

        text = await self.llm.generate(
            system="你是一个聚变度评估系统。请严格返回JSON格式。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.max_tokens_fusion,
        )
        text = text.strip()
        # Try to extract JSON from response
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        result = json.loads(text)
        return {
            "alignment": max(0.0, min(1.0, float(result.get("alignment", quant["alignment"])))),
            "depth": max(0.0, min(1.0, float(result.get("depth", quant["depth"])))),
            "coherence": max(0.0, min(1.0, float(result.get("coherence", quant["coherence"])))),
            "integrity": max(0.0, min(1.0, float(result.get("integrity", quant["integrity"])))),
            "reasoning": result.get("reasoning", ""),
        }

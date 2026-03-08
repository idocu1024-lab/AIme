import json
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.llm import LLMClient
from aime.core.memory_layer import MemoryLayer
from aime.models.dialogue import DialogueTurn
from aime.models.entity import Entity
from aime.prompts.entity_system import build_entity_system_prompt
from aime.utils.id_gen import gen_short_id


class EntityMind:
    def __init__(self, memory: MemoryLayer, llm: LLMClient):
        self.memory = memory
        self.llm = llm

    async def dialogue(
        self,
        entity: Entity,
        player_message: str,
        db: AsyncSession,
        session_id: str | None = None,
    ) -> AsyncIterator[str]:
        """RAG-powered streaming dialogue with the entity."""
        if session_id is None:
            session_id = gen_short_id()

        # 1. Retrieve relevant memories
        memories = self.memory.recall(entity.id, player_message, n_results=5)
        memory_context = "\n---\n".join([m.content for m in memories])

        # 2. Get recent dialogue history
        recent = await self._get_recent_turns(entity.id, session_id, db, limit=10)

        # 3. Build messages
        messages = []
        for turn in recent:
            messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": player_message})

        # 4. Build system prompt
        system = build_entity_system_prompt(
            name=entity.name,
            core_belief=entity.core_belief,
            intent=entity.intent,
            direction=entity.current_direction,
            cultivation_day=entity.cultivation_day,
            memory_context=memory_context,
        )

        # 5. Stream response
        full_response = ""
        async for text in self.llm.stream(
            system=system,
            messages=messages,
            max_tokens=settings.max_tokens_dialogue,
        ):
            full_response += text
            yield text

        # 6. Save turns
        memory_refs = json.dumps([m.chroma_id for m in memories])
        await self._save_turn(entity.id, "user", player_message, session_id, db)
        await self._save_turn(
            entity.id, "assistant", full_response, session_id, db, memory_refs
        )

        # 7. Update dialogue count
        entity.total_dialogues += 1
        await db.commit()

    async def dialogue_sync(
        self,
        entity: Entity,
        player_message: str,
        db: AsyncSession,
        session_id: str | None = None,
    ) -> tuple[str, str]:
        """Non-streaming dialogue. Returns (response, session_id)."""
        if session_id is None:
            session_id = gen_short_id()

        full = ""
        async for token in self.dialogue(entity, player_message, db, session_id):
            full += token
        return full, session_id

    async def _get_recent_turns(
        self, entity_id: str, session_id: str, db: AsyncSession, limit: int = 10
    ) -> list[DialogueTurn]:
        result = await db.execute(
            select(DialogueTurn)
            .where(
                DialogueTurn.entity_id == entity_id,
                DialogueTurn.session_id == session_id,
            )
            .order_by(DialogueTurn.created_at.desc())
            .limit(limit)
        )
        turns = list(result.scalars().all())
        turns.reverse()
        return turns

    async def _save_turn(
        self,
        entity_id: str,
        role: str,
        content: str,
        session_id: str,
        db: AsyncSession,
        memory_refs: str | None = None,
    ):
        turn = DialogueTurn(
            entity_id=entity_id,
            role=role,
            content=content,
            session_id=session_id,
            memory_refs=memory_refs,
        )
        db.add(turn)

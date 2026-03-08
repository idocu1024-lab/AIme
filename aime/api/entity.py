from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.deps import get_current_player, get_db
from aime.models.entity import Entity
from aime.models.player import Player
from aime.schemas.entity import EntityBrief, EntityCreate, EntityStatus, FusionScores

router = APIRouter(prefix="/api/entity", tags=["entity"])


@router.post("", response_model=EntityStatus)
async def create_entity(
    data: EntityCreate,
    player: Player = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    if player.entity is not None:
        raise HTTPException(status_code=400, detail="你已经拥有一个念体")

    entity = Entity(
        player_id=player.id,
        name=data.name,
        core_belief=data.core_belief,
        intent=data.intent,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)

    # Process first feed (will be done via feed processor in Phase B)
    # For now, just record the intent
    from aime.core.feed_processor import process_feed
    await process_feed(entity, data.first_feed, "初始投喂", db)

    return _entity_to_status(entity)


@router.get("/me", response_model=EntityStatus)
async def get_my_entity(
    player: Player = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Entity).where(Entity.player_id == player.id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="你还没有念体，请先创建")
    return _entity_to_status(entity)


@router.get("/{entity_id}", response_model=EntityBrief)
async def get_entity(entity_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="念体不存在")
    return EntityBrief(
        id=entity.id,
        name=entity.name,
        current_direction=entity.current_direction,
        fusion_total=entity.fusion_total,
        soul_force=entity.soul_force,
    )


@router.put("/direction")
async def set_direction(
    direction: str,
    player: Player = Depends(get_current_player),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Entity).where(Entity.player_id == player.id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="你还没有念体")
    entity.current_direction = direction
    await db.commit()
    return {"message": f"修炼方向已设定为：{direction}"}


def _entity_to_status(entity: Entity) -> EntityStatus:
    return EntityStatus(
        id=entity.id,
        name=entity.name,
        core_belief=entity.core_belief,
        intent=entity.intent,
        current_direction=entity.current_direction,
        cultivation_day=entity.cultivation_day,
        total_feeds=entity.total_feeds,
        total_dialogues=entity.total_dialogues,
        fusion=FusionScores(
            alignment=entity.fusion_alignment,
            depth=entity.fusion_depth,
            coherence=entity.fusion_coherence,
            integrity=entity.fusion_integrity,
            total=entity.fusion_total,
        ),
        soul_force=entity.soul_force,
        is_npc=entity.is_npc,
    )

from pydantic import BaseModel, Field


class EntityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    core_belief: str = Field(..., min_length=10, max_length=2000)
    intent: str = Field(..., min_length=5, max_length=1000)
    first_feed: str = Field(..., min_length=10, max_length=10000)


class FusionScores(BaseModel):
    alignment: float = Field(ge=0.0, le=1.0)
    depth: float = Field(ge=0.0, le=1.0)
    coherence: float = Field(ge=0.0, le=1.0)
    integrity: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)


class EntityStatus(BaseModel):
    id: str
    name: str
    core_belief: str
    intent: str
    current_direction: str | None
    cultivation_day: int
    total_feeds: int
    total_dialogues: int
    fusion: FusionScores
    soul_force: int
    is_npc: bool


class EntityBrief(BaseModel):
    id: str
    name: str
    current_direction: str | None
    fusion_total: float
    soul_force: int

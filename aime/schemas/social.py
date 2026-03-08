from pydantic import BaseModel


class SocialEventBrief(BaseModel):
    id: str
    event_type: str
    entity_a_name: str
    entity_b_name: str
    day: int
    topic: str | None
    outcome: str | None


class SocialEventDetail(BaseModel):
    id: str
    event_type: str
    entity_a_name: str
    entity_b_name: str
    day: int
    topic: str | None
    transcript: str
    outcome: str | None
    fusion_impact: str | None

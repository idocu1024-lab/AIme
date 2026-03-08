from pydantic import BaseModel, Field


class FeedSubmit(BaseModel):
    text: str = Field(..., min_length=10, max_length=50000)
    source_label: str | None = None


class FeedResponse(BaseModel):
    id: str
    chunk_count: int
    message: str

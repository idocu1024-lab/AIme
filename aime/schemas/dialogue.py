from pydantic import BaseModel, Field


class DialogueMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class DialogueResponse(BaseModel):
    reply: str
    session_id: str

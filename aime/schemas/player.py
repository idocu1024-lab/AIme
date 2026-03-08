from pydantic import BaseModel, Field


class PlayerRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=64)


class PlayerLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PlayerInfo(BaseModel):
    id: str
    username: str
    display_name: str
    has_entity: bool

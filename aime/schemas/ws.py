from pydantic import BaseModel


class WSIncoming(BaseModel):
    type: str = "command"  # "command"
    cmd: str
    args: str = ""


class WSOutgoing(BaseModel):
    type: str  # system | narrative | entity_speech | error | highlight | divider
    content: str
    streaming: bool = False
    done: bool = False

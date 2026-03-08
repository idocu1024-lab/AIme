from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aime.models.base import Base, TimestampMixin, gen_id


class DialogueTurn(Base, TimestampMixin):
    __tablename__ = "dialogue_turns"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    memory_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str] = mapped_column(String(12), index=True)

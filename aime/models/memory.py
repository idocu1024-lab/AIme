from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aime.models.base import Base, TimestampMixin, gen_id


class MemoryChunk(Base, TimestampMixin):
    __tablename__ = "memory_chunks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    feed_id: Mapped[str] = mapped_column(ForeignKey("feeds.id"))
    chroma_id: Mapped[str] = mapped_column(String(64), unique=True)
    content_preview: Mapped[str] = mapped_column(String(200))
    chunk_index: Mapped[int] = mapped_column(default=0)
    token_count: Mapped[int] = mapped_column(default=0)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)

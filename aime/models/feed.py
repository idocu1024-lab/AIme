from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aime.models.base import Base, TimestampMixin, gen_id


class Feed(Base, TimestampMixin):
    __tablename__ = "feeds"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    processed: Mapped[bool] = mapped_column(default=False)

    entity: Mapped["Entity"] = relationship(back_populates="feeds")  # noqa: F821

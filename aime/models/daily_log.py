from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aime.models.base import Base, TimestampMixin, gen_id


class DailyLog(Base, TimestampMixin):
    __tablename__ = "daily_logs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    day: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    feeds_digested: Mapped[int] = mapped_column(default=0)
    social_events_count: Mapped[int] = mapped_column(default=0)
    fusion_delta: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity: Mapped["Entity"] = relationship(  # noqa: F821
        back_populates="daily_logs"
    )

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aime.models.base import Base, TimestampMixin, gen_id


class SocialEvent(Base, TimestampMixin):
    __tablename__ = "social_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    event_type: Mapped[str] = mapped_column(String(16))  # lun_dao | qie_cuo
    entity_a_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    entity_b_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    day: Mapped[int] = mapped_column()
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    fusion_impact_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    fusion_impact_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="complete")

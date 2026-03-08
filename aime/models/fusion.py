from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aime.models.base import Base, TimestampMixin, gen_id


class FusionSnapshot(Base, TimestampMixin):
    __tablename__ = "fusion_snapshots"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    day: Mapped[int] = mapped_column()
    alignment: Mapped[float] = mapped_column()
    depth: Mapped[float] = mapped_column()
    coherence: Mapped[float] = mapped_column()
    integrity: Mapped[float] = mapped_column()
    total: Mapped[float] = mapped_column()
    soul_force: Mapped[int] = mapped_column(default=10)
    evaluation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity: Mapped["Entity"] = relationship(  # noqa: F821
        back_populates="fusion_history"
    )

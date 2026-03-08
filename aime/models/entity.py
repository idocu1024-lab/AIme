from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aime.models.base import Base, TimestampMixin, gen_id


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    player_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.id"), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(64))
    core_belief: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(Text)
    current_direction: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fusion scores (cached, updated daily)
    fusion_alignment: Mapped[float] = mapped_column(default=0.1)
    fusion_depth: Mapped[float] = mapped_column(default=0.1)
    fusion_coherence: Mapped[float] = mapped_column(default=0.1)
    fusion_integrity: Mapped[float] = mapped_column(default=0.1)
    fusion_total: Mapped[float] = mapped_column(default=0.1)

    # Stats
    total_feeds: Mapped[int] = mapped_column(default=0)
    total_dialogues: Mapped[int] = mapped_column(default=0)
    cultivation_day: Mapped[int] = mapped_column(default=1)
    is_npc: Mapped[bool] = mapped_column(default=False)

    # Soul force (魂念力)
    soul_force: Mapped[int] = mapped_column(default=10)

    # Relationships
    player: Mapped["Player | None"] = relationship(  # noqa: F821
        back_populates="entity"
    )
    feeds: Mapped[list["Feed"]] = relationship(back_populates="entity")  # noqa: F821
    fusion_history: Mapped[list["FusionSnapshot"]] = relationship(  # noqa: F821
        back_populates="entity"
    )
    daily_logs: Mapped[list["DailyLog"]] = relationship(  # noqa: F821
        back_populates="entity"
    )

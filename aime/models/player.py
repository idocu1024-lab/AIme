from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aime.models.base import Base, TimestampMixin, gen_id


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True)

    entity: Mapped["Entity | None"] = relationship(  # noqa: F821
        back_populates="player", uselist=False
    )

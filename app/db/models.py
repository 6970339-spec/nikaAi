from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # BROTHER / SISTER
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profiles: Mapped[list["Profile"]] = relationship(back_populates="user")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # О себе (структурно)
    age: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    children: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prayer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relocation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra_about: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Кого ищу (структурно)
    partner_age: Mapped[str | None] = mapped_column(String(32), nullable=True)
    partner_nationality_pref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    partner_priority: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # “Полный текст” для будущего ИИ
    about_me_text: Mapped[str] = mapped_column(Text, default="")
    looking_for_text: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="profiles")

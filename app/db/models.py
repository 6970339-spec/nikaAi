from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    age: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    children: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prayer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relocation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra_about: Mapped[str | None] = mapped_column(Text, nullable=True)
    aqida: Mapped[str | None] = mapped_column(String(32), nullable=True)
    polygyny: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Кого ищу (структурно)
    partner_age: Mapped[str | None] = mapped_column(String(32), nullable=True)
    partner_nationality_pref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    partner_priority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # “Полный текст” для будущего ИИ
    about_me_text: Mapped[str] = mapped_column(Text, default="")
    looking_for_text: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="profiles")
    attribute_values: Mapped[list["ProfileAttributeValue"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class Attribute(Base):
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(16))
    value_type: Mapped[str] = mapped_column(String(16))
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    options: Mapped[list["AttributeOption"]] = relationship(
        back_populates="attribute",
        cascade="all, delete-orphan",
    )
    values: Mapped[list["ProfileAttributeValue"]] = relationship(back_populates="attribute")


class AttributeOption(Base):
    __tablename__ = "attribute_options"
    __table_args__ = (UniqueConstraint("attribute_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))

    attribute: Mapped["Attribute"] = relationship(back_populates="options")
    values: Mapped[list["ProfileAttributeValue"]] = relationship(back_populates="option")


class ProfileAttributeValue(Base):
    __tablename__ = "profile_attribute_values"
    __table_args__ = (UniqueConstraint("profile_id", "attribute_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"), index=True)
    option_id: Mapped[int | None] = mapped_column(ForeignKey("attribute_options.id"), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="attribute_values")
    attribute: Mapped["Attribute"] = relationship(back_populates="values")
    option: Mapped["AttributeOption"] = relationship(back_populates="values")

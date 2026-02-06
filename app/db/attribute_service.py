from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attribute, AttributeOption, ProfileAttributeValue


def normalize_key(raw: str) -> str:
    original = (raw or "").strip()
    raw = original.lower()
    raw = re.sub(r"\s+", "_", raw)
    raw = re.sub(r"[^a-z0-9_]+", "", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        digest = hashlib.sha1((original or "empty").encode("utf-8")).hexdigest()[:8]
        return f"dyn_{digest}"
    return raw


async def get_attribute_by_key(session: AsyncSession, key: str) -> Attribute | None:
    result = await session.execute(select(Attribute).where(Attribute.key == key))
    return result.scalar_one_or_none()


async def get_or_create_dynamic_attribute(
    session: AsyncSession,
    key: str,
    title: str,
    scope: str,
    value_type: str = "TEXT",
) -> Attribute:
    safe_key = normalize_key(key)
    existing = await get_attribute_by_key(session, safe_key)
    if existing is not None:
        return existing
    attr = Attribute(
        key=safe_key,
        title=title or safe_key,
        scope=scope,
        value_type=value_type,
        is_canonical=False,
        is_primary=False,
        status="PENDING_REVIEW",
    )
    session.add(attr)
    await session.flush()
    return attr


async def _find_option_for_value(
    session: AsyncSession,
    attribute_id: int,
    option_code: str | None,
    value: str,
) -> AttributeOption | None:
    if option_code:
        result = await session.execute(
            select(AttributeOption).where(
                AttributeOption.attribute_id == attribute_id,
                AttributeOption.code == option_code,
            )
        )
        option = result.scalar_one_or_none()
        if option is not None:
            return option
    if not value:
        return None
    normalized = value.strip().lower()
    result = await session.execute(
        select(AttributeOption).where(AttributeOption.attribute_id == attribute_id)
    )
    for option in result.scalars().all():
        if option.code.lower() == normalized or option.label.lower() == normalized:
            return option
    return None


def _extract_int(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _extract_bool(value: str) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"yes", "true", "1", "да"}:
        return True
    if normalized in {"no", "false", "0", "нет"}:
        return False
    return None


async def upsert_profile_attribute_value(
    session: AsyncSession,
    profile_id: int,
    attribute: Attribute,
    value: str,
    option_code: str | None,
    confidence: float,
    evidence: str | None,
) -> None:
    value_text: str | None = None
    value_int: int | None = None
    value_bool: bool | None = None
    option_id: int | None = None

    if attribute.value_type == "ENUM":
        option = await _find_option_for_value(session, attribute.id, option_code, value)
        if option is not None:
            option_id = option.id
        else:
            value_text = value
    elif attribute.value_type == "INT":
        value_int = _extract_int(value)
        if value_int is None:
            value_text = value
    elif attribute.value_type == "BOOL":
        value_bool = _extract_bool(value)
        if value_bool is None:
            value_text = value
    else:
        value_text = value

    result = await session.execute(
        select(ProfileAttributeValue).where(
            ProfileAttributeValue.profile_id == profile_id,
            ProfileAttributeValue.attribute_id == attribute.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        session.add(
            ProfileAttributeValue(
                profile_id=profile_id,
                attribute_id=attribute.id,
                option_id=option_id,
                value_text=value_text,
                value_int=value_int,
                value_bool=value_bool,
                confidence=confidence,
                evidence=evidence,
            )
        )
        return

    existing.option_id = option_id
    existing.value_text = value_text
    existing.value_int = value_int
    existing.value_bool = value_bool
    existing.confidence = confidence
    existing.evidence = evidence


async def map_extracted_item_to_attribute(
    session: AsyncSession,
    item: dict[str, Any],
) -> tuple[Attribute, dict[str, Any]]:
    raw_key = str(item.get("key", "")).strip()
    attribute = None
    if raw_key:
        attribute = await get_attribute_by_key(session, raw_key)
    normalized_key = normalize_key(raw_key)
    if attribute is None:
        attribute = await get_attribute_by_key(session, normalized_key)
    if attribute is None:
        title = raw_key or normalized_key
        scope = str(item.get("scope") or "SELF")
        attribute = await get_or_create_dynamic_attribute(
            session=session,
            key=normalized_key,
            title=title,
            scope=scope,
            value_type="TEXT",
        )
    normalized_item = dict(item)
    normalized_item["key"] = attribute.key
    return attribute, normalized_item

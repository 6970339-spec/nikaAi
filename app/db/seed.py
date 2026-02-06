from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attribute, AttributeOption

CANONICAL_ATTRIBUTES: list[dict] = [
    {
        "key": "age",
        "title": "Возраст",
        "scope": "SELF",
        "value_type": "INT",
        "is_primary": True,
        "options": [],
    },
    {
        "key": "location",
        "title": "Локация (город/страна)",
        "scope": "SELF",
        "value_type": "TEXT",
        "is_primary": True,
        "options": [],
    },
    {
        "key": "nationality",
        "title": "Национальность/этнос",
        "scope": "SELF",
        "value_type": "TEXT",
        "is_primary": True,
        "options": [],
    },
    {
        "key": "aqida_manhaj",
        "title": "Акъыда/манхадж",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": True,
        "options": [
            ("AHLU_SUNNA", "Ахлю-Сунна"),
            ("SALAFI", "Саляфи"),
            ("OTHER", "Другое"),
            ("UNKNOWN", "Не знаю"),
        ],
    },
    {
        "key": "marital_status",
        "title": "Семейное положение",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": True,
        "options": [
            ("NEVER_MARRIED", "Не был(а) женат(а)"),
            ("MARRIED", "Женат/замужем"),
            ("DIVORCED", "В разводе"),
            ("WIDOWED", "Вдовец/вдова"),
        ],
    },
    {
        "key": "children",
        "title": "Дети",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": True,
        "options": [
            ("NONE", "Нет"),
            ("HAS_1", "Есть: 1"),
            ("HAS_2", "Есть: 2"),
            ("HAS_3PLUS", "Есть: 3+"),
            ("UNKNOWN", "Не хочу указывать"),
        ],
    },
    {
        "key": "polygyny_attitude",
        "title": "Отношение к многоженству",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": True,
        "options": [
            ("MONOGAMY_ONLY", "Хочу только единобрачие"),
            ("OPEN_TO_POLYGYNY", "Допускаю многоженство"),
            ("SEEKS_POLYGYNY", "Хочу/планирую многоженство"),
            ("NEUTRAL", "Не важно/не обсуждала(л)"),
        ],
    },
    {
        "key": "height_cm",
        "title": "Рост (см)",
        "scope": "SELF",
        "value_type": "INT",
        "is_primary": False,
        "options": [],
    },
    {
        "key": "weight_kg",
        "title": "Вес (кг)",
        "scope": "SELF",
        "value_type": "INT",
        "is_primary": False,
        "options": [],
    },
    {
        "key": "prayer_level",
        "title": "Намаз",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": False,
        "options": [
            ("REGULAR", "Регулярно"),
            ("SOMETIMES", "Иногда"),
            ("RARELY", "Редко/не совершаю"),
            ("UNKNOWN", "Не указано"),
        ],
    },
    {
        "key": "hijab_type",
        "title": "Одеяние",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": False,
        "options": [
            ("NIQAB", "Никаб"),
            ("HIJAB", "Хиджаб"),
            ("SHARIA", "Шариатский хиджаб"),
            ("NONE", "Не указано"),
        ],
    },
    {
        "key": "relocation_ready",
        "title": "Переезд",
        "scope": "SELF",
        "value_type": "ENUM",
        "is_primary": False,
        "options": [
            ("YES", "Готов(а)"),
            ("NO", "Не готов(а)"),
            ("DEPENDS", "Зависит"),
            ("UNKNOWN", "Не указано"),
        ],
    },
    {
        "key": "partner_age_range",
        "title": "Возраст партнера (диапазон)",
        "scope": "PREFERENCE",
        "value_type": "TEXT",
        "is_primary": False,
        "options": [],
    },
]


async def seed_canonical_attributes(session: AsyncSession) -> None:
    keys = [item["key"] for item in CANONICAL_ATTRIBUTES]
    result = await session.execute(select(Attribute).where(Attribute.key.in_(keys)))
    existing = {item.key: item for item in result.scalars()}

    for spec in CANONICAL_ATTRIBUTES:
        attr = existing.get(spec["key"])
        if attr is None:
            attr = Attribute(
                key=spec["key"],
                title=spec["title"],
                scope=spec["scope"],
                value_type=spec["value_type"],
                is_canonical=True,
                is_primary=spec["is_primary"],
            )
            session.add(attr)
            await session.flush()
        else:
            if not attr.is_canonical:
                attr.is_canonical = True
            if attr.is_primary != spec["is_primary"]:
                attr.is_primary = spec["is_primary"]
            if attr.title != spec["title"]:
                attr.title = spec["title"]
            if attr.scope != spec["scope"]:
                attr.scope = spec["scope"]
            if attr.value_type != spec["value_type"]:
                attr.value_type = spec["value_type"]

        options = spec.get("options") or []
        if options:
            res = await session.execute(
                select(AttributeOption.code).where(AttributeOption.attribute_id == attr.id)
            )
            existing_codes = set(res.scalars().all())
            for code, label in options:
                if code not in existing_codes:
                    session.add(
                        AttributeOption(
                            attribute_id=attr.id,
                            code=code,
                            label=label,
                        )
                    )

    await session.commit()

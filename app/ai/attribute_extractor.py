from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


client = OpenAI()  # читает ключ из env: OPENAI_API_KEY


@dataclass
class ExtractedAttribute:
    key: str                 # canonical key, например: "polygamy"
    label: str               # человекочитаемое: "Многоженство"
    value: str               # например: "against" / "allow" / "conditional" / "unknown"
    confidence: float        # 0..1
    evidence: str            # короткая цитата/обрывок из текста


def _safe_json_load(s: str) -> dict[str, Any]:
    try:
        return json.loads(s)
    except Exception:
        # на случай если модель вернула лишний текст
        # попробуем вытащить JSON между первой { и последней }
        a = s.find("{")
        b = s.rfind("}")
        if a != -1 and b != -1 and b > a:
            return json.loads(s[a : b + 1])
        raise


def extract_profile_attributes_free_text(free_text: str) -> list[ExtractedAttribute]:
    """
    Извлекает структурированные атрибуты из свободного текста анкеты.
    На MVP этапе: возвращаем список атрибутов. Дальше вы сохраните это в БД.
    """

    free_text = (free_text or "").strip()
    if not free_text:
        return []

    system = (
        "Ты — извлекатель атрибутов для мусульманского брачного бота.\n"
        "Твоя задача: из свободного текста анкеты выделить устойчивые атрибуты "
        "и нормализовать их.\n"
        "Верни ТОЛЬКО JSON без пояснений.\n\n"
        "Правила:\n"
        "1) Если пользователь против многоженства ИЛИ хочет быть единственной женой "
        "ИЛИ просит многоженцев не беспокоить — это один атрибут key='polygamy', label='Многоженство'.\n"
        "2) value для polygamy: 'against' (против), 'allow' (разрешает), 'conditional' (условно), 'unknown'.\n"
        "3) confidence 0..1.\n"
        "4) evidence — короткая цитата из исходного текста.\n"
        "5) Если встречается новый устойчивый атрибут, добавляй его, но key делай на латинице snake_case.\n\n"
        "Формат ответа:\n"
        "{\n"
        "  \"attributes\": [\n"
        "     {\"key\": \"polygamy\", \"label\": \"Многоженство\", \"value\": \"against\", \"confidence\": 0.9, \"evidence\": \"...\"},\n"
        "     ...\n"
        "  ]\n"
        "}"
    )

    # Дешёвый/быстрый вариант для MVP: gpt-4.1-nano (вы можете заменить модель позже)
    resp = client.responses.create(
        model="gpt-4.1-nano",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": free_text},
        ],
    )

    # SDK отдаёт удобное поле output_text
    data = _safe_json_load(resp.output_text)

    out: list[ExtractedAttribute] = []
    for item in data.get("attributes", []):
        try:
            out.append(
                ExtractedAttribute(
                    key=str(item.get("key", "")).strip(),
                    label=str(item.get("label", "")).strip(),
                    value=str(item.get("value", "")).strip(),
                    confidence=float(item.get("confidence", 0.0)),
                    evidence=str(item.get("evidence", "")).strip(),
                )
            )
        except Exception:
            # пропускаем битые элементы
            continue

    # минимальная фильтрация
    out = [a for a in out if a.key and a.value]
    return out

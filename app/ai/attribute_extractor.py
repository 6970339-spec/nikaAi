from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def extract_profile_attributes_free_text(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    prompt = (
        "Извлеки атрибуты из текста анкеты. "
        "Верни только JSON-массив объектов без пояснений. "
        "Пример: [{\"attribute\":\"хобби\",\"value\":\"чтение\"}].\n\n"
        f"Текст:\n{text}"
    )
    response = client.responses.create(
        model="gpt-4.1-nano",
        input=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "profile_attributes",
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "attribute": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["attribute", "value"],
                        "additionalProperties": False,
                    },
                },
            },
        },
    )
    output_text = response.output_text.strip()
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        logger.warning("AI response was not valid JSON: %s", output_text)
        start = output_text.find("[")
        end = output_text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(output_text[start : end + 1])
        raise

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


def extract_profile_attributes_free_text(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []

    client = OpenAI()
    prompt = (
        "Извлеки атрибуты из текста анкеты. "
        "Верни только JSON-массив объектов без пояснений. "
        "Пример: [{\"attribute\":\"хобби\",\"value\":\"чтение\"}].\n\n"
        f"Текст:\n{text}"
    )
    response = client.responses.create(
        model="gpt-4.1-nano",
        input=[{"role": "user", "content": prompt}],
    )
    output_text = response.output_text.strip()
    return json.loads(output_text)

"""
Валидация левой части маппинга триггера (без пакета triggers — избегаем циклического импорта с models).
"""

from typing import Dict


def validate_trigger_state_mapping_keys(mapping: Dict[str, str], label: str) -> None:
    """
    Проверяет левую часть output_mapping / input_mapping триггера.
    Запрещены variables.* — только content и context.*.
    """
    for key in mapping:
        k = key.strip()
        if not k:
            msg = f"{label}: пустой ключ в маппинге"
            raise ValueError(msg)
        if k.startswith("variables."):
            msg = (
                f"{label}: ключ {key!r} недопустим. "
                "Поля триггера укажите в context.* (например context.chat_id), не в variables."
            )
            raise ValueError(msg)
        if k.startswith("triggers."):
            msg = f"{label}: ключ {key!r} недопустим. Путь triggers.* задаёт рантайм, не маппинг."
            raise ValueError(msg)
        if k == "content":
            continue
        if k == "context" or k.startswith("context."):
            continue
        msg = f"{label}: ключ {key!r} недопустим. Допустимы: content, context, context.*"
        raise ValueError(msg)

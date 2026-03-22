"""
Пример кастомной react-ноды с хуками промпта.

Хуки before_prompt_render и after_prompt_render — изменение промпта и переменных.
"""

from typing import Any, Dict

from apps.flows.src.runtime.nodes import LlmNode
from core.logging import get_logger

logger = get_logger(__name__)


class CustomFlowWithPromptHooks(LlmNode):
    """
    Нода с хуками для изменения промпта.

    Добавляет:
    - Динамическое изменение промпта на основе state
    - Дополнительные переменные
    - Правка финального промпта
    """

    name = "custom_flow_with_prompt_hooks"
    description = "Нода с хуками для изменения промпта"

    async def before_prompt_render(
        self, prompt_template: str, state: Dict[str, Any], variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """До рендеринга промпта: шаблон и variables."""
        if state.get("user_role") == "admin":
            variables["admin_instructions"] = "Вы администратор. У вас есть полный доступ."
        else:
            variables["admin_instructions"] = ""

        if state.get("context") == "support":
            prompt_template = f"""{prompt_template}

ВАЖНО: Вы работаете в режиме поддержки клиентов.
Будьте вежливы и профессиональны."""
        elif state.get("context") == "technical":
            prompt_template = f"""{prompt_template}

ВАЖНО: Вы работаете в техническом режиме.
Используйте точную терминологию."""

        logger.info(f"[{self.node_id}] before_prompt_render: модифицирован шаблон и переменные")

        return prompt_template, variables

    async def after_prompt_render(
        self, rendered_prompt: str, state: Dict[str, Any]
    ) -> str:
        """После рендеринга: финальный текст промпта."""
        additional_info = state.get("additional_context", "")
        if additional_info:
            rendered_prompt = f"""{rendered_prompt}

Дополнительный контекст:
{additional_info}"""

        logger.debug(f"[{self.node_id}] after_prompt_render: финальный промпт ({len(rendered_prompt)} символов)")

        return rendered_prompt

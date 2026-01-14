"""
Пример кастомного агента с хуками для изменения промпта.

Демонстрирует использование хуков before_prompt_render и after_prompt_render
для изменения промпта и переменных до и после рендеринга.
"""

from typing import Any, Dict

from apps.agents.src.agent.nodes import ReactNode
from core.logging import get_logger

logger = get_logger(__name__)


class CustomAgentWithPromptHooks(ReactNode):
    """
    Кастомный агент с хуками для изменения промпта.
    
    Добавляет:
    - Динамическое изменение промпта на основе state
    - Добавление дополнительных переменных
    - Модификация финального промпта
    """

    name = "custom_agent_with_prompt_hooks"
    description = "Агент с хуками для изменения промпта"

    async def before_prompt_render(
        self, prompt_template: str, state: Dict[str, Any], variables: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Хук вызывается ДО рендеринга промпта.
        Позволяет изменить шаблон промпта и переменные.
        """
        # Пример: добавляем дополнительную переменную на основе state
        if state.get("user_role") == "admin":
            variables["admin_instructions"] = "Вы администратор. У вас есть полный доступ."
        else:
            variables["admin_instructions"] = ""

        # Пример: модифицируем шаблон промпта
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
        """
        Хук вызывается ПОСЛЕ рендеринга промпта.
        Позволяет изменить финальный промпт.
        """
        # Пример: добавляем дополнительную информацию в конец промпта
        additional_info = state.get("additional_context", "")
        if additional_info:
            rendered_prompt = f"""{rendered_prompt}

Дополнительный контекст:
{additional_info}"""

        # Пример: логируем финальный промпт (для отладки)
        logger.debug(f"[{self.node_id}] after_prompt_render: финальный промпт ({len(rendered_prompt)} символов)")

        return rendered_prompt


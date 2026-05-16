"""API для работы с промптами"""

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from apps.flows.src.dependencies import ContainerDep
from core.variables import VariableResolver

router = APIRouter(tags=["prompts"])


class RenderPromptRequest(BaseModel):
    """Запрос на рендер промпта"""

    prompt: str
    variables: dict[str, Any] | None = None


class RenderPromptResponse(BaseModel):
    """Ответ с отрендеренным промптом"""

    rendered: str
    used_variables: list[str]


@router.post("/render", response_model=RenderPromptResponse)
async def render_prompt(
    request: RenderPromptRequest,
    container: ContainerDep,
) -> RenderPromptResponse:
    """
    Рендерит промпт с подстановкой переменных.

    Используется для предпросмотра промпта с резолвом переменных.
    """
    # Резолвим @var: ссылки в variables перед рендерингом
    resolved_variables = None
    if request.variables:
        # Резолвим все @var: ссылки через VariablesService
        resolved_variables = await container.variables_service.resolve(request.variables)

        # Извлекаем значения из FlowVariableConfig формата если нужно
        if isinstance(resolved_variables, dict):
            cleaned_variables = {}
            for key, value in resolved_variables.items():
                # Проверяем, является ли это FlowVariableConfig (имеет поля value, public, title, description)
                if isinstance(value, dict) and "value" in value and ("public" in value or "title" in value or "description" in value):
                    cleaned_variables[key] = value["value"]
                else:
                    cleaned_variables[key] = value
            resolved_variables = cleaned_variables

    rendered = VariableResolver.render_template(
        template=request.prompt,
        local_vars=resolved_variables,
        safe=True,
        include_system=True,
    )

    # Извлекаем использованные переменные
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    used_variables = list(set(re.findall(pattern, request.prompt)))

    return RenderPromptResponse(
        rendered=rendered,
        used_variables=used_variables,
    )


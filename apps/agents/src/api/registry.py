"""
Registry API - совместимость с platformweb.
Предоставляет endpoints для получения списка flows и tools.
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from apps.agents.src.container import get_container
from core.logging import get_logger
from apps.agents.src.models import AgentConfig, SkillConfig
from apps.agents.src.services.agents_loader import get_all_flows

logger = get_logger(__name__)

router = APIRouter(prefix="/registry", tags=["registry"])


def get_base_url(request: Request) -> str:
    """Формирует base URL из запроса с приоритетом X-Forwarded-Proto."""
    # Приоритет X-Forwarded-Proto над request.url.scheme
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto.lower()
    else:
        scheme = request.url.scheme
    
    # Используем X-Forwarded-Host, который содержит host:port от Nginx
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host
    else:
        host = request.headers.get("host") or request.url.netloc
        # Если host не содержит порт, добавляем порт
        if ":" not in host:
            if request.url.port:
                host = f"{host}:{request.url.port}"
            elif scheme == "https":
                host = f"{host}:443"
            elif scheme == "http":
                host = f"{host}:80"
    
    return f"{scheme}://{host}"


def build_skill_info(skill_id: str, skill: SkillConfig) -> Dict[str, Any]:
    """Конвертирует SkillConfig в A2A формат."""
    return {
        "id": skill_id,
        "name": skill.name,
        "description": skill.description or "",
        "tags": skill.tags,
        "inputModes": ["text"],
        "outputModes": ["text"],
        "examples": None,
        "security": None,
    }


def build_agent_card(
    config: AgentConfig, base_url: str = "", skills: Dict[str, SkillConfig] = None
) -> Dict[str, Any]:
    """
    Собирает AgentCard из AgentConfig.
    Формат совместим с A2A протоколом и platformweb.

    Args:
        config: AgentConfig
        base_url: Базовый URL сервера
        skills: Словарь skills (если не передан, берется из config или генерируется default)
    """
    agent_id = config.agent_id
    name = config.name
    description = config.description or ""
    tags = config.tags
    config_skills = config.skills

    # Определяем skills
    if skills is not None:
        effective_skills = skills
    elif config_skills:
        effective_skills = config_skills
    else:
        # Генерируем default skill
        effective_skills = {"default": SkillConfig(name=name, description=description, tags=tags)}

    # Конвертируем skills в A2A формат
    skills_list = [
        build_skill_info(skill_id, skill) for skill_id, skill in effective_skills.items()
    ]

    card_dict = {
        "agent_id": agent_id,
        "name": name,
        "url": f"{base_url}/agents/api/v1/agents/{agent_id}",
        "description": description,
        "version": "1.0.0",
        "protocolVersion": "1.0",
        "preferredTransport": "http",
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "capabilities": {
            "streaming": False,
            "pushNotifications": None,
            "stateTransitionHistory": None,
            "extensions": None,
        },
        "skills": skills_list,
        "tags": tags,
        "provider": None,
        "documentationUrl": None,
        "iconUrl": None,
        "security": None,
        "securitySchemes": None,
        "signatures": None,
        "supportsAuthenticatedExtendedCard": False,
        "additionalInterfaces": None,
    }

    # Добавляем публичные variables как дополнительное поле (не входит в стандарт A2A)
    public_vars = {}
    if isinstance(config, AgentConfig):
        flow_variables = config.variables or {}
        for var_name, var_config in flow_variables.items():
            # AgentVariableConfig объект
            if var_config.public:
                var_value = var_config.value
                var_info = {}

                # Добавляем метаданные если есть
                if var_config.title:
                    var_info["title"] = var_config.title
                if var_config.description:
                    var_info["description"] = var_config.description

                # Обрабатываем значение
                if isinstance(var_value, str) and var_value.startswith("@var:"):
                    var_info["type"] = "reference"
                    var_info["key"] = var_value[5:]
                else:
                    var_info["value"] = var_value

                public_vars[var_name] = var_info

    if public_vars:
        card_dict["variables"] = public_vars

    return card_dict


@router.get("/agents")
async def get_agents(request: Request) -> List[Dict[str, Any]]:
    """
    Список flows как AgentCard[] (A2A формат).
    Совместимость с platformweb OrchestratorService.getAgents()
    """
    base_url = get_base_url(request)
    container = get_container()
    configs = await get_all_flows(container.agent_repository)

    agent_cards = []
    for config in configs.values():
        card = build_agent_card(config, base_url)
        agent_cards.append(card)

    return agent_cards


@router.get("/tools")
async def get_tools() -> List[Dict[str, Any]]:
    """
    Список tools в формате совместимом с platformweb.
    Совместимость с platformweb OrchestratorService.getTools()
    """
    container = get_container()
    tools = await container.tool_repository.list_all()
    return [tool.to_registry_format() for tool in tools]


@router.get("/models/values")
async def get_models_values(provider: Optional[str] = None) -> List[str]:
    """
    Список доступных моделей.
    
    Args:
        provider: Провайдер (bothub, openrouter, openai). 
                  Если не указан - используется текущий из конфига.
    """
    container = get_container()
    
    if provider:
        models = await container.llm_models_service.get_models_by_provider(provider)
    else:
        models = await container.llm_models_service.get_models()
    
    # Fallback на базовый список если БД пуста
    if not models:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]
    
    return models


@router.post("/models/sync")
async def sync_models(provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Синхронизация моделей от провайдеров.
    
    Args:
        provider: Провайдер для синхронизации. 
                  Если не указан - синхронизируются ВСЕ настроенные провайдеры.
    """
    container = get_container()
    
    if provider:
        count = await container.llm_models_service.sync_models_by_provider(provider)
        return {"provider": provider, "count": count}
    else:
        results = await container.llm_models_service.sync_all_providers()
        return {"providers": results, "total": sum(results.values())}


def _add_subagents_recursive(lines: list, parent_id: str, subagents: list, depth: int = 0) -> None:
    """Рекурсивно добавляет субагенты и их tools в Mermaid."""
    if depth > 3:  # Лимит глубины
        return

    for subagent in subagents:
        sub_id = subagent["id"].replace("_", "__")
        sub_name = subagent.get("name", subagent["id"])
        sub_safe_id = f"{parent_id}__sub__{sub_id}"

        # Субагент как закругленный прямоугольник
        lines.append(f"    {sub_safe_id}([{sub_name}]):::subagent")
        lines.append(f"    {parent_id} ==> {sub_safe_id}")

        # Tools субагента
        for sub_tool in subagent.get("tools", []):
            sub_tool_id = f"{sub_safe_id}__tool__{sub_tool.replace('_', '__')}"
            lines.append(f"    {sub_tool_id}[/{sub_tool}/]:::tool")
            lines.append(f"    {sub_safe_id} -.-> {sub_tool_id}")

        # Рекурсивно добавляем вложенных субагентов
        nested_subagents = subagent.get("subagents", [])
        if nested_subagents:
            _add_subagents_recursive(lines, sub_safe_id, nested_subagents, depth + 1)


def _generate_mermaid(skill_schema: Dict[str, Any]) -> str:
    """Генерирует Mermaid код для схемы skill."""
    lines = ["flowchart TD"]

    # Определяем классы стилей
    lines.append("    classDef agent fill:#6366f1,stroke:#818cf8,color:#fff,stroke-width:2px")
    lines.append("    classDef subagent fill:#3b82f6,stroke:#60a5fa,color:#fff,stroke-width:2px")
    lines.append("    classDef function fill:#f59e0b,stroke:#fbbf24,color:#fff,stroke-width:2px")
    lines.append("    classDef agent fill:#10b981,stroke:#34d399,color:#fff,stroke-width:2px")
    lines.append("    classDef terminal fill:#374151,stroke:#6b7280,color:#fff,stroke-width:2px")

    nodes = skill_schema["nodes"]
    edges = skill_schema["edges"]
    entry = skill_schema["entry"]

    # Собираем ноды которые реально используются в edges
    used_nodes = {entry}
    for edge in edges:
        used_nodes.add(edge["from"])
        if edge.get("to"):
            used_nodes.add(edge["to"])

    # Определяем специальные ноды
    lines.append("    start((start)):::terminal")
    lines.append("    finish((END)):::terminal")

    # Определяем класс для tools
    lines.append(
        "    classDef tool fill:#8b5cf6,stroke:#a78bfa,color:#fff,stroke-width:2px,font-size:11px"
    )

    # Определяем только используемые ноды
    for node_id, node_info in nodes.items():
        if node_id not in used_nodes:
            continue

        node_type = node_info.get("type", "unknown")
        # Безопасный ID для mermaid (заменяем _ на __)
        safe_id = node_id.replace("_", "__")

        # Имя для отображения (name агента или node_id)
        display_name = node_info.get("name", node_id)

        # Форма и класс зависит от типа
        if node_type == "code":
            # Ромб для code (условия)
            lines.append(f"    {safe_id}{{{display_name}}}:::code")
        elif node_type == "agent":
            # Двойной закругленный для agent
            lines.append(f'    {safe_id}[["{display_name}"]]:::agent')
        else:
            # Закругленный для react_node
            lines.append(f"    {safe_id}([{display_name}]):::agent")

        # Добавляем tools для react_node
        tools = node_info.get("tools", [])
        if tools and node_type == "react_node":
            for tool_name in tools:
                tool_safe_id = f"{safe_id}__tool__{tool_name.replace('_', '__')}"
                lines.append(f"    {tool_safe_id}[/{tool_name}/]:::tool")
                lines.append(f"    {safe_id} -.-> {tool_safe_id}")

        # Рекурсивно добавляем субагенты
        subagents = node_info.get("subagents", [])
        _add_subagents_recursive(lines, safe_id, subagents)

    # Отмечаем entry
    safe_entry = entry.replace("_", "__")
    lines.append(f"    start --> {safe_entry}")

    # Добавляем edges
    if edges:
        for edge in edges:
            from_node = edge["from"].replace("_", "__")
            to_node = edge.get("to")
            condition = edge.get("condition")

            if to_node is None:
                # Конец агента
                lines.append(f"    {from_node} --> finish")
            elif condition:
                # Условный переход - экранируем спецсимволы
                safe_condition = condition.replace('"', "'").replace("==", " = ")
                safe_to = to_node.replace("_", "__")
                lines.append(f"    {from_node} -->|{safe_condition}| {safe_to}")
            else:
                # Безусловный переход
                safe_to = to_node.replace("_", "__")
                lines.append(f"    {from_node} --> {safe_to}")
    else:
        # Если нет edges - соединяем entry с finish напрямую
        lines.append(f"    {safe_entry} --> finish")

    return "\n".join(lines)


def _generate_html(schema: Dict[str, Any]) -> str:
    """Генерирует HTML страницу с Mermaid диаграммами."""
    agent_id = schema["agent_id"]
    agent_name = schema["name"]
    agent_desc = schema["description"]
    skills = schema["skills"]

    skill_ids = list(skills.keys())

    # Генерируем табы и контент
    tabs_html = []
    content_html = []

    for i, skill_id in enumerate(skill_ids):
        skill = skills[skill_id]
        active = "active" if i == 0 else ""
        hidden = "" if i == 0 else "hidden"

        tabs_html.append(
            f'<button class="tab {active}" data-skill="{skill_id}">'
            f"{skill['name']} ({skill_id})</button>"
        )

        mermaid_code = _generate_mermaid(skill)
        content_html.append(f"""
        <div id="tab-{skill_id}" class="tab-content {hidden}">
            <p class="skill-desc">{skill["description"]}</p>
            <p class="skill-entry">Entry: <code>{skill["entry"]}</code></p>
            <pre class="mermaid">
{mermaid_code}
            </pre>
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{agent_name} - Schema</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

        * {{ box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0;
            padding: 30px;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0d1b2a 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        h1 {{
            color: #fff;
            margin-bottom: 8px;
            font-weight: 600;
            font-size: 28px;
        }}
        .description {{
            color: #8b8ba7;
            margin-bottom: 24px;
            font-size: 14px;
        }}
        .agent-id {{
            display: inline-block;
            background: rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            padding: 4px 12px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            margin-bottom: 24px;
        }}
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 0;
            flex-wrap: wrap;
        }}
        .tab {{
            padding: 12px 24px;
            border: none;
            background: rgba(255, 255, 255, 0.05);
            color: #8b8ba7;
            cursor: pointer;
            border-radius: 12px 12px 0 0;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s ease;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-bottom: none;
        }}
        .tab:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }}
        .tab.active {{
            background: rgba(30, 30, 60, 0.8);
            color: #fff;
            border-color: rgba(99, 102, 241, 0.3);
        }}
        .tab-content {{
            background: rgba(30, 30, 60, 0.6);
            backdrop-filter: blur(10px);
            padding: 24px;
            border-radius: 0 16px 16px 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .tab-content.hidden {{
            display: none;
        }}
        .skill-desc {{
            color: #a0a0b8;
            margin-bottom: 12px;
            font-size: 14px;
        }}
        .skill-entry {{
            color: #6b6b80;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        .skill-entry code {{
            background: rgba(99, 102, 241, 0.2);
            color: #a5b4fc;
            padding: 3px 8px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
            padding: 20px;
        }}
        /* Mermaid SVG стили */
        .mermaid .node rect {{
            rx: 12px !important;
            ry: 12px !important;
        }}
        .mermaid .node polygon {{
            stroke-linejoin: round !important;
            stroke-width: 3px !important;
        }}
        .mermaid .label {{
            color: #fff !important;
            fill: #fff !important;
            font-weight: 500 !important;
        }}
        .mermaid .edgeLabel {{
            background-color: rgba(30, 30, 60, 0.9) !important;
            color: #c4b5fd !important;
            fill: #c4b5fd !important;
            padding: 4px 8px !important;
            border-radius: 4px !important;
            font-size: 12px !important;
        }}
        .mermaid .edgePath path {{
            stroke: #6b7280 !important;
            stroke-width: 2px !important;
        }}
        .mermaid marker path {{
            fill: #6b7280 !important;
        }}
        .legend {{
            margin-top: 30px;
            padding: 20px;
            background: rgba(30, 30, 60, 0.4);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .legend h3 {{
            margin-top: 0;
            color: #fff;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 12px;
        }}
        .legend-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            color: #8b8ba7;
            font-size: 13px;
        }}
        .legend-icon {{
            width: 24px;
            height: 24px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
        }}
        .icon-agent {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }}
        .icon-subagent {{ background: linear-gradient(135deg, #3b82f6, #60a5fa); color: #fff; }}
        .icon-function {{ background: linear-gradient(135deg, #f59e0b, #f97316); color: #fff; }}
        .icon-tool {{ background: linear-gradient(135deg, #8b5cf6, #a78bfa); color: #fff; }}
        .icon-agent {{ background: linear-gradient(135deg, #10b981, #14b8a6); color: #fff; }}
        .icon-terminal {{ background: linear-gradient(135deg, #6b7280, #9ca3af); color: #fff; border-radius: 50%; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{agent_name}</h1>
        <p class="description">{agent_desc}</p>
        <div class="agent-id">{agent_id}</div>

        <div class="tabs">
            {"".join(tabs_html)}
        </div>

        {"".join(content_html)}

        <div class="legend">
            <h3>Components</h3>
            <div class="legend-grid">
                <div class="legend-item">
                    <span class="legend-icon icon-agent">A</span>
                    <span>Agent (react_node)</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-subagent">S</span>
                    <span>Subagent</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-function">F</span>
                    <span>Function</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-tool">T</span>
                    <span>Tool</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-agent">AG</span>
                    <span>Agent Node</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-terminal"></span>
                    <span>Start / End</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'dark',
            themeVariables: {{
                primaryColor: '#6366f1',
                primaryTextColor: '#fff',
                primaryBorderColor: '#818cf8',
                lineColor: '#6b7280',
                secondaryColor: '#f59e0b',
                tertiaryColor: '#1e1e3e',
                background: '#0f0f23',
                mainBkg: '#1e1e3e',
                nodeBorder: '#4b5563',
                clusterBkg: '#1e1e3e',
                clusterBorder: '#4b5563',
                titleColor: '#fff',
                edgeLabelBackground: 'transparent'
            }},
            flowchart: {{
                curve: 'basis',
                padding: 20
            }}
        }});

        // Рендерим все диаграммы при загрузке
        document.addEventListener('DOMContentLoaded', async () => {{
            // Временно показываем все табы для рендеринга
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('hidden'));

            // Рендерим Mermaid
            await mermaid.run();

            // Скрываем все кроме первого
            document.querySelectorAll('.tab-content').forEach((el, i) => {{
                if (i > 0) el.classList.add('hidden');
            }});
        }});

        // Обработчик клика на табы
        document.querySelectorAll('.tab').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const skillId = btn.dataset.skill;
                document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
                document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
                document.getElementById('tab-' + skillId).classList.remove('hidden');
                btn.classList.add('active');
            }});
        }});
    </script>
</body>
</html>"""


@router.get("/agents/{agent_id}/schema", response_class=HTMLResponse)
async def get_flow_schema(agent_id: str) -> HTMLResponse:
    """
    HTML страница с визуализацией схемы агента для всех skills.
    Использует Mermaid.js для отрисовки графов.
    """
    container = get_container()
    schema = await container.agent_factory.get_flow_schema(agent_id)

    if schema is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    html = _generate_html(schema)
    return HTMLResponse(content=html)

"""Registry API - совместимость с platformweb."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import BranchConfig, FlowConfig
from apps.flows.src.models.registry_contracts import (
    RegistryBranchInfo,
    RegistryBranchSchema,
    RegistryFlowCapabilities,
    RegistryFlowCard,
    RegistryFlowSchema,
    RegistryProviderOption,
    RegistrySchemaSubflow,
)
from apps.flows.src.services.flows_loader import get_all_flows
from core.clients.llm.model_routing import HUMANITEC_LLM_PROVIDER
from core.company_ai import CUSTOM_PROVIDER_REF_PREFIX, AICapability, CompanyAIProviders
from core.context import get_context
from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(prefix="/registry", tags=["registry"])

_LLM_CAPABILITY_VALUES = {
    AICapability.LLM_CHAT.value,
    AICapability.LLM_SUMMARIZE.value,
    AICapability.LLM_FORMAT_MARKDOWN.value,
    AICapability.LLM_CODEGEN.value,
    AICapability.LLM_VISION.value,
    AICapability.IMAGE_GEN.value,
}


def _company_ai_from_context() -> CompanyAIProviders:
    context = get_context()
    if context is None or context.active_company is None:
        return CompanyAIProviders()
    return CompanyAIProviders.from_metadata(context.active_company.metadata)


def _custom_provider_options(aip: CompanyAIProviders) -> list[RegistryProviderOption]:
    items: list[RegistryProviderOption] = []
    for provider in aip.custom_providers:
        if not any(cap in _LLM_CAPABILITY_VALUES for cap in provider.capabilities):
            continue
        items.append(
            RegistryProviderOption(
                value=f"{CUSTOM_PROVIDER_REF_PREFIX}{provider.id}",
                label=provider.label,
                kind="custom",
                custom_id=provider.id,
            )
        )
    return items


def _platform_provider_options(providers: list[str]) -> list[str | RegistryProviderOption]:
    out: list[str | RegistryProviderOption] = []
    for provider in providers:
        if provider == HUMANITEC_LLM_PROVIDER:
            out.append(
                RegistryProviderOption(
                    value=HUMANITEC_LLM_PROVIDER,
                    label="Humanitec LLM",
                    kind="virtual",
                )
            )
            continue
        out.append(provider)
    return out


def _custom_provider_models(aip: CompanyAIProviders, provider_ref: str) -> list[str]:
    if not provider_ref.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        return []
    custom_id = provider_ref[len(CUSTOM_PROVIDER_REF_PREFIX) :].strip()
    try:
        provider = aip.find_custom(custom_id)
    except KeyError:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for cap in _LLM_CAPABILITY_VALUES:
        model = provider.model_by_capability.get(cap)
        if model and model not in seen:
            out.append(model)
            seen.add(model)
    return out


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


def build_branch_info(branch_id: str, branch: BranchConfig) -> RegistryBranchInfo:
    """Конвертирует BranchConfig в элемент списка branches карточки агента (A2A)."""
    return RegistryBranchInfo(
        id=branch_id,
        name=branch.name,
        description=branch.description or "",
        tags=branch.tags,
        inputModes=["text"],
        outputModes=["text"],
        examples=None,
        security=None,
    )


def build_flow_card(
    config: FlowConfig, base_url: str = "", branches: dict[str, BranchConfig] | None = None
) -> RegistryFlowCard:
    """
    Собирает AgentCard из FlowConfig.
    Формат совместим с A2A протоколом и platformweb.

    Args:
        config: FlowConfig
        base_url: Базовый URL сервера
        branches: Словарь веток (если не передан, берётся из config или генерируется default)
    """
    flow_id = config.flow_id
    name = config.name
    description = config.description or ""
    tags = config.tags
    config_branches = config.branches

    if branches is not None:
        effective_branches = branches
    elif config_branches:
        effective_branches = config_branches
    else:
        effective_branches = {"default": BranchConfig(name=name, description=description, tags=tags)}

    branches_list = [
        build_branch_info(branch_id, br) for branch_id, br in effective_branches.items()
    ]

    public_vars: dict[str, JsonObject] = {}
    for var_name, var_config in (config.variables or {}).items():
        if not var_config.public:
            continue
        var_value = var_config.value
        var_info: JsonObject = {}
        if var_config.title:
            var_info["title"] = var_config.title
        if var_config.description:
            var_info["description"] = var_config.description
        if isinstance(var_value, str) and var_value.startswith("@var:"):
            var_info["type"] = "reference"
            var_info["key"] = var_value[5:]
        else:
            var_info["value"] = var_value
        public_vars[var_name] = var_info

    return RegistryFlowCard(
        flow_id=flow_id,
        name=name,
        url=f"{base_url}/flows/api/v1/flows/{flow_id}",
        description=description,
        version="1.0.0",
        protocolVersion="1.0",
        preferredTransport="http",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=RegistryFlowCapabilities(
            streaming=False,
            pushNotifications=None,
            stateTransitionHistory=None,
            extensions=None,
        ),
        branches=branches_list,
        tags=tags,
        provider=None,
        documentationUrl=None,
        iconUrl=None,
        security=None,
        securitySchemes=None,
        signatures=None,
        supportsAuthenticatedExtendedCard=False,
        additionalInterfaces=None,
        variables=public_vars or None,
    )


@router.get("/flows")
async def list_registry_flows(request: Request, container: ContainerDep) -> list[RegistryFlowCard]:
    """
    Список flows как AgentCard[] (A2A формат).
    """
    base_url = get_base_url(request)
    configs = await get_all_flows(container.flow_repository)

    cards: list[RegistryFlowCard] = []
    for config in configs.values():
        card = build_flow_card(config, base_url)
        cards.append(card)

    return cards


@router.get("/tools")
async def get_tools(container: ContainerDep) -> list[JsonObject]:
    """
    Список tools в формате совместимом с platformweb.
    Совместимость с platformweb OrchestratorService.getTools()
    """
    tools = await container.tool_repository.list(limit=10000)
    return [tool.to_registry_format() for tool in tools]


@router.get("/providers/values")
async def get_providers_values(container: ContainerDep) -> list[str | RegistryProviderOption]:
    """
    Список настроенных LLM-провайдеров платформы и custom-провайдеров активной компании.
    """
    platform_items = _platform_provider_options(container.llm_models_service.get_configured_providers())
    return [*platform_items, *_custom_provider_options(_company_ai_from_context())]


@router.get("/models/values")
async def get_models_values(container: ContainerDep, provider: str | None = None) -> list[str]:
    """
    Список доступных моделей.

    Args:
        provider: Провайдер (bothub, openrouter, openai, yandex, humanitec_llm).
                  Если не указан - используется текущий из конфига.
    """

    if provider and provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        models = _custom_provider_models(_company_ai_from_context(), provider)
    elif provider:
        models = await container.llm_models_service.get_models_by_provider(provider)
    else:
        models = await container.llm_models_service.get_models()

    return models


@router.post("/models/sync")
async def sync_models(container: ContainerDep, provider: str | None = None) -> JsonObject:
    """
    Синхронизация моделей от провайдеров.

    Args:
        provider: Провайдер для синхронизации.
                  Если не указан - синхронизируются ВСЕ настроенные провайдеры.
    """

    if provider:
        count = await container.llm_models_service.sync_models_by_provider(provider)
        return {"provider": provider, "count": count}
    else:
        results = await container.llm_models_service.sync_all_providers()
        return {"providers": results, "total": sum(results.values())}


def _add_subflows_recursive(
    lines: list[str],
    parent_id: str,
    subflows: list[RegistrySchemaSubflow],
    depth: int = 0,
) -> None:
    """Рекурсивно добавляет вложенные flow (как tools) и их tools в Mermaid."""
    if depth > 3:
        return

    for subflow in subflows:
        sub_id = subflow.id.replace("_", "__")
        sub_name = subflow.name
        sub_safe_id = f"{parent_id}__sub__{sub_id}"

        lines.append(f"    {sub_safe_id}([{sub_name}]):::subflow")
        lines.append(f"    {parent_id} ==> {sub_safe_id}")

        for sub_tool in subflow.tools:
            sub_tool_id = f"{sub_safe_id}__tool__{sub_tool.replace('_', '__')}"
            lines.append(f"    {sub_tool_id}[/{sub_tool}/]:::tool")
            lines.append(f"    {sub_safe_id} -.-> {sub_tool_id}")

        nested = subflow.subflows
        if nested:
            _add_subflows_recursive(lines, sub_safe_id, nested, depth + 1)


def _generate_mermaid(branch_schema: RegistryBranchSchema) -> str:
    """Генерирует Mermaid код для схемы ветки (branch)."""
    lines = ["flowchart TD"]

    lines.append("    classDef react fill:#6366f1,stroke:#818cf8,color:#fff,stroke-width:2px")
    lines.append("    classDef subflow fill:#3b82f6,stroke:#60a5fa,color:#fff,stroke-width:2px")
    lines.append("    classDef function fill:#f59e0b,stroke:#fbbf24,color:#fff,stroke-width:2px")
    lines.append("    classDef flow fill:#ec4899,stroke:#f472b6,color:#fff,stroke-width:2px")
    lines.append("    classDef terminal fill:#374151,stroke:#6b7280,color:#fff,stroke-width:2px")

    nodes = branch_schema.nodes
    edges = branch_schema.edges
    entry = branch_schema.entry

    # Собираем ноды которые реально используются в edges
    used_nodes = {entry}
    for edge in edges:
        used_nodes.add(edge.from_node)
        if edge.to:
            used_nodes.add(edge.to)

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

        node_type = node_info.type
        # Безопасный ID для mermaid (заменяем _ на __)
        safe_id = node_id.replace("_", "__")

        # Имя для отображения (name агента или node_id)
        display_name = node_info.name

        # Форма и класс зависит от типа
        if node_type == "code":
            # Ромб для code (условия)
            lines.append(f"    {safe_id}{{{display_name}}}:::code")
        elif node_type == "flow":
            # Вложенный flow (subflow)
            lines.append(f'    {safe_id}[["{display_name}"]]:::flow')
        else:
            lines.append(f"    {safe_id}([{display_name}]):::react")

        # Добавляем tools для llm_node
        tools = node_info.tools
        if tools and node_type == "llm_node":
            for tool_name in tools:
                tool_safe_id = f"{safe_id}__tool__{tool_name.replace('_', '__')}"
                lines.append(f"    {tool_safe_id}[/{tool_name}/]:::tool")
                lines.append(f"    {safe_id} -.-> {tool_safe_id}")

        _add_subflows_recursive(lines, safe_id, node_info.subflows)

    # Отмечаем entry
    safe_entry = entry.replace("_", "__")
    lines.append(f"    start --> {safe_entry}")

    # Добавляем edges
    if edges:
        for edge in edges:
            from_node = edge.from_node.replace("_", "__")
            to_node = edge.to
            condition = edge.condition

            if to_node is None:
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


def _generate_html(schema: RegistryFlowSchema) -> str:
    """Генерирует HTML страницу с Mermaid диаграммами."""
    flow_id = schema.flow_id
    flow_title = schema.name
    flow_description = schema.description
    branches_map = schema.branches

    branch_ids = list(branches_map.keys())

    # Генерируем табы и контент
    tabs_html: list[str] = []
    content_html: list[str] = []

    for i, branch_id in enumerate(branch_ids):
        branch_payload = branches_map[branch_id]
        active = "active" if i == 0 else ""
        hidden = "" if i == 0 else "hidden"

        tabs_html.append(f'<button class="tab {active}" data-branch="{branch_id}">{branch_payload.name} ({branch_id})</button>')

        mermaid_code = _generate_mermaid(branch_payload)
        content_html.append(f"""
        <div id="tab-{branch_id}" class="tab-content {hidden}">
            <p class="branch-desc">{branch_payload.description}</p>
            <p class="branch-entry">Entry: <code>{branch_payload.entry}</code></p>
            <pre class="mermaid">
{mermaid_code}
            </pre>
        </div>
        """)

    tabs_markup = "".join(tabs_html)
    content_markup = "".join(content_html)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="{PLATFORM_MOBILE_VIEWPORT_CONTENT}">
    <title>{flow_title} - Schema</title>
    <script src="/static/core/assets/js/mermaid/mermaid.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
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
        .flow-id {{
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
        .branch-desc {{
            color: #a0a0b8;
            margin-bottom: 12px;
            font-size: 14px;
        }}
        .branch-entry {{
            color: #6b6b80;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        .branch-entry code {{
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
        .icon-react {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }}
        .icon-subflow {{ background: linear-gradient(135deg, #3b82f6, #60a5fa); color: #fff; }}
        .icon-function {{ background: linear-gradient(135deg, #f59e0b, #f97316); color: #fff; }}
        .icon-tool {{ background: linear-gradient(135deg, #8b5cf6, #a78bfa); color: #fff; }}
        .icon-flow-node {{ background: linear-gradient(135deg, #10b981, #14b8a6); color: #fff; }}
        .icon-terminal {{ background: linear-gradient(135deg, #6b7280, #9ca3af); color: #fff; border-radius: 50%; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{flow_title}</h1>
        <p class="description">{flow_description}</p>
        <div class="flow-id">{flow_id}</div>

        <div class="tabs">
            {tabs_markup}
        </div>

        {content_markup}

        <div class="legend">
            <h3>Components</h3>
            <div class="legend-grid">
                <div class="legend-item">
                    <span class="legend-icon icon-react">R</span>
                    <span>React node</span>
                </div>
                <div class="legend-item">
                    <span class="legend-icon icon-subflow">N</span>
                    <span>Nested flow (tool)</span>
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
                    <span class="legend-icon icon-flow-node">FN</span>
                    <span>Flow node (subgraph)</span>
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
                const branchId = btn.dataset.branch;
                document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
                document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
                document.getElementById('tab-' + branchId).classList.remove('hidden');
                btn.classList.add('active');
            }});
        }});
    </script>
</body>
</html>"""


@router.get("/flows/{flow_id}/schema", response_class=HTMLResponse)
async def get_flow_schema(flow_id: str, container: ContainerDep) -> HTMLResponse:
    """
    HTML страница с визуализацией схемы агента для всех веток (branches).
    Использует Mermaid.js для отрисовки графов.
    """
    schema = await container.flow_factory.get_flow_schema(flow_id)

    if schema is None:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    html = _generate_html(schema)
    return HTMLResponse(content=html)

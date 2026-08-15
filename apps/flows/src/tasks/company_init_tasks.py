"""
TaskIQ задачи для инициализации компаний и system.
"""

from pathlib import Path

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.agent_toolkit_service import bootstrap_agent_toolkits_from_registry
from apps.flows.src.services.demo_company_variables import seed_demo_company_variables
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from apps.flows.src.services.hitl_demo_queue import (
    ensure_example_hitl_queue,
    hitl_demo_operator_user_ids,
)
from apps.flows.src.services.mcp_catalog_crawler import upsert_allowlist_seed_entries_only
from apps.flows.src.services.mcp_catalog_provisioner import provision_mcp_catalog_for_company
from apps.flows.src.services.mcp_sync import (
    ensure_default_mcp_servers_for_company,
    sync_auto_mcp_servers_for_company,
)
from apps.flows.src.services.platform_assistant_skills import seed_platform_assistant_skills
from apps.flows.src.tasks.task_names import TASK_INIT_COMPANY_RESOURCES
from core.authz.company_sync import sync_company_member_roles
from core.authz.group_sync import sync_user_groups
from core.context import Context, clear_context, set_context
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(TASK_INIT_COMPANY_RESOURCES)
async def init_company_resources(
    company_id: str,
    company_name: str = "",
    subdomain: str = ""
) -> JsonObject:
    """
    Универсальная задача инициализации ресурсов для компании.

    Если company_id == "system":
        Загружает ВСЕ агенты и тулы из registry в system namespace
        (триггер: idle `company_init_system` при старте idle_worker)

    Иначе:
        Загружает ТОЛЬКО PUBLIC агенты и тулы из кода в company namespace
        (триггер: idle `company_init_new_company` при создании компании)

    Аргументы:
        company_id: "system" или ID компании
        company_name: Название компании (для логов)
        subdomain: Subdomain компании (slug)

    Возвращает:
        {"flows": count, "tools": count, "nodes": count, "status": "completed"}
    """
    is_system = (company_id == "system")
    action = "Загрузка" if is_system else "Копирование"
    company_display_name = company_name.strip() if company_name.strip() else company_id
    company_subdomain = subdomain.strip() if subdomain.strip() else None

    logger.info(
        f"{action} ресурсов для компании: {company_id} ({company_display_name})"
    )

    # Установить контекст компании
    company_context = Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host="system",
        session_id=f"init_company_{company_id}",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id=company_id,
            name=company_display_name,
            subdomain=company_subdomain,
        ),
        user_companies=[],
        trace_id=f"system:init_company:{company_id}",
    )
    _ = set_context(company_context)

    try:
        container = get_container()
        await sync_company_member_roles(
            container.authz_service,
            company_id=company_id,
            user_id="system",
            roles=["owner", "admin"],
        )
        await sync_user_groups(
            container.authz_service,
            user_id="system",
            groups=["admin", "developers"],
            company_ids=[company_id],
            previous_groups=[],
        )

        # Путь к единому registry
        registry_path = Path(__file__).parent.parent.parent / "registry.yaml"
        bundles_dir = Path(__file__).parent.parent.parent / "bundles"

        # Загружаем tools (для ВСЕХ компаний, включая system)
        loaded_tools = await load_tools_to_db(
        container.tool_repository,
        flow_access_service=container.flow_access_service,
    )
        logger.info(f"Загружено {len(loaded_tools)} tools для {company_id}")

        try:
            runtime_container = as_flow_runtime_container(container)
            seed_stats = await upsert_allowlist_seed_entries_only(container=runtime_container)
            logger.info(
                "MCP allowlist seed для %s: upserted=%s verified=%s verify_failed=%s",
                company_id,
                seed_stats.upserted,
                seed_stats.verified,
                seed_stats.verify_failed,
            )
            _ = await ensure_default_mcp_servers_for_company(container=runtime_container)
            catalog_stats = await provision_mcp_catalog_for_company(container=runtime_container)
            synced = await sync_auto_mcp_servers_for_company(container=runtime_container)
            logger.info(
                "MCP синхронизация для %s: catalog_added=%s catalog_updated=%s servers=%s tools=%s",
                company_id,
                catalog_stats.added,
                catalog_stats.updated,
                synced["servers"],
                synced["tools"],
            )
        except Exception as mcp_err:
            logger.error(
                "MCP синхронизация при init_company_resources failed (%s): %s",
                company_id,
                mcp_err,
                exc_info=True,
            )
            raise

        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
            flow_access_service=container.flow_access_service,
        )

        # Универсальный метод - работает и для system и для company
        # Для system фильтр public отключен, для company - включен
        stats = await loader.load_all_for_company(
            company_id=company_id,
            filter_public=(company_id != "system")
        )

        toolkits_loaded = await bootstrap_agent_toolkits_from_registry(
            container.agent_toolkit_repository,
            registry_path,
            filter_public=(company_id != "system"),
        )
        stats["agent_toolkits"] = toolkits_loaded

        seeded_variables = await seed_demo_company_variables(
            container.variables_service,
            company_id,
        )
        stats["demo_variables"] = seeded_variables

        seeded_skills = await seed_platform_assistant_skills(
            container.agent_skill_service,
            container.files_service,
            company_id,
        )
        stats["platform_assistant_skills"] = seeded_skills

        stored_company = await container.company_repository.get(company_id)
        member_user_ids: list[str] = []
        if stored_company is not None:
            member_user_ids = await hitl_demo_operator_user_ids(
                container.authz_service, company_id
            )
            owner_user_id = stored_company.owner_user_id
            if (
                not member_user_ids
                and owner_user_id is not None
                and owner_user_id.strip() != ""
            ):
                raw_owner_roles = stored_company.members.get(owner_user_id)
                owner_roles: list[str] = (
                    list(raw_owner_roles)
                    if raw_owner_roles is not None and len(raw_owner_roles) > 0
                    else ["owner", "admin"]
                )
                await sync_company_member_roles(
                    container.authz_service,
                    company_id=company_id,
                    user_id=owner_user_id,
                    roles=owner_roles,
                )
                member_user_ids = await hitl_demo_operator_user_ids(
                    container.authz_service, company_id
                )
        await ensure_example_hitl_queue(
            container.work_item_service,
            company_id,
            member_user_ids=member_user_ids,
        )

        # Обновляем статистику tools
        stats["tools"] = len(loaded_tools)

        logger.info(
            "%s завершено для %s: flows=%s, tools=%s, nodes=%s",
            action,
            company_id,
            stats["flows"],
            stats["tools"],
            stats["nodes"],
        )

        return {
            **stats,
            "status": "completed",
            "company_id": company_id,
        }

    except Exception as e:
        logger.error(
            f"Ошибка {action.lower()} для {company_id}: {e}",
            exc_info=True
        )
        raise
    finally:
        clear_context()

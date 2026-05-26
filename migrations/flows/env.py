"""
Alembic env для БД сервиса flows.

Таблицы: flows, flows_versions, nodes, tools, durable workflow ledger,
evaluation lab, resources, operator queues/tasks.
"""

import asyncio
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from apps.flows.src.db.models import (  # noqa: F401
    ActivityTasks,
    Base,
    EvaluationCaseRuns,
    EvaluationCases,
    EvaluationRunEvents,
    EvaluationRuns,
    EvaluationSuites,
    EvaluationSuiteVersions,
    ExecutionBranches,
    Flows,
    FlowsVersions,
    Nodes,
    OperatorQueueMembers,
    OperatorQueues,
    OperatorTasks,
    Resources,
    Tools,
    WorkflowEvents,
    WorkflowInstances,
    WorkflowSnapshots,
)

config = context.config
logger = logging.getLogger("alembic.env")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

MANAGED_TABLES = {
    "flows", "flows_versions", "nodes", "tools",
    "workflow_instances", "execution_branches", "workflow_events",
    "workflow_snapshots", "activity_tasks",
    "evaluation_suites", "evaluation_cases",
    "evaluation_suite_versions", "evaluation_runs", "evaluation_case_runs",
    "evaluation_run_events", "resources",
    "operator_queues", "operator_queue_members", "operator_tasks",
}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in MANAGED_TABLES
    return True


def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from core.config import get_settings
    settings = get_settings()
    if not settings.database.flows_url:
        raise ValueError("DATABASE__FLOWS_URL не настроен")
    return settings.database.flows_url


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        do_run_migrations(connectable)
    else:
        asyncio.run(_run_async())


async def _run_async() -> None:
    engine = create_async_engine(_get_url(), poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

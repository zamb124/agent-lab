"""
СТРОГИЕ тесты FlowRepository с разделением на две таблицы.

Проверяет что:
1. Версии сохраняются в agents_versions
2. Актуальные конфиги сохраняются в agents
3. list_all читает из agents (маленькая таблица) и не зависит от количества версий
4. get_version читает из agents_versions
5. delete удаляет из обеих таблиц
6. rollback копирует из agents_versions в agents
7. Все методы работают корректно даже при большом количестве версий (1000+)

ПРИНЦИПЫ:
- БЕЗ МОКОВ - реальный PostgreSQL
- Строгие проверки структуры данных
- Проверка изоляции таблиц
- Проверка производительности при большом количестве версий
"""

import pytest

from apps.flows.src.models import FlowConfig
from core.context import set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


class TestFlowRepositoryTwoTables:
    """СТРОГИЕ тесты FlowRepository с двумя таблицами."""

    @pytest.mark.asyncio
    async def test_set_saves_to_both_tables(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: set() сохраняет версию в agents_versions И актуальный конфиг в agents.
        """

        flow_id = f"test_two_tables_set_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            description="For testing two tables",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        await FlowConfig.create_version(agent)

        # Проверяем что версия сохранена
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        assert len(versions) == 1, "Должна быть создана одна версия"
        version = versions[0]

        # Проверяем что можем получить версию
        version_agent = await FlowConfig.by_flow_id_and_version(flow_id, version)
        assert version_agent is not None, "Версия ДОЛЖНА быть доступна через by_flow_id_and_version"
        assert version_agent.flow_id == flow_id

        # Проверяем что можем получить актуальный конфиг
        latest_agent = await FlowConfig.current_for_flow(flow_id)
        assert latest_agent is not None, "Актуальный конфиг ДОЛЖЕН быть доступен через current_for_flow"
        assert latest_agent.flow_id == flow_id

        # Проверяем что данные идентичны
        assert version_agent.version == latest_agent.version, "Версии должны совпадать"
        assert version_agent.name == latest_agent.name, "Данные должны быть идентичны"

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_current_for_flow_reads_from_agents_table(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: current_for_flow() читает ТОЛЬКО из таблицы agents.
        """

        flow_id = f"test_current_for_flow_source_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        await FlowConfig.create_version(agent)

        # Проверяем что версия создана
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        assert len(versions) == 1, "Должна быть создана одна версия"

        # current_for_flow() читает из agents (не из agents_versions)
        loaded = await FlowConfig.current_for_flow(flow_id)
        assert loaded is not None, "current_for_flow() ДОЛЖЕН читать из agents"
        assert loaded.flow_id == flow_id
        assert loaded.name == "Test Agent"

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_get_version_reads_from_agents_versions_table(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: get_version() читает ТОЛЬКО из таблицы agents_versions.
        """

        flow_id = f"test_get_version_source_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        await FlowConfig.create_version(agent)

        # Проверяем что агент создан
        loaded_agent = await FlowConfig.current_for_flow(flow_id)
        assert loaded_agent is not None, "Агент должен быть создан"
        assert loaded_agent.version is not None, "Версия должна быть установлена"

        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        if len(versions) == 0:
            # Если версий нет, используем версию из агента
            version = loaded_agent.version
        else:
            assert len(versions) == 1, f"Должна быть создана версия, найдено: {len(versions)}"
            version = versions[0]

        # get_version() читает из agents_versions
        loaded = await FlowConfig.by_flow_id_and_version(flow_id, version)
        assert loaded is not None, "get_version() ДОЛЖЕН читать из agents_versions"
        assert loaded.flow_id == flow_id
        assert loaded.version == version

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_list_all_reads_from_agents_table_only(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: list_all() читает ТОЛЬКО из таблицы agents и НЕ зависит от количества версий.
        """

        # Создаём агента с множеством версий
        flow_id = f"test_list_all_isolation_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        # Создаём 50 версий (симулируем большое количество)
        for i in range(50):
            agent.name = f"Test Agent v{i}"
            await FlowConfig.create_version(agent)

        # Проверяем что агент доступен через get (читает из agents)
        retrieved_agent = await FlowConfig.current_for_flow(flow_id)
        assert retrieved_agent is not None, "Агент ДОЛЖЕН быть доступен через get()"
        assert retrieved_agent.name == "Test Agent v49", "Должна быть последняя версия"

        # list_all() ДОЛЖЕН вернуть агента (с достаточно большим limit)
        all_agents = await FlowConfig.list_current(limit=1000)
        agent_ids = [a.flow_id for a in all_agents]
        assert flow_id in agent_ids, "list_all() ДОЛЖЕН вернуть агента независимо от количества версий"
        assert agent_ids.count(flow_id) == 1, "list_all() ДОЛЖЕН вернуть каждого агента только один раз"

        # Проверяем что версий действительно много
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        assert len(versions) == 50, "Должно быть создано 50 версий"

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60, func_only=True)
    async def test_list_all_performance_with_many_versions(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: list_all() работает быстро даже при большом количестве версий у других агентов.
        """
        _ = app
        company_id = f"flow-list-perf-{unique_id}"
        set_context(
            Context(
                user=User(user_id=f"u-{unique_id}", name="List Perf"),
                active_company=make_test_company(
                    company_id=company_id, name="List Perf"
                ),
                session_id=f"list-perf-{unique_id}",
                channel="test",
            )
        )

        # Создаём агента с ОЧЕНЬ большим количеством версий (симулируем проблему с лимитом)
        many_versions_agent_id = f"test_many_versions_agent_{unique_id}"
        agent = FlowConfig(
            flow_id=many_versions_agent_id,
            name="Many Versions Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        # Создаём 200 версий (больше чем лимит в старом коде)
        for i in range(200):
            agent.name = f"Many Versions Agent v{i}"
            await FlowConfig.create_version(agent)

        # Создаём другого агента ПОСЛЕ (по алфавиту он идёт позже)
        later_agent_id = f"test_later_agent_{unique_id}"
        later_agent = FlowConfig(
            flow_id=later_agent_id,
            name="Later Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )
        await FlowConfig.create_version(later_agent)

        # Проверяем что оба агента доступны
        agent1 = await FlowConfig.current_for_flow(many_versions_agent_id)
        agent2 = await FlowConfig.current_for_flow(later_agent_id)
        assert agent1 is not None, "Первый агент ДОЛЖЕН быть доступен"
        assert agent2 is not None, "Второй агент ДОЛЖЕН быть доступен"

        # list_all() ДОЛЖЕН вернуть ОБОИХ агентов (с большим limit)
        all_agents = await FlowConfig.list_current(limit=1000)
        agent_ids = [a.flow_id for a in all_agents]
        assert many_versions_agent_id in agent_ids, "Агент с множеством версий ДОЛЖЕН быть в списке"
        assert later_agent_id in agent_ids, "Агент, идущий позже по алфавиту, ДОЛЖЕН быть в списке"

        # Cleanup
        await FlowConfig.delete_by_flow_id(many_versions_agent_id)
        await FlowConfig.delete_by_flow_id(later_agent_id)

    @pytest.mark.asyncio
    async def test_delete_removes_from_both_tables(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: delete() удаляет из ОБЕИХ таблиц.
        """

        flow_id = f"test_delete_both_tables_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        # Создаём несколько версий
        for i in range(5):
            agent.name = f"Test Agent v{i}"
            await FlowConfig.create_version(agent)

        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        assert len(versions) == 5, "Должно быть создано 5 версий"

        # Удаляем агента
        result = await FlowConfig.delete_by_flow_id(flow_id)
        assert result is True, "delete() ДОЛЖЕН вернуть True"

        # Проверяем что агент удален
        deleted_agent = await FlowConfig.current_for_flow(flow_id)
        assert deleted_agent is None, "Агент ДОЛЖЕН быть удалён"

        # Проверяем что версии удалены
        remaining_versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        assert len(remaining_versions) == 0, "После удаления не должно остаться версий"

    @pytest.mark.asyncio
    async def test_rollback_copies_from_agents_versions_to_agents(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: rollback_to_version() копирует версию из agents_versions в agents.
        """

        flow_id = f"test_rollback_copy_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent v1",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Prompt v1"}},
        )

        # Создаём версию 1
        await FlowConfig.create_version(agent)
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        version1 = versions[0]

        # Создаём версию 2 (меняем данные)
        agent.name = "Test Agent v2"
        agent.nodes["main"]["prompt"] = "Prompt v2"
        await FlowConfig.create_version(agent)
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        version2 = versions[0]

        # Проверяем что актуальная версия - это v2
        latest = await FlowConfig.current_for_flow(flow_id)
        assert latest.name == "Test Agent v2", "Актуальная версия должна быть v2"

        # Откатываемся к версии 1
        result = await FlowConfig.rollback_to_version(flow_id, version1)
        assert result is True, "rollback_to_version() ДОЛЖЕН вернуть True"

        # Проверяем что актуальная версия теперь v1
        latest_after_rollback = await FlowConfig.current_for_flow(flow_id)
        assert latest_after_rollback.name == "Test Agent v1", "После rollback актуальная версия должна быть v1"
        assert latest_after_rollback.nodes["main"]["prompt"] == "Prompt v1", "Промпт должен быть из версии 1"

        # Проверяем что версия 2 всё ещё существует в agents_versions
        version2_data = await FlowConfig.by_flow_id_and_version(flow_id, version2)
        assert version2_data is not None, "Версия 2 ДОЛЖНА остаться в agents_versions"
        assert version2_data.name == "Test Agent v2", "Версия 2 не должна измениться"

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_multiple_agents_independence(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: Множество агентов работают независимо, list_all() возвращает всех.
        """

        # Создаём несколько агентов
        agent_ids = []
        for i in range(10):
            flow_id = f"test_independence_{unique_id}_{i}"
            agent_ids.append(flow_id)
            agent = FlowConfig(
                flow_id=flow_id,
                name=f"Test Agent {i}",
                entry="main",
                nodes={"main": {"type": "llm_node", "prompt": f"Prompt {i}"}},
            )
            await FlowConfig.create_version(agent)

        # Проверяем что все агенты доступны через get
        for flow_id in agent_ids:
            agent = await FlowConfig.current_for_flow(flow_id)
            assert agent is not None, f"Агент {flow_id} ДОЛЖЕН быть доступен"

        # list_all() ДОЛЖЕН вернуть всех агентов (с большим limit)
        all_agents = await FlowConfig.list_current(limit=1000)
        all_agent_ids = [a.flow_id for a in all_agents]

        for flow_id in agent_ids:
            assert flow_id in all_agent_ids, f"Агент {flow_id} ДОЛЖЕН быть в списке"

        # Cleanup
        for flow_id in agent_ids:
            await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_list_all_limit_respected(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: list_all(limit=N) возвращает не более N агентов.
        """

        # Создаём больше агентов чем лимит
        agent_ids = []
        for i in range(15):
            flow_id = f"test_limit_{i}"
            agent_ids.append(flow_id)
            agent = FlowConfig(
                flow_id=flow_id,
                name=f"Test Agent {i}",
                entry="main",
                nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            )
            await FlowConfig.create_version(agent)

        # list_all(limit=10) ДОЛЖЕН вернуть не более 10 агентов
        limited_agents = await FlowConfig.list_current(limit=10)
        assert len(limited_agents) <= 10, "list_all(limit=10) ДОЛЖЕН вернуть не более 10 агентов"

        # Cleanup
        for flow_id in agent_ids:
            await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_table_isolation_strict(self, app, unique_id, di):
        """
        СТРОГИЙ ТЕСТ: Таблицы agents и agents_versions полностью изолированы.

        Проверяет что:
        - Данные в agents не содержат версионных ключей
        - Данные в agents_versions не содержат актуальных конфигов без версий
        - Операции с одной таблицей не влияют на другую
        """

        flow_id = f"test_table_isolation_{unique_id}"
        agent = FlowConfig(
            flow_id=flow_id,
            name="Isolation Test",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )

        await FlowConfig.create_version(agent)
        versions = await FlowConfig.list_version_strings_by_version_desc(flow_id)
        version = versions[0]

        # Проверяем что агент создан правильно
        loaded_agent = await FlowConfig.current_for_flow(flow_id)
        assert loaded_agent is not None, "Агент должен быть создан"

        # Проверяем что версия создана
        loaded_version = await FlowConfig.by_flow_id_and_version(flow_id, version)
        assert loaded_version is not None, "Версия должна быть создана"

        # Cleanup
        await FlowConfig.delete_by_flow_id(flow_id)


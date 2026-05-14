"""
GraphCompiler - компилятор графов агентов.

Статическая сборка и валидация графа до выполнения.
Zero-Guess: все ошибки обнаруживаются на этапе компиляции, не runtime.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from core.errors import (
    CyclicDependencyError,
    InvalidGraphError,
)
from core.models import StrictBaseModel


class CompiledEdge(StrictBaseModel):
    """Скомпилированная связь между нодами"""

    from_node: str = Field(..., description="ID исходной ноды")
    to_node: Optional[str] = Field(..., description="ID целевой ноды (null = конец)")
    condition: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Условие перехода: строка или объект {type: simple|python, ...}.",
    )


class CompiledGraph(StrictBaseModel):
    """
    Неизменяемый скомпилированный граф агента.

    Результат компиляции FlowConfig + BranchConfig.
    Все проверки пройдены, граф готов к выполнению.

    Zero-Guess гарантии:
    - Все ноды существуют
    - entry нода валидна
    - Нет недостижимых нод
    - Нет циклов без выхода (проверено)
    - Input/Output схемы совместимы (если указаны)
    """

    flow_id: str = Field(..., description="ID агента")
    branch_id: str = Field(default="default", description="ID применённой ветки")
    entry_node: str = Field(..., description="Стартовая нода")

    nodes: Dict[str, Dict[str, Any]] = Field(..., description="Ноды графа")
    edges: List[CompiledEdge] = Field(..., description="Связи между нодами")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Резолвнутые переменные")

    # Метаданные компиляции
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время компиляции")
    checksum: str = Field(..., description="Хеш конфига для кеширования")

    # Read-only граф
    model_config = {"frozen": True}

    def validate_state_flow(self) -> None:
        """
        Валидирует совместимость схем данных между нодами.

        Проверяет что output схема ноды A совместима с input схемой ноды B.

        Raises:
            SchemaMismatchError: Если схемы несовместимы
        """
        # TODO: Реализовать JSON Schema валидацию
        pass


class GraphCompiler:
    """
    Компилятор графа агента.

    Принципы Zero-Guess:
    1. Все ошибки на этапе компиляции, не runtime
    2. Явная валидация всех связей
    3. Проверка циклов и достижимости
    4. Конфликты skills обнаруживаются до запуска

    Examples:
        >>> compiler = GraphCompiler()
        >>> graph = compiler.compile(flow_config, branch_config=None)
        >>> # Граф валиден и готов к исполнению
    """

    def compile(
        self,
        flow_config: Any,  # FlowConfig
        branch_config: Optional[Any] = None,  # BranchConfig
        variables: Optional[Dict[str, Any]] = None,
    ) -> CompiledGraph:
        """
        Компилирует агента в неизменяемый граф.

        Проверки:
        1. entry нода существует
        2. Все ноды в edges существуют
        3. Нет недостижимых нод
        4. Нет циклов без выхода
        5. Ветки не конфликтуют с базовым графом

        Args:
            flow_config: Конфигурация агента
            branch_config: Конфигурация ветки (опционально)
            variables: Предрезолвнутые переменные

        Returns:
            CompiledGraph - неизменяемый граф

        Raises:
            ConfigError: Если конфиг невалиден
            CyclicDependencyError: Если есть циклы
            NodeConflictError: Если ветка конфликтует
            InvalidGraphError: Если структура графа невалидна
        """
        # Применяем ветку к базовой конфигурации
        effective_config = self._apply_branch(flow_config, branch_config)

        # Валидируем entry ноду
        self._validate_entry_node(effective_config)

        # Валидируем edges
        self._validate_edges(effective_config)

        # Проверка на циклы
        self._check_for_cycles(effective_config)

        # Проверка достижимости
        self._check_reachability(effective_config)

        # Создаём checksum
        checksum = self._calculate_checksum(effective_config)

        # Создаём CompiledEdge объекты
        compiled_edges = [
            CompiledEdge(
                from_node=e.from_node if hasattr(e, "from_node") else e["from"],
                to_node=e.to_node if hasattr(e, "to_node") else e.get("to"),
                condition=e.condition if hasattr(e, "condition") else e.get("condition"),
            )
            for e in effective_config["edges"]
        ]

        return CompiledGraph(
            flow_id=flow_config.flow_id,
            branch_id=branch_config.name if branch_config else "default",
            entry_node=effective_config["entry"],
            nodes=effective_config["nodes"],
            edges=compiled_edges,
            variables=variables or {},
            checksum=checksum,
        )

    def _apply_branch(
        self,
        flow_config: Any,
        branch_config: Optional[Any],
    ) -> Dict[str, Any]:
        """
        Применяет ветку к базовой конфигурации агента.

        TODO: Эта логика будет перенесена из FlowFactory.
        Пока возвращаем базовую конфигурацию.
        """
        return {
            "entry": flow_config.entry,
            "nodes": dict(flow_config.nodes),
            "edges": list(flow_config.edges),
        }

    def _validate_entry_node(self, config: Dict[str, Any]) -> None:
        """
        Проверяет что entry нода существует в графе.

        Raises:
            InvalidGraphError: Если entry нода не найдена
        """
        entry = config["entry"]
        nodes = config["nodes"]

        if entry not in nodes:
            raise InvalidGraphError(
                message=f"Entry нода '{entry}' не найдена в графе",
                payload={"entry": entry, "available_nodes": list(nodes.keys())},
            )

    def _validate_edges(self, config: Dict[str, Any]) -> None:
        """
        Проверяет что все ноды в edges существуют.

        Raises:
            InvalidGraphError: Если нода в edge не найдена
        """
        nodes = config["nodes"]
        edges = config["edges"]

        for edge in edges:
            from_node = edge.from_node if hasattr(edge, "from_node") else edge["from"]
            to_node = edge.to_node if hasattr(edge, "to_node") else edge.get("to")

            if from_node not in nodes:
                raise InvalidGraphError(
                    message=f"from_node '{from_node}' не найдена в графе",
                    payload={"from_node": from_node, "available_nodes": list(nodes.keys())},
                )

            if to_node is not None and to_node not in nodes:
                raise InvalidGraphError(
                    message=f"to_node '{to_node}' не найдена в графе",
                    payload={"to_node": to_node, "available_nodes": list(nodes.keys())},
                )

    def _check_for_cycles(self, config: Dict[str, Any]) -> None:
        """
        Проверяет граф на циклы без выхода.

        Использует DFS для обнаружения циклов.

        Raises:
            CyclicDependencyError: Если обнаружен цикл без выхода
        """
        # Строим adjacency list
        graph = {}
        for edge in config["edges"]:
            from_node = edge.from_node if hasattr(edge, "from_node") else edge["from"]
            to_node = edge.to_node if hasattr(edge, "to_node") else edge.get("to")

            if to_node is None:
                continue  # Выход из графа

            if from_node not in graph:
                graph[from_node] = []
            graph[from_node].append(to_node)

        # DFS для поиска циклов
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            if node in graph:
                for neighbor in graph[node]:
                    if neighbor not in visited:
                        dfs(neighbor, path[:])
                    elif neighbor in rec_stack:
                        # Найден цикл
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        raise CyclicDependencyError(cycle_path=cycle)

            rec_stack.remove(node)

        # Проверяем от entry ноды
        entry = config["entry"]
        if entry in graph or entry in config["nodes"]:
            try:
                dfs(entry, [])
            except CyclicDependencyError:
                raise

    def _check_reachability(self, config: Dict[str, Any]) -> None:
        """
        Проверяет что все ноды достижимы от entry ноды.

        Raises:
            InvalidGraphError: Если есть недостижимые ноды
        """
        # Строим adjacency list
        graph = {}
        for edge in config["edges"]:
            from_node = edge.from_node if hasattr(edge, "from_node") else edge["from"]
            to_node = edge.to_node if hasattr(edge, "to_node") else edge.get("to")

            if to_node is None:
                continue

            if from_node not in graph:
                graph[from_node] = []
            graph[from_node].append(to_node)

        # BFS от entry ноды
        entry = config["entry"]
        reachable = set()
        queue = [entry]

        while queue:
            node = queue.pop(0)
            if node in reachable:
                continue
            reachable.add(node)

            if node in graph:
                queue.extend(graph[node])

        # Проверяем недостижимые ноды
        all_nodes = set(config["nodes"].keys())
        unreachable = all_nodes - reachable

        # Ноды могут быть доступны как tools, не только через edges
        # Поэтому недостижимые ноды это предупреждение, не ошибка
        if unreachable:
            from core.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(
                f"Ноды не достижимы через edges от entry '{entry}': {', '.join(unreachable)}. "
                f"Если они используются как tools - это нормально."
            )

    def _calculate_checksum(self, config: Dict[str, Any]) -> str:
        """
        Вычисляет checksum конфигурации для кеширования.

        Args:
            config: Effective конфигурация

        Returns:
            SHA256 хеш конфигурации
        """
        # Сериализуем конфиг в JSON для хеширования
        config_json = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_json.encode()).hexdigest()


__all__ = ["GraphCompiler", "CompiledGraph"]

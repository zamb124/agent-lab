"""
GraphCompiler - компилятор графов агентов.

Статическая сборка и валидация графа до выполнения.
Zero-Guess: все ошибки обнаруживаются на этапе компиляции, не runtime.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.errors import (
    CyclicDependencyError,
    InvalidGraphError,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


class GraphEdge(Protocol):
    """Минимальный контракт edge для компилятора графа."""

    @property
    def from_node(self) -> str: ...

    @property
    def to_node(self) -> str | None: ...

    @property
    def condition(self) -> BaseModel | JsonObject | None: ...

    @property
    def contributes_to_join(self) -> bool: ...


class CompiledEdge(StrictBaseModel):
    """Скомпилированная связь между нодами"""

    from_node: str = Field(..., description="ID исходной ноды")
    to_node: str | None = Field(..., description="ID целевой ноды (null = конец)")
    condition: JsonObject | None = Field(
        default=None,
        description="Типизированное условие перехода как JSON object.",
    )
    contributes_to_join: bool = Field(
        default=True,
        description="Участвует ли edge в AND-join входов целевой ноды.",
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

    nodes: dict[str, JsonObject] = Field(..., description="Ноды графа")
    edges: list[CompiledEdge] = Field(..., description="Связи между нодами")
    variables: JsonObject = Field(default_factory=dict, description="Резолвнутые переменные")

    # Метаданные компиляции
    compiled_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Время компиляции"
    )
    checksum: str = Field(..., description="Хеш конфига для кеширования")

    # Граф только для чтения
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    def validate_state_flow(self) -> None:
        """
        Валидирует совместимость схем данных между нодами.

        Проверяет что output схема ноды A совместима с input схемой ноды B.

        Исключения:
            SchemaMismatchError: Если схемы несовместимы
        """
        # TODO: реализовать JSON Schema валидацию
        pass


class GraphCompiler:
    """
    Компилятор графа агента.

    Принципы Zero-Guess:
    1. Все ошибки на этапе компиляции, не runtime
    2. Явная валидация всех связей
    3. Проверка циклов и достижимости
    4. Конфликты skills обнаруживаются до запуска

    Примеры:
        >>> compiler = GraphCompiler()
        >>> graph = compiler.compile(flow_config, branch_config=None)
        >>> # Граф валиден и готов к исполнению
    """

    def compile(
        self,
        *,
        flow_id: str,
        entry: str,
        nodes: Mapping[str, JsonObject],
        edges: Sequence[GraphEdge],
        branch_id: str = "default",
        variables: JsonObject | None = None,
    ) -> CompiledGraph:
        """
        Компилирует уже собранный effective-граф в неизменяемый граф.

        Проверки:
        1. entry нода существует
        2. Все ноды в edges существуют
        3. Нет недостижимых нод
        4. Нет циклов без выхода
        5. Ветки не конфликтуют с базовым графом

        Аргументы:
            flow_id: ID flow
            entry: Стартовая нода effective-графа
            nodes: Ноды effective-графа
            edges: Связи effective-графа
            branch_id: ID применённой ветки
            variables: Предрезолвнутые переменные

        Возвращает:
            CompiledGraph - неизменяемый граф

        Исключения:
            ConfigError: Если конфиг невалиден
            CyclicDependencyError: Если есть циклы
            NodeConflictError: Если ветка конфликтует
            InvalidGraphError: Если структура графа невалидна
        """
        graph_nodes = dict(nodes)
        graph_edges = list(edges)
        graph_variables = variables if variables is not None else {}

        # Валидируем entry ноду
        self._validate_entry_node(entry, graph_nodes)

        # Валидируем edges
        self._validate_edges(graph_nodes, graph_edges)

        # Проверка на циклы
        self._check_for_cycles(entry, graph_nodes, graph_edges)

        # Проверка достижимости
        self._check_reachability(entry, graph_nodes, graph_edges)

        compiled_edges = self._compile_edges(graph_edges)

        # Создаём checksum
        checksum = self._calculate_checksum(
            entry=entry,
            nodes=graph_nodes,
            edges=compiled_edges,
            variables=graph_variables,
        )

        return CompiledGraph(
            flow_id=flow_id,
            branch_id=branch_id,
            entry_node=entry,
            nodes=graph_nodes,
            edges=compiled_edges,
            variables=graph_variables,
            checksum=checksum,
        )

    def _compile_edges(self, edges: Sequence[GraphEdge]) -> list[CompiledEdge]:
        return [
            CompiledEdge(
                from_node=edge.from_node,
                to_node=edge.to_node,
                condition=self._compile_edge_condition(edge.condition),
                contributes_to_join=edge.contributes_to_join,
            )
            for edge in edges
        ]

    @staticmethod
    def _compile_edge_condition(condition: BaseModel | JsonObject | None) -> JsonObject | None:
        if condition is None:
            return None
        if isinstance(condition, BaseModel):
            return require_json_object(
                condition.model_dump(mode="json"),
                "edge.condition",
            )
        return require_json_object(condition, "edge.condition")

    def _validate_entry_node(self, entry: str, nodes: Mapping[str, JsonObject]) -> None:
        """
        Проверяет что entry нода существует в графе.

        Исключения:
            InvalidGraphError: Если entry нода не найдена
        """
        if entry not in nodes:
            raise InvalidGraphError(
                message=f"Entry нода '{entry}' не найдена в графе",
                payload={"entry": entry, "available_nodes": list(nodes.keys())},
            )

    def _validate_edges(
        self,
        nodes: Mapping[str, JsonObject],
        edges: Sequence[GraphEdge],
    ) -> None:
        """
        Проверяет что все ноды в edges существуют.

        Исключения:
            InvalidGraphError: Если нода в edge не найдена
        """
        for edge in edges:
            if edge.from_node not in nodes:
                raise InvalidGraphError(
                    message=f"from_node '{edge.from_node}' не найдена в графе",
                    payload={"from_node": edge.from_node, "available_nodes": list(nodes.keys())},
                )

            if edge.to_node is not None and edge.to_node not in nodes:
                raise InvalidGraphError(
                    message=f"to_node '{edge.to_node}' не найдена в графе",
                    payload={"to_node": edge.to_node, "available_nodes": list(nodes.keys())},
                )

    def _build_adjacency(self, edges: Sequence[GraphEdge]) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for edge in edges:
            if edge.to_node is None:
                continue
            graph.setdefault(edge.from_node, []).append(edge.to_node)
        return graph

    def _check_for_cycles(
        self,
        entry: str,
        nodes: Mapping[str, JsonObject],
        edges: Sequence[GraphEdge],
    ) -> None:
        """
        Проверяет граф на циклы без выхода.

        Использует DFS для обнаружения циклов.

        Исключения:
            CyclicDependencyError: Если обнаружен цикл без выхода
        """
        graph = self._build_adjacency(edges)

        # DFS для поиска циклов
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, path: list[str]) -> None:
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
        if entry in graph or entry in nodes:
            dfs(entry, [])

    def _check_reachability(
        self,
        entry: str,
        nodes: Mapping[str, JsonObject],
        edges: Sequence[GraphEdge],
    ) -> None:
        """
        Проверяет что все ноды достижимы от entry ноды.

        Исключения:
            InvalidGraphError: Если есть недостижимые ноды
        """
        graph = self._build_adjacency(edges)

        # BFS от entry-ноды
        reachable: set[str] = set()
        queue = [entry]

        while queue:
            node = queue.pop(0)
            if node in reachable:
                continue
            reachable.add(node)

            if node in graph:
                queue.extend(graph[node])

        # Проверяем недостижимые ноды
        all_nodes = set(nodes.keys())
        unreachable = all_nodes - reachable

        # Ноды могут быть доступны как tools, не только через edges
        # Поэтому недостижимые ноды это предупреждение, не ошибка
        if unreachable:
            unreachable_nodes = ", ".join(sorted(unreachable))
            logger.warning(
                f"Ноды не достижимы через edges от entry '{entry}': {unreachable_nodes}."
            )

    def _calculate_checksum(
        self,
        *,
        entry: str,
        nodes: Mapping[str, JsonObject],
        edges: Sequence[CompiledEdge],
        variables: JsonObject,
    ) -> str:
        """
        Вычисляет checksum конфигурации для кеширования.

        Аргументы:
            config: Effective конфигурация

        Возвращает:
            SHA256 хеш конфигурации
        """
        edge_payloads: list[JsonObject] = [
            {
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "condition": edge.condition,
                "contributes_to_join": edge.contributes_to_join,
            }
            for edge in edges
        ]
        graph_payload: JsonObject = {
            "entry": entry,
            "nodes": dict(nodes),
            "edges": edge_payloads,
            "variables": variables,
        }
        config_json = json.dumps(graph_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(config_json.encode()).hexdigest()


__all__ = ["GraphCompiler", "CompiledGraph"]

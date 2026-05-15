"""
Модели для Graph API.

Используются для построения и представления графов связей между entities.
"""

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """
    Узел в графе связей.

    Представляет entity с информацией о доступе и глубине в графе.
    """
    entity_id: str = Field(description="ID entity")
    entity_type: str = Field(description="Тип entity или 'hidden' если нет доступа")
    name: str = Field(description="Название entity или 'Hidden'")
    level: int = Field(description="Глубина от корневого узла (0 для root)")
    access: bool = Field(description="Есть ли полный доступ к entity")
    created_at: str | None = Field(
        default=None,
        description="Время создания entity (ISO8601)"
    )
    attributes: dict[str, Any] | None = Field(
        default=None,
        description="Атрибуты entity (только если access=True)"
    )


class GraphEdge(BaseModel):
    """
    Ребро в графе связей.

    Представляет relationship между двумя entities.
    """
    edge_id: str = Field(description="ID relationship")
    source_id: str = Field(description="ID источника")
    target_id: str = Field(description="ID цели")
    relationship_type: str = Field(description="Тип связи")
    weight: float = Field(description="Вес ребра")
    confidence: float = Field(description="Уверенность в корректности связи (модель / источник)")
    is_directed: bool = Field(description="Направленное ли ребро")
    attributes: dict[str, Any] | None = Field(
        default=None,
        description="Дополнительные атрибуты связи"
    )


class InfluenceGraphResponse(BaseModel):
    """
    Граф влияния от корневой entity.

    Содержит все узлы и ребра в пределах max_depth.
    """
    root_entity_id: str = Field(description="ID корневой entity")
    max_depth: int = Field(description="Максимальная глубина обхода")
    nodes: list[GraphNode] = Field(description="Узлы графа")
    edges: list[GraphEdge] = Field(description="Ребра графа")
    total_nodes: int = Field(description="Общее количество узлов")
    filtered_count: int = Field(description="Количество скрытых узлов из-за прав")


class ShortestPathResponse(BaseModel):
    """
    Кратчайший путь между двумя entities.

    Использует weighted алгоритм Dijkstra.
    """
    from_entity_id: str = Field(description="Начальная entity")
    to_entity_id: str = Field(description="Конечная entity")
    path: list[str] = Field(description="Список entity_id в пути")
    edges: list[GraphEdge] = Field(description="Ребра вдоль пути")
    total_distance: float = Field(description="Сумма весов вдоль пути")
    exists: bool = Field(description="Существует ли путь")
    undirected_path: list[str] = Field(description="Путь без учета направления ребер")
    undirected_edges: list[GraphEdge] = Field(description="Ребра пути без учета направления")
    undirected_total_distance: float = Field(description="Сумма весов пути без учета направления")
    undirected_exists: bool = Field(description="Существует ли путь без учета направления")


class RelatedEntitiesResponse(BaseModel):
    """
    Прямо связанные entities (1 уровень).

    Разделяет по направлению: incoming, outgoing, undirected.
    """
    entity_id: str = Field(description="ID центральной entity")
    incoming: list[GraphNode] = Field(
        description="Entities которые ссылаются на текущую"
    )
    outgoing: list[GraphNode] = Field(
        description="Entities на которые ссылается текущая"
    )
    undirected: list[GraphNode] = Field(
        description="Симметричные связи (is_directed=False)"
    )


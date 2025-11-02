"""
Модуль для работы с checkpointer для LangGraph.
Обеспечивает сохранение состояния агентов между вызовами и инспекцию чекпоинтеров.
"""

import asyncio
import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings
from app.core.tracing.decorators import trace_span
from app.models.trace_models import SpanType

logger = logging.getLogger(__name__)

# Глобальный checkpointer
_checkpointer = None


class CheckpointerManager:
    """Менеджер checkpointer для агентов"""

    def __init__(self):
        self._checkpointer = None

    def get_checkpointer(self, serde=None):
        """Возвращает checkpointer для агентов"""
        if serde is not None:
            # Если serde задан, создаем новый checkpointer без кэширования
            return self._create_postgres_checkpointer(serde)

        # Для стандартного случая используем кэширование
        if self._checkpointer is None:
            self._checkpointer = self._create_postgres_checkpointer()

        return self._checkpointer

    def _create_postgres_checkpointer(self, serde=None):
        """Создает checkpointer для PostgreSQL"""

        class PostgresCheckpointer:
            def __init__(self, conn_string, serde=None):
                self.conn_string = conn_string
                self.serde = serde
                self._connection = None
                self._context_manager = None
                self._lock = asyncio.Lock()

            async def _get_connection(self):
                """Получает или создает переиспользуемое соединение"""
                async with self._lock:
                    # Проверяем что соединение существует и активно
                    if self._connection is not None:
                        # Проверяем статус соединения
                        try:
                            if hasattr(self._connection, 'conn') and hasattr(self._connection.conn, 'closed'):
                                if self._connection.conn.closed:
                                    logger.debug("⚠️ Соединение закрыто, пересоздаем...")
                                    self._connection = None
                                    self._context_manager = None
                        except:
                            # Если проверка не удалась, пересоздадим соединение
                            self._connection = None
                            self._context_manager = None

                    if self._connection is None:
                        if self.serde:
                            self._context_manager = AsyncPostgresSaver.from_conn_string(
                                self.conn_string, serde=self.serde
                            )
                        else:
                            self._context_manager = AsyncPostgresSaver.from_conn_string(
                                self.conn_string
                            )

                        self._connection = await self._context_manager.__aenter__()
                        logger.debug("✅ Создано переиспользуемое соединение с PostgreSQL checkpointer")

                    return self._connection

            async def setup(self):
                """Создает таблицы checkpointer'а в БД"""
                cp = await self._get_connection()
                await cp.setup()

            async def aget_tuple(self, config):
                cp = await self._get_connection()
                logger.info(f"🔍 checkpointer.aget_tuple: config={config}")
                result = await cp.aget_tuple(config)
                logger.info(f"🔍 checkpointer.aget_tuple: result={result}")
                return result

            async def aput(self, config, checkpoint, metadata, new_versions):
                cp = await self._get_connection()
                logger.info(f"🔍 checkpointer.aput: config={config}, checkpoint keys={list(checkpoint.keys()) if isinstance(checkpoint, dict) else 'not dict'}")
                result = await cp.aput(config, checkpoint, metadata, new_versions)
                logger.info(f"🔍 checkpointer.aput: result={result}")
                return result

            async def alist(self, config, *, limit=None, before=None):
                cp = await self._get_connection()
                return cp.alist(config, limit=limit, before=before)

            async def adelete_thread(self, thread_id):
                cp = await self._get_connection()
                if hasattr(cp, "adelete_thread"):
                    return await cp.adelete_thread(thread_id)

            def get_next_version(self, current, channel):
                """Синхронный метод для получения следующей версии"""
                if current is None:
                    return "00000000000000000000000000000001"
                return f"{int(current.split('.')[0]) + 1:032d}"

            async def aput_writes(self, config, writes, task_id):
                """Сохранение writes"""
                cp = await self._get_connection()
                if hasattr(cp, "aput_writes"):
                    return await cp.aput_writes(config, writes, task_id)

            async def close(self):
                """Закрывает соединение"""
                async with self._lock:
                    if self._connection is not None and self._context_manager is not None:
                        try:
                            await self._context_manager.__aexit__(None, None, None)
                            logger.info("✅ PostgreSQL checkpointer connection закрыт")
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка при закрытии checkpointer connection: {e}")
                        finally:
                            self._connection = None
                            self._context_manager = None

            @property
            def config_specs(self):
                return []

        settings = get_settings()  # Используем синглтон
        return PostgresCheckpointer(settings.database.checkpointer_url, serde)


# Глобальный менеджер
_manager = CheckpointerManager()


@trace_span(
    name="checkpointer.init_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "init"}
)
async def init_checkpointer() -> None:
    """Инициализация checkpointer"""
    global _checkpointer

    try:
        logger.info("🔄 Инициализация checkpointer...")

        # Получаем checkpointer через менеджер
        checkpointer = _manager.get_checkpointer()

        if hasattr(checkpointer, "setup"):
            await checkpointer.setup()

        _checkpointer = checkpointer
        logger.info("✅ Checkpointer успешно инициализирован (PostgreSQL)")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации checkpointer: {e}")
        raise


@trace_span(
    name="checkpointer.get_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "get"}
)
async def get_checkpointer():
    """Получение checkpointer"""
    global _checkpointer

    if _checkpointer is None:
        await init_checkpointer()

    logger.info(f"🔍 get_checkpointer: возвращаем checkpointer {type(_checkpointer)}")
    return _checkpointer


@trace_span(
    name="checkpointer.update_checkpointer_with_store_changes",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "update_store"}
)
async def update_checkpointer_with_store_changes(checkpointer, run_config: dict, store_data: dict):
    """
    Обновляет checkpointer с изменениями store, сделанными в tools.
    Это лаконичная архитектура для персистентности state.
    """
    # Получаем текущий checkpoint
    checkpoint_tuple = await checkpointer.aget_tuple(run_config)
    if checkpoint_tuple and checkpoint_tuple.checkpoint:
        # Обновляем channel_values с новыми данными store
        updated_channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        updated_channel_values["store"] = store_data

        # Создаем новый checkpoint с обновленными данными
        updated_checkpoint = checkpoint_tuple.checkpoint.copy()
        updated_checkpoint["channel_values"] = updated_channel_values

        # Обновляем channel_versions для store
        channel_versions = checkpoint_tuple.checkpoint.get("channel_versions", {})
        if "store" in channel_versions:
            # Инкрементируем версию store
            current_version = channel_versions["store"]
            if isinstance(current_version, str):
                try:
                    new_version = f"{int(current_version.split('.')[0]) + 1:032d}"
                except:
                    new_version = "00000000000000000000000000000002"
            else:
                new_version = "00000000000000000000000000000002"
            channel_versions["store"] = new_version
        else:
            channel_versions["store"] = "00000000000000000000000000000001"

        # Сохраняем обновленный checkpoint
        # Используем checkpoint_tuple.config для сохранения (содержит checkpoint_ns)
        await checkpointer.aput(
            checkpoint_tuple.config,
            updated_checkpoint,
            checkpoint_tuple.metadata,
            channel_versions
        )

        logger.info(f"✅ Store обновлен в checkpointer: {list(store_data.keys())}")
    else:
        logger.warning("⚠️ Не удалось получить checkpoint для обновления store")


@trace_span(
    name="checkpointer.close_checkpointer",
    span_type=SpanType.OTHER,
    metadata={"component": "checkpointer", "operation": "close_global"}
)
async def close_checkpointer() -> None:
    """Закрытие checkpointer"""
    global _checkpointer

    if _checkpointer is not None:
        try:
            if hasattr(_checkpointer, 'close'):
                await _checkpointer.close()
            logger.info("✅ Checkpointer закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия checkpointer: {e}")
        finally:
            _checkpointer = None


class CheckpointInspector:
    """Инспектор для анализа и визуализации чекпоинтеров LangGraph"""

    def __init__(self, checkpointer_manager: Optional[CheckpointerManager] = None):
        self.manager = checkpointer_manager or CheckpointerManager()

    async def get_checkpoint_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Получает полную историю чекпоинтеров для thread_id.

        Args:
            thread_id: ID потока выполнения

        Returns:
            Список чекпоинтеров с метаданными
        """
        checkpointer = self.manager.get_checkpointer()

        config = {"configurable": {"thread_id": thread_id}}
        checkpoints = []

        checkpoints_list = await checkpointer.alist(config)
        raw_checkpoints = []
        async for checkpoint_tuple in checkpoints_list:
            raw_checkpoints.append(checkpoint_tuple)

        raw_checkpoints.sort(key=lambda x: x.metadata.get("step", 0))

        previous_tool_calls = set()
        for checkpoint_tuple in raw_checkpoints:
            tool_calls = self._extract_tool_calls_from_checkpoint(checkpoint_tuple, previous_tool_calls)
            store_vars = self._extract_store_variables(checkpoint_tuple)

            metadata = self._sanitize_for_json(checkpoint_tuple.metadata)
            source = metadata.get("source", "")
            
            node_name = source
            if ":" in source:
                parts = source.split(":", 1)
                if len(parts) > 1:
                    node_name = parts[1]
            
            checkpoint_data = {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_tuple.config.get("configurable", {}).get("checkpoint_id", ""),
                "parent_checkpoint_id": checkpoint_tuple.parent_config.get("configurable", {}).get("checkpoint_id", "") if checkpoint_tuple.parent_config else "",
                "timestamp": checkpoint_tuple.checkpoint.get("ts", ""),
                "step": metadata.get("step", 0),
                "source": source,
                "node_name": node_name,
                "next_nodes": metadata.get("next", []),
                "task_id": metadata.get("task_id"),
                "tool_calls": tool_calls,
                "store_variables": store_vars,
                "metadata": metadata,
                "values": self._sanitize_for_json(checkpoint_tuple.checkpoint.get("channel_values", {}))
            }
            checkpoints.append(checkpoint_data)

        checkpoints.sort(key=lambda x: x["timestamp"], reverse=True)
        return checkpoints

    async def get_checkpoint_connections(self, thread_id: str) -> Dict[str, Any]:
        """
        Получает все связи между чекпоинтерами для thread_id.

        Args:
            thread_id: ID потока выполнения

        Returns:
            Словарь с информацией о связях чекпоинтеров
        """
        checkpoints = await self.get_checkpoint_history(thread_id)

        if not checkpoints:
            return {"thread_id": thread_id, "connections": [], "summary": {"total_checkpoints": 0, "total_connections": 0, "transition_stats": {}}}

        connections = []
        checkpoint_map = {cp["checkpoint_id"]: cp for cp in checkpoints}

        for checkpoint in checkpoints:
            parent_id = checkpoint["parent_checkpoint_id"]
            if parent_id and parent_id in checkpoint_map:
                parent = checkpoint_map[parent_id]
                connection = {
                    "from": {
                        "checkpoint_id": parent["checkpoint_id"],
                        "step": parent["step"],
                        "source": parent["source"],
                        "timestamp": parent["timestamp"],
                        "tool_calls": parent.get("tool_calls", [])
                    },
                    "to": {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "step": checkpoint["step"],
                        "source": checkpoint["source"],
                        "timestamp": checkpoint["timestamp"],
                        "tool_calls": checkpoint.get("tool_calls", [])
                    },
                    "transition_type": checkpoint["source"]
                }
                connections.append(connection)

        transition_stats = {}
        for conn in connections:
            trans_type = conn["transition_type"]
            transition_stats[trans_type] = transition_stats.get(trans_type, 0) + 1

        return {
            "thread_id": thread_id,
            "connections": connections,
            "summary": {
                "total_checkpoints": len(checkpoints),
                "total_connections": len(connections),
                "transition_stats": transition_stats,
                "first_checkpoint": checkpoints[-1] if checkpoints else None,
                "last_checkpoint": checkpoints[0] if checkpoints else None
            }
        }

    async def get_timeline(self, thread_id: str, include_values: bool = False) -> Dict[str, Any]:
        """
        Получает timeline представление выполнения агента.

        Args:
            thread_id: ID потока
            include_values: Включать ли детальные значения сообщений

        Returns:
            Словарь с timeline данными включая структуру дерева
        """
        checkpoints = await self.get_checkpoint_history(thread_id)

        if not checkpoints:
            return {
                "thread_id": thread_id,
                "timeline": [],
                "tree": [],
                "summary": {"total_steps": 0}
            }

        timeline_entries = []
        for checkpoint in sorted(checkpoints, key=lambda x: x["timestamp"], reverse=True):
            entry = {
                "step": checkpoint["step"],
                "timestamp": checkpoint["timestamp"],
                "source": checkpoint["source"],
                "node_name": checkpoint.get("node_name", checkpoint.get("source", "")),
                "checkpoint_id": checkpoint["checkpoint_id"],
                "parent_checkpoint_id": checkpoint.get("parent_checkpoint_id"),
                "tool_calls": checkpoint.get("tool_calls", []),
                "store_variables": checkpoint.get("store_variables", {}),
                "next_nodes": checkpoint.get("next_nodes", []),
                "task_id": checkpoint.get("task_id")
            }

            if include_values:
                entry["messages"] = checkpoint.get("values", {}).get("messages", [])

            timeline_entries.append(entry)

        all_tool_calls = []
        for entry in timeline_entries:
            all_tool_calls.extend(entry["tool_calls"])

        tool_stats = {}
        for tool_call in all_tool_calls:
            name = tool_call.get("name", "unknown")
            tool_stats[name] = tool_stats.get(name, 0) + 1

        summary = {
            "total_steps": len(timeline_entries),
            "transition_stats": {},
            "tool_stats": tool_stats
        }

        for entry in timeline_entries:
            source = entry["source"]
            summary["transition_stats"][source] = summary["transition_stats"].get(source, 0) + 1

        tree = self._build_checkpoint_tree(checkpoints)

        return {
            "thread_id": thread_id,
            "timeline": timeline_entries,
            "tree": tree,
            "summary": summary
        }

    def _build_checkpoint_tree(self, checkpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Строит дерево чекпоинтеров по связям parent-child"""
        if not checkpoints:
            return []

        checkpoint_map = {cp["checkpoint_id"]: cp for cp in checkpoints}
        root_checkpoints = []
        children_map = {}

        for checkpoint in checkpoints:
            parent_id = checkpoint.get("parent_checkpoint_id")
            if not parent_id or parent_id not in checkpoint_map:
                root_checkpoints.append(checkpoint)
            else:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(checkpoint)

        def build_node(cp):
            node = {
                "checkpoint_id": cp["checkpoint_id"],
                "step": cp["step"],
                "timestamp": cp["timestamp"],
                "source": cp["source"],
                "node_name": cp.get("node_name", cp.get("source", "")),
                "tool_calls": cp.get("tool_calls", []),
                "store_variables": cp.get("store_variables", {}),
                "next_nodes": cp.get("next_nodes", []),
                "task_id": cp.get("task_id"),
                "values": cp.get("values", {}),
                "metadata": cp.get("metadata", {}),
                "children": []
            }

            children = children_map.get(cp["checkpoint_id"], [])
            for child in sorted(children, key=lambda x: x.get("step", 0)):
                node["children"].append(build_node(child))

            return node

        tree = []
        for root in sorted(root_checkpoints, key=lambda x: x.get("step", 0)):
            tree.append(build_node(root))

        return tree

    def _sanitize_for_json(self, value: Any, _depth: int = 0) -> Any:
        if _depth > 8:
            return str(value)

        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.hex()

        if isinstance(value, dict):
            return {
                str(self._sanitize_for_json(k, _depth + 1)):
                    self._sanitize_for_json(v, _depth + 1)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [self._sanitize_for_json(item, _depth + 1) for item in value]

        if is_dataclass(value):
            return self._sanitize_for_json(asdict(value), _depth + 1)

        for attr in ("model_dump", "dict", "to_dict"):
            if hasattr(value, attr) and callable(getattr(value, attr)):
                try:
                    result = getattr(value, attr)()
                    return self._sanitize_for_json(result, _depth + 1)
                except Exception:
                    continue

        if hasattr(value, "__dict__"):
            try:
                return self._sanitize_for_json(value.__dict__, _depth + 1)
            except Exception:
                pass

        return str(value)

    def convert_tree_to_network_data(self, tree: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Преобразует дерево чекпоинтеров в данные для Vis.js Network"""
        nodes = []
        edges = []
        node_id = 0

        def process_node(node, parent_id=None):
            nonlocal node_id
            current_id = node_id
            node_id += 1
            
            node_name = node.get("node_name", node.get("source", "unknown"))
            step = node.get("step", 0)
            timestamp = node.get("timestamp", "")
            
            color = self._get_node_color(node.get("source", ""))
            
            nodes.append({
                "id": current_id,
                "label": f"Шаг {step}\n{node_name}",
                "title": f"{node_name} ({timestamp})" if timestamp else node_name,
                "color": color,
                "font": {"size": 12}
            })

            if parent_id is not None:
                edges.append({
                    "from": parent_id,
                    "to": current_id,
                    "arrows": "to"
                })

            for child in node.get("children", []):
                process_node(child, current_id)

        for root_node in tree:
            process_node(root_node)
        
        return {"nodes": nodes, "edges": edges}

    def convert_tree_to_timeline_items(self, tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Преобразует дерево чекпоинтеров в элементы для Vis.js Timeline"""
        items = []
        item_id = 0

        def process_node(node):
            nonlocal item_id
            node_name = node.get("node_name", node.get("source", "unknown"))
            step = node.get("step", 0)
            timestamp = node.get("timestamp", "")
            
            if timestamp:
                try:
                    start_time = timestamp if isinstance(timestamp, str) else str(timestamp)
                    items.append({
                        "id": item_id,
                        "content": f"Шаг {step}: {node_name}",
                        "start": start_time,
                        "title": f"{node_name} ({start_time})",
                        "group": 1
                    })
                    item_id += 1
                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка обработки timestamp для шага {step}: {e}")

            for child in node.get("children", []):
                process_node(child)

        for root_node in tree:
            process_node(root_node)
        
        return items

    def _get_node_color(self, source: str) -> str:
        """Возвращает цвет для узла по типу источника"""
        colors = {
            "input": "#28a745",
            "loop": "#007bff", 
            "update": "#ffc107",
            "interrupt": "#dc3545"
        }
        return colors.get(source, "#6c757d")

    def _extract_tool_calls_from_checkpoint(self, checkpoint_tuple, previous_tool_calls: set) -> List[Dict[str, Any]]:
        """Извлекает новые вызовы инструментов из чекпоинтера"""
        tool_calls = []

        channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])

        if not isinstance(messages, list):
            return tool_calls

        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_call_info = {
                        "name": str(tool_call.get("name", "unknown")),
                        "arguments": self._sanitize_for_json(tool_call.get("arguments", {})),
                        "id": str(tool_call.get("id", "")),
                        "type": str(tool_call.get("type", "function"))
                    }

                    tool_call_key = f"{tool_call_info['name']}_{str(tool_call_info['arguments'])}_{tool_call_info['id']}"

                    if tool_call_key not in previous_tool_calls:
                        tool_calls.append(tool_call_info)
                        previous_tool_calls.add(tool_call_key)

        return tool_calls

    def _extract_store_variables(self, checkpoint_tuple) -> Dict[str, Any]:
        """Извлекает переменные store из чекпоинтера"""
        try:
            channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            store = channel_values.get("store", {})

            if not isinstance(store, dict):
                return {}

            formatted_store = {}
            for key, value in store.items():
                if value is None:
                    formatted_store[key] = None
                elif isinstance(value, (str, int, float, bool)):
                    formatted_store[key] = value
                elif isinstance(value, list):
                    if len(value) == 0:
                        formatted_store[key] = "[]"
                    else:
                        formatted_store[key] = f"list({len(value)})"
                elif isinstance(value, dict):
                    if len(value) == 0:
                        formatted_store[key] = "{}"
                    else:
                        formatted_store[key] = f"dict({len(value)} keys)"
                else:
                    formatted_store[key] = str(value)[:100] if len(str(value)) > 100 else str(value)

            return formatted_store
        except Exception as e:
            logger.warning(f"Ошибка извлечения store из чекпоинтера: {e}")
            return {}

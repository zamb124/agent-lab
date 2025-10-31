"""
Инспектор чекпоинтеров LangGraph для визуализации и анализа связей.

Предоставляет инструменты для:
1. Получения визуального отображения чекпоинтеров
2. Получения всех связей чекпоинтеров по thread_id

Использование:
    python checkpoint_inspector.py --thread-id <thread_id> --format mermaid
    python checkpoint_inspector.py --list-threads
"""

import asyncio
import logging
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime
import os
import sys

# Добавляем путь к проекту для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.checkpointer import CheckpointerManager

logger = logging.getLogger(__name__)


class CheckpointInspector:
    """Инспектор для анализа чекпоинтеров LangGraph"""

    def __init__(self):
        self.manager = CheckpointerManager()

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

        try:
            # Получаем все чекпоинтеры для потока
            checkpoints_list = await checkpointer.alist(config)
            raw_checkpoints = []
            async for checkpoint_tuple in checkpoints_list:
                raw_checkpoints.append(checkpoint_tuple)

            # Сортируем по шагу (от старых к новым)
            raw_checkpoints.sort(key=lambda x: x.metadata.get("step", 0))

            # Извлекаем tool_calls для каждого чекпоинтера
            previous_tool_calls = set()
            for i, checkpoint_tuple in enumerate(raw_checkpoints):
                # Извлекаем tool_calls из чекпоинтера
                tool_calls = self._extract_tool_calls_from_checkpoint(checkpoint_tuple, previous_tool_calls)

                # Извлекаем переменные store
                store_vars = self._extract_store_variables(checkpoint_tuple)

                checkpoint_data = {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_tuple.config.get("configurable", {}).get("checkpoint_id", ""),
                    "parent_checkpoint_id": checkpoint_tuple.parent_config.get("configurable", {}).get("checkpoint_id", "") if checkpoint_tuple.parent_config else "",
                    "timestamp": checkpoint_tuple.checkpoint.get("ts", ""),
                    "step": checkpoint_tuple.metadata.get("step", 0),
                    "source": checkpoint_tuple.metadata.get("source", ""),
                    "next_nodes": checkpoint_tuple.metadata.get("next", []),
                    "tool_calls": tool_calls,  # Только новые tool_calls
                    "store_variables": store_vars,  # Переменные store
                    "values": checkpoint_tuple.checkpoint.get("channel_values", {}),
                    "metadata": checkpoint_tuple.metadata
                }
                checkpoints.append(checkpoint_data)

            # Сортируем по timestamp (сначала самые новые)
            checkpoints.sort(key=lambda x: x["timestamp"], reverse=True)

        except Exception as e:
            logger.error(f"Ошибка получения чекпоинтеров для thread_id {thread_id}: {e}")
            return []

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

        # Строим граф связей
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

        # Анализируем типы переходов
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

    def generate_mermaid_graph(self, connections_data: Dict[str, Any], include_values: bool = False) -> str:
        """
        Генерирует Mermaid диаграмму связей чекпоинтеров.

        Args:
            connections_data: Данные о связях чекпоинтеров
            include_values: Включать ли значения состояния в диаграмму

        Returns:
            Mermaid код диаграммы
        """
        connections = connections_data["connections"]

        if not connections:
            return "graph TD\n    A[Нет чекпоинтеров]"

        mermaid_lines = ["graph TD"]

        # Добавляем ноды
        added_nodes = set()
        for conn in connections:
            from_id = conn["from"]["checkpoint_id"][-8:]  # последние 8 символов
            to_id = conn["to"]["checkpoint_id"][-8:]

            if from_id not in added_nodes:
                label = f"Шаг {conn['from']['step']}<br/>{conn['from']['source']}"
                if include_values and conn["from"].get("values"):
                    # Добавляем ключевые значения (первые 50 символов)
                    values_str = str(conn["from"]["values"])[:50] + "..."
                    label += f"<br/><small>{values_str}</small>"
                mermaid_lines.append(f'    {from_id}["{label}"]')
                added_nodes.add(from_id)

            if to_id not in added_nodes:
                label = f"Шаг {conn['to']['step']}<br/>{conn['to']['source']}"
                if include_values and conn["to"].get("values"):
                    values_str = str(conn["to"]["values"])[:50] + "..."
                    label += f"<br/><small>{values_str}</small>"
                mermaid_lines.append(f'    {to_id}["{label}"]')
                added_nodes.add(to_id)

        # Добавляем ребра
        for conn in connections:
            from_id = conn["from"]["checkpoint_id"][-8:]
            to_id = conn["to"]["checkpoint_id"][-8:]
            transition = conn["transition_type"]
            mermaid_lines.append(f'    {from_id} -->|"{transition}"| {to_id}')

        return "\n".join(mermaid_lines)

    async def get_visualization(self, thread_id: str, format: str = "mermaid", include_values: bool = False) -> str:
        """
        Получает визуальное представление чекпоинтеров.

        Args:
            thread_id: ID потока выполнения
            format: Формат вывода ("mermaid", "json", "text")
            include_values: Включать ли значения состояния

        Returns:
            Визуальное представление чекпоинтеров
        """
        connections_data = await self.get_checkpoint_connections(thread_id)

        if format == "mermaid":
            return self.generate_mermaid_graph(connections_data, include_values)
        elif format == "json":
            import json
            return json.dumps(connections_data, indent=2, ensure_ascii=False, default=str)
        elif format == "text":
            return self.generate_text_representation(connections_data)
        elif format == "timeline":
            return self.generate_timeline_representation(thread_id, connections_data, include_values)
        elif format == "timeline-mermaid":
            return self.generate_timeline_mermaid(thread_id, connections_data, include_values)
        else:
            raise ValueError(f"Неподдерживаемый формат: {format}")

    def generate_text_representation(self, connections_data: Dict[str, Any]) -> str:
        """
        Генерирует текстовое представление связей чекпоинтеров.

        Args:
            connections_data: Данные о связях чекпоинтеров

        Returns:
            Текстовое представление
        """
        lines = []
        lines.append(f"=== ЧЕКПОИНТЕРЫ ПОТОКА {connections_data['thread_id']} ===")
        lines.append("")

        summary = connections_data["summary"]
        lines.append(f"Всего чекпоинтеров: {summary['total_checkpoints']}")
        lines.append(f"Всего связей: {summary['total_connections']}")
        lines.append("")

        if summary["transition_stats"]:
            lines.append("Статистика переходов:")
            for trans_type, count in summary["transition_stats"].items():
                lines.append(f"  {trans_type}: {count}")
            lines.append("")

        lines.append("Цепочка чекпоинтеров:")
        connections = connections_data["connections"]

        if not connections:
            lines.append("  Нет связей между чекпоинтерами")
        else:
            for i, conn in enumerate(connections):
                from_cp = conn["from"]
                to_cp = conn["to"]

                lines.append(f"  {i+1}. {from_cp['checkpoint_id'][-8:]} (шаг {from_cp['step']})")
                lines.append(f"     → {to_cp['checkpoint_id'][-8:]} (шаг {to_cp['step']}) [{conn['transition_type']}]")
                lines.append(f"     Время: {from_cp['timestamp']} → {to_cp['timestamp']}")

                # Добавляем информацию о вызовах инструментов
                tool_calls = from_cp.get("tool_calls", [])
                if tool_calls:
                    formatted_tools = self._format_tool_calls_for_display(tool_calls)
                    lines.append(f"     🔧 Инструменты: {formatted_tools}")

                # Добавляем информацию о переменных store
                store_vars = from_cp.get("store_variables", {})
                if store_vars:
                    store_items = []
                    for key, value in store_vars.items():
                        store_items.append(f"{key}={value}")
                    lines.append(f"     📦 Store: {', '.join(store_items)}")

                lines.append("")

        return "\n".join(lines)

    async def get_thread_list(self, limit: int = 50) -> List[str]:
        """
        Получает список всех доступных thread_id.

        Args:
            limit: Максимальное количество thread_id для возврата

        Returns:
            Список thread_id
        """
        checkpointer = self.manager.get_checkpointer()
        thread_ids = []

        try:
            # alist возвращает корутину, нужно await
            checkpoints_list = await checkpointer.alist({})
            async for checkpoint_tuple in checkpoints_list:
                thread_id = checkpoint_tuple.config.get("configurable", {}).get("thread_id")
                if thread_id and thread_id not in thread_ids:
                    thread_ids.append(thread_id)
                    if len(thread_ids) >= limit:
                        break
        except Exception as e:
            logger.error(f"Ошибка получения списка thread_id: {e}")

        return thread_ids

    def _extract_tool_calls_from_checkpoint(self, checkpoint_tuple, previous_tool_calls: set) -> List[Dict[str, Any]]:
        """
        Извлекает новые вызовы инструментов из чекпоинтера (не показывая уже виденные ранее).

        Args:
            checkpoint_tuple: Кортеж чекпоинтера от LangGraph
            previous_tool_calls: Множество уже виденных tool_calls

        Returns:
            Список новых вызовов инструментов
        """
        new_tool_calls = []

        try:
            channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])

            if not isinstance(messages, list):
                return new_tool_calls

            for msg in messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_call_info = {
                            "name": tool_call.get("name", "unknown"),
                            "arguments": tool_call.get("arguments", {}),
                            "id": tool_call.get("id", ""),
                            "type": tool_call.get("type", "function")
                        }

                        # Создаем уникальный ключ для tool_call
                        tool_call_key = f"{tool_call_info['name']}_{str(tool_call_info['arguments'])}_{tool_call_info['id']}"

                        # Добавляем только если не видели раньше
                        if tool_call_key not in previous_tool_calls:
                            new_tool_calls.append(tool_call_info)
                            previous_tool_calls.add(tool_call_key)

        except Exception as e:
            logger.warning(f"Ошибка извлечения tool_calls из чекпоинтера: {e}")

        return new_tool_calls

    def _extract_store_variables(self, checkpoint_tuple) -> Dict[str, Any]:
        """
        Извлекает переменные store из чекпоинтера.

        Args:
            checkpoint_tuple: Кортеж чекпоинтера от LangGraph

        Returns:
            Словарь с переменными store
        """
        try:
            channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
            store = channel_values.get("store", {})

            if not isinstance(store, dict):
                return {}

            # Фильтруем и форматируем переменные store
            formatted_store = {}
            for key, value in store.items():
                if isinstance(value, (str, int, float, bool)):
                    formatted_store[key] = value
                elif isinstance(value, (list, dict)):
                    formatted_store[key] = f"{type(value).__name__}({len(value) if hasattr(value, '__len__') else 'unknown'})"
                else:
                    formatted_store[key] = f"{type(value).__name__}"

            return formatted_store

        except Exception as e:
            logger.warning(f"Ошибка извлечения store из чекпоинтера: {e}")
            return {}

    def _format_tool_calls_for_display(self, tool_calls: List[Dict[str, Any]]) -> str:
        """
        Форматирует список вызовов инструментов для отображения.

        Args:
            tool_calls: Список вызовов инструментов

        Returns:
            Отформатированная строка
        """
        if not tool_calls:
            return "Нет вызовов инструментов"

        lines = []
        for i, tool_call in enumerate(tool_calls, 1):
            name = tool_call.get("name", "unknown")
            args = tool_call.get("arguments", {})

            # Форматируем аргументы
            if isinstance(args, dict):
                args_str = ", ".join(f"{k}={v}" for k, v in args.items() if len(str(args)) < 100)
                if len(str(args)) >= 100:
                    args_str = f"{len(args)} параметров"
            else:
                args_str = str(args)[:50] + "..." if len(str(args)) > 50 else str(args)

            lines.append(f"{name}({args_str})")

        return " | ".join(lines)

    def generate_timeline_representation(self, thread_id: str, connections_data: Dict[str, Any], include_values: bool = False) -> str:
        """
        Генерирует timeline представление выполнения агента.

        Args:
            thread_id: ID потока
            connections_data: Данные о связях чекпоинтеров
            include_values: Включать ли детальные значения

        Returns:
            Timeline диаграмма в формате текста
        """
        lines = []
        lines.append(f"🕐 TIMELINE ВЫПОЛНЕНИЯ АГЕНТА")
        lines.append(f"Поток: {thread_id}")
        lines.append("=" * 80)
        lines.append("")

        connections = connections_data["connections"]
        if not connections:
            lines.append("Нет данных о выполнении")
            return "\n".join(lines)

        # Группируем connections по времени (сначала новые)
        sorted_connections = sorted(connections, key=lambda x: x["to"]["timestamp"], reverse=True)

        for i, conn in enumerate(sorted_connections, 1):
            step = conn["to"]["step"]
            timestamp = conn["to"]["timestamp"]
            transition = conn["transition_type"]

            lines.append(f"[{i:2d}] ШАГ {step} | {timestamp}")
            lines.append(f"     Тип: {transition}")

            # Информация о tool_calls
            tool_calls = conn["to"].get("tool_calls", [])
            if tool_calls:
                lines.append("     🔧 Вызовы инструментов:")
                for tool_call in tool_calls:
                    name = tool_call.get("name", "unknown")
                    args = tool_call.get("arguments", {})
                    if args and isinstance(args, dict):
                        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                        lines.append(f"        • {name}({args_str})")
                    else:
                        lines.append(f"        • {name}()")
            else:
                lines.append("     🔧 Инструменты: не вызывались")

            # Информация о store переменных
            store_vars = conn["to"].get("store_variables", {})
            if store_vars:
                lines.append("     📦 Переменные состояния:")
                for key, value in store_vars.items():
                    lines.append(f"        • {key}: {value}")
            else:
                lines.append("     📦 Переменные: отсутствуют")

            # Информация о сообщениях (если include_values)
            if include_values:
                messages = conn["to"].get("values", {}).get("messages", [])
                if messages:
                    last_msg = messages[-1] if messages else None
                    if hasattr(last_msg, 'content'):
                        content = last_msg.content[:100] + "..." if len(last_msg.content) > 100 else last_msg.content
                        lines.append(f"     💬 Последнее сообщение: {content}")
                    elif hasattr(last_msg, 'type'):
                        lines.append(f"     💬 Последнее сообщение: {last_msg.type}")

            lines.append("")  # Пустая строка между шагами

        # Добавляем сводку
        summary = connections_data["summary"]
        lines.append("=" * 80)
        lines.append("📊 СВОДКА ВЫПОЛНЕНИЯ:")
        lines.append(f"   Всего шагов: {summary['total_checkpoints']}")
        lines.append(f"   Всего переходов: {summary['total_connections']}")
        lines.append(f"   Типы переходов: {', '.join(f'{k}({v})' for k, v in summary['transition_stats'].items())}")

        # Статистика по инструментам
        all_tool_calls = []
        for conn in connections:
            all_tool_calls.extend(conn["to"].get("tool_calls", []))

        if all_tool_calls:
            tool_stats = {}
            for tool_call in all_tool_calls:
                name = tool_call.get("name", "unknown")
                tool_stats[name] = tool_stats.get(name, 0) + 1

            lines.append(f"   Вызовы инструментов: {', '.join(f'{k}({v})' for k, v in tool_stats.items())}")
        else:
            lines.append("   Вызовы инструментов: отсутствовали")
        return "\n".join(lines)

    def generate_timeline_mermaid(self, thread_id: str, connections_data: Dict[str, Any], include_values: bool = False) -> str:
        """
        Генерирует Mermaid timeline диаграмму выполнения агента.

        Args:
            thread_id: ID потока
            connections_data: Данные о связях чекпоинтеров
            include_values: Включать ли детальные значения

        Returns:
            Mermaid timeline диаграмма
        """
        lines = []
        lines.append("timeline")
        lines.append(f"    title Timeline выполнения агента")
        lines.append(f"    Поток: {thread_id[:20]}...")
        lines.append("")

        connections = connections_data["connections"]
        if not connections:
            lines.append("    section Нет данных")
            lines.append("        Нет чекпоинтеров")
            return "\n".join(lines)

        # Группируем connections по времени (сначала новые)
        sorted_connections = sorted(connections, key=lambda x: x["to"]["timestamp"], reverse=True)

        current_section = None

        for conn in sorted_connections:
            step = conn["to"]["step"]
            timestamp = conn["to"]["timestamp"]
            transition = conn["transition_type"]

            # Создаем секцию по типу перехода
            section_name = f"Шаг {step} ({transition})"
            if section_name != current_section:
                lines.append(f"    section {section_name}")
                current_section = section_name

            # Время выполнения
            time_str = timestamp.split('T')[1][:8] if 'T' in timestamp else timestamp[:19]
            lines.append(f"        {time_str} : Начало шага")

            # Информация о tool_calls
            tool_calls = conn["to"].get("tool_calls", [])
            if tool_calls:
                for tool_call in tool_calls:
                    name = tool_call.get("name", "unknown")
                    args = tool_call.get("arguments", {})
                    if args and isinstance(args, dict):
                        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                        lines.append(f"        {time_str} : 🔧 {name}({args_str})")
                    else:
                        lines.append(f"        {time_str} : 🔧 {name}()")
            else:
                lines.append(f"        {time_str} : 🔧 Инструменты не вызывались")

            # Информация о store переменных
            store_vars = conn["to"].get("store_variables", {})
            if store_vars:
                for key, value in store_vars.items():
                    lines.append(f"        {time_str} : 📦 {key} = {value}")

            # Информация о сообщениях (если include_values)
            if include_values:
                messages = conn["to"].get("values", {}).get("messages", [])
                if messages:
                    last_msg = messages[-1] if messages else None
                    if hasattr(last_msg, 'content') and last_msg.content:
                        content = last_msg.content[:50] + "..." if len(last_msg.content) > 50 else last_msg.content
                        lines.append(f"        {time_str} : 💬 {content}")

        return "\n".join(lines)


async def main():
    """Основная функция для работы с инспектором чекпоинтеров"""
    parser = argparse.ArgumentParser(description="Инспектор чекпоинтеров LangGraph")
    parser.add_argument("--thread-id", help="ID потока для анализа")
    parser.add_argument("--list-threads", action="store_true", help="Показать список доступных потоков")
    parser.add_argument("--format", choices=["text", "mermaid", "json", "timeline", "timeline-mermaid"], default="text",
                       help="Формат вывода (text, mermaid, json, timeline, timeline-mermaid)")
    parser.add_argument("--include-values", action="store_true",
                       help="Включать значения состояния в вывод")
    parser.add_argument("--limit", type=int, default=10,
                       help="Максимальное количество потоков для отображения")

    args = parser.parse_args()

    inspector = CheckpointInspector()

    try:
        if args.list_threads:
            # Показываем список доступных потоков
            print("Получаем список доступных потоков...")
            thread_ids = await inspector.get_thread_list(limit=args.limit)
            print(f"Найдено потоков: {len(thread_ids)}")
            if thread_ids:
                print("\nДоступные потоки:")
                for i, thread_id in enumerate(thread_ids, 1):
                    print(f"  {i}. {thread_id}")
            else:
                print("Нет доступных потоков с чекпоинтерами")
            return

        # Определяем thread_id
        if args.thread_id:
            thread_id = args.thread_id
        else:
            # Получаем список и выбираем первый
            thread_ids = await inspector.get_thread_list(limit=1)
            if not thread_ids:
                print("Нет доступных потоков с чекпоинтерами")
                return
            thread_id = thread_ids[0]
            print(f"Используем поток по умолчанию: {thread_id}")

        print(f"Анализируем поток: {thread_id}")

        # Получаем визуализацию в выбранном формате
        result = await inspector.get_visualization(
            thread_id,
            format=args.format,
            include_values=args.include_values
        )

        if args.format in ["json", "timeline", "timeline-mermaid"]:
            print(result)
        else:
            print(result)

    except Exception as e:
        logger.error(f"Ошибка выполнения: {e}", exc_info=True)
        print(f"Ошибка: {e}")
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

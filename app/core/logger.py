"""
Настройка логирования приложения.

Система логирования поддерживает несколько форматов:

## Форматы для файлов:
1. JSON формат (json_format: true) - компактный JSON для парсинга и анализа
2. Pretty формат (json_format: false) - читаемый текстовый формат

## Форматы для консоли (console_format):
1. "structured" (рекомендуется) - красивый структурированный вывод с цветами
2. "json" - компактный JSON (как в файлах)
3. "pretty" - текстовый формат

## Пример Structured формата (консоль):

14:32:15.123 INFO     app.core.lifespan [lifespan:startup:42]
  ▸ Приложение запущено
  Context:
    user: Иван Иванов (user_123)
    company: Моя Компания (comp_456)
    session: session_789
    platform: telegram
    agent: FAQ Агент (agent_101)
    flow: Обработка жалоб (flow_202)

## Пример JSON формата (файлы):

{
  "timestamp": "2025-10-22T19:55:42.417000",
  "level": "INFO",
  "logger": "app.main",
  "message": "Приложение запущено",
  "module": "main",
  "function": "startup",
  "line": 123,
  "process": 12345,
  "thread": 123,
  "context": {
    "user": {"user_id": "user_123", "name": "Иван Иванов", "status": "active"},
    "company": {"company_id": "comp_456", "name": "Моя Компания", "subdomain": "company"},
    "session_id": "session_789",
    "platform": "telegram",
    "agent": {"agent_id": "agent_101", "name": "FAQ Агент", "model": "claude-3"},
    "flow": {"flow_id": "flow_202", "name": "Обработка жалоб", "entry_point_agent": "complaint_agent"}
  }
}

## Настройки в conf.json:

"logging": {
  "level": "INFO",
  "json_format": true,           # Формат для файлов
  "console_format": "structured", # Формат для консоли: "structured", "json", "pretty"
  "console_colors": true,         # Использовать цвета в консоли
  "file_enabled": true,
  "console_enabled": true
}
"""

import logging
import logging.handlers
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    """JSON форматтер для структурированных логов (для файлов)"""

    def format(self, record):
        # Базовые поля лог-записи
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Добавляем информацию из контекста
        try:
            from app.core.context import get_context
            context = get_context()

            if context:
                context_info = {}

                # Информация о пользователе
                if context.user:
                    try:
                        context_info["user"] = {
                            "user_id": getattr(context.user, 'user_id', 'unknown'),
                            "name": getattr(context.user, 'name', 'unknown'),
                            "status": getattr(context.user.status, 'value', str(context.user.status)) if hasattr(context.user, 'status') else 'unknown'
                        }
                    except Exception:
                        context_info["user"] = {"error": "failed to extract user info"}

                # Информация о компании
                if context.active_company:
                    try:
                        context_info["company"] = {
                            "company_id": getattr(context.active_company, 'company_id', 'unknown'),
                            "name": getattr(context.active_company, 'name', 'unknown'),
                            "subdomain": getattr(context.active_company, 'subdomain', 'unknown')
                        }
                    except Exception:
                        context_info["company"] = {"error": "failed to extract company info"}

                # Сессия
                if context.session_id:
                    context_info["session_id"] = context.session_id

                # Платформа
                context_info["platform"] = context.platform

                # Агент
                if context.agent_config:
                    try:
                        context_info["agent"] = {
                            "agent_id": getattr(context.agent_config, 'agent_id', 'unknown'),
                            "name": getattr(context.agent_config, 'name', 'unknown'),
                            "model": getattr(context.agent_config, 'model', 'unknown')
                        }
                    except Exception:
                        context_info["agent"] = {"error": "failed to extract agent info"}

                # Flow
                if context.flow_config:
                    try:
                        context_info["flow"] = {
                            "flow_id": getattr(context.flow_config, 'flow_id', 'unknown'),
                            "name": getattr(context.flow_config, 'name', 'unknown'),
                            "entry_point_agent": str(getattr(context.flow_config, 'entry_point_agent', 'unknown'))
                        }
                    except Exception:
                        context_info["flow"] = {"error": "failed to extract flow info"}

                # Переменные flow (если не пустые)
                if context.flow_variables:
                    context_info["flow_variables"] = context.flow_variables

                # State (если есть и не слишком большой)
                if context.state and len(str(context.state)) < 1000:  # Ограничение размера
                    context_info["state"] = context.state

                # Метаданные (если есть)
                if context.metadata:
                    context_info["metadata"] = context.metadata

                if context_info:
                    log_entry["context"] = context_info

        except Exception as e:
            # Если не удалось получить контекст, добавляем информацию об ошибке
            log_entry["context_error"] = str(e)

        # Добавляем exc_info если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Добавляем дополнительные поля из record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, ensure_ascii=False, default=str, separators=(',', ':'))


class StructuredConsoleFormatter(logging.Formatter):
    """Красивый структурированный форматтер для консоли с цветовой подсветкой"""

    # ANSI цветовые коды
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m',       # Reset
        'BOLD': '\033[1m',        # Bold
        'DIM': '\033[2m',         # Dim
        'BLUE': '\033[34m',       # Blue
        'GRAY': '\033[90m',       # Gray
    }

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def _colorize(self, text: str, color_name: str) -> str:
        """Применяет цвет к тексту если включены цвета"""
        if not self.use_colors:
            return text
        color = self.COLORS.get(color_name, '')
        reset = self.COLORS['RESET']
        return f"{color}{text}{reset}"

    def format(self, record):
        lines = []

        # Время и уровень
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname.ljust(8)

        # Основная строка: время | уровень | logger | локация
        logger_name = record.name
        location = f"{record.module}:{record.funcName}:{record.lineno}"

        # Форматируем первую строку с цветами
        time_str = self._colorize(timestamp, 'GRAY')
        level_str = self._colorize(level, record.levelname)
        logger_str = self._colorize(logger_name, 'BLUE')
        location_str = self._colorize(f"[{location}]", 'DIM')

        header = f"{time_str} {level_str} {logger_str} {location_str}"
        lines.append(header)

        # Сообщение (с отступом)
        message = record.getMessage()
        if message:
            lines.append(f"  ▸ {self._colorize(message, 'BOLD')}")

        # Добавляем контекст если есть
        context_info = {}
        try:
            from app.core.context import get_context
            context = get_context()

            if context:
                # Информация о пользователе
                if context.user:
                    try:
                        user_id = getattr(context.user, 'user_id', None)
                        user_name = getattr(context.user, 'name', None)
                        if user_id:
                            context_info["user"] = f"{user_name} ({user_id})" if user_name else user_id
                    except Exception:
                        pass

                # Информация о компании
                if context.active_company:
                    try:
                        company_id = getattr(context.active_company, 'company_id', None)
                        company_name = getattr(context.active_company, 'name', None)
                        if company_id:
                            context_info["company"] = f"{company_name} ({company_id})" if company_name else company_id
                    except Exception:
                        pass

                # Сессия
                if context.session_id:
                    context_info["session"] = context.session_id

                # Платформа
                if context.platform:
                    context_info["platform"] = context.platform

                # Агент
                if context.agent_config:
                    try:
                        agent_id = getattr(context.agent_config, 'agent_id', None)
                        agent_name = getattr(context.agent_config, 'name', None)
                        if agent_id:
                            context_info["agent"] = f"{agent_name} ({agent_id})" if agent_name else agent_id
                    except Exception:
                        pass

                # Flow
                if context.flow_config:
                    try:
                        flow_id = getattr(context.flow_config, 'flow_id', None)
                        flow_name = getattr(context.flow_config, 'name', None)
                        if flow_id:
                            context_info["flow"] = f"{flow_name} ({flow_id})" if flow_name else flow_id
                    except Exception:
                        pass

        except Exception:
            pass

        # Добавляем дополнительные поля из record
        if hasattr(record, 'extra_fields'):
            context_info.update(record.extra_fields)

        # Выводим контекст
        if context_info:
            lines.append(self._colorize("  Context:", 'DIM'))
            for key, value in context_info.items():
                key_str = self._colorize(f"    {key}:", 'GRAY')
                lines.append(f"{key_str} {value}")

        # Добавляем exception если есть
        if record.exc_info:
            lines.append(self._colorize("  Exception:", 'ERROR'))
            exc_text = self.formatException(record.exc_info)
            for line in exc_text.split('\n'):
                lines.append(f"    {self._colorize(line, 'ERROR')}")

        return '\n'.join(lines)


class PrettyJSONFormatter(logging.Formatter):
    """Форматтер для красивого вывода JSON в логах (для обратной совместимости)"""

    def format(self, record):
        msg = super().format(record)
        # Ищем JSON в сообщении и форматируем его
        if "json_data" in msg or "Request options" in msg or "Response" in msg:
            try:
                # Пытаемся найти и отформатировать JSON
                import re
                json_match = re.search(r"\{.*\}", msg, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        json_obj = eval(json_str)  # Осторожно! Только для логов
                        pretty_json = json.dumps(json_obj, indent=2, ensure_ascii=False)
                        msg = msg.replace(json_str, f"\n{pretty_json}")
                    except Exception:
                        pass
            except Exception:
                pass
        return msg


def setup_logging(component: str = "app") -> None:
    """
    Настраивает логирование для указанного компонента.

    Args:
        component: Компонент приложения ("app" или "worker")
    """
    settings = get_settings()
    logging_config = settings.logging

    # Получаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, logging_config.level.upper()))

    # Очищаем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаем форматтер для файла
    if logging_config.json_format:
        file_formatter = JSONFormatter()
    else:
        file_formatter = PrettyJSONFormatter(logging_config.format)

    # Создаем форматтер для консоли на основе настроек
    console_format = getattr(logging_config, 'console_format', 'structured')
    use_colors = getattr(logging_config, 'console_colors', True)

    if console_format == "structured":
        console_formatter = StructuredConsoleFormatter(use_colors=use_colors)
    elif console_format == "json":
        console_formatter = JSONFormatter()
    elif console_format == "pretty":
        console_formatter = PrettyJSONFormatter(logging_config.format)
    else:
        # По умолчанию structured
        console_formatter = StructuredConsoleFormatter(use_colors=use_colors)

    # Настраиваем файл для логирования
    if logging_config.file_enabled:
        # Создаем директорию для логов
        log_dir = Path(logging_config.file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Выбираем файл в зависимости от компонента
        if component == "worker":
            log_file = logging_config.worker_file_path
        else:
            log_file = logging_config.app_file_path

        # Создаем директорию для файла компонента
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Создаем RotatingFileHandler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=logging_config.file_max_bytes,
            backupCount=logging_config.file_backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Настраиваем консольный вывод
    if logging_config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Применяем индивидуальные уровни логирования для конкретных логгеров
    for logger_name, level_str in logging_config.loggers_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level_str.upper()))

    # Специальная настройка для OpenAI логов
    for logger_name in ["openai._base_client", "openai", "httpx", "httpcore"]:
        logger_obj = logging.getLogger(logger_name)
        # Применяем соответствующий форматтер ко всем обработчикам OpenAI логгеров
        for handler in logger_obj.handlers:
            if logging_config.json_format:
                handler.setFormatter(JSONFormatter())
            else:
                handler.setFormatter(PrettyJSONFormatter(logging_config.format))


def get_logger(name: str) -> logging.Logger:
    """
    Получает логгер с указанным именем.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def setup_app_logging() -> None:
    """Настраивает логирование для основного приложения"""
    setup_logging("app")


def setup_worker_logging() -> None:
    """Настраивает логирование для воркера"""
    setup_logging("worker")


def log_extra(logger: logging.Logger, level: int, message: str, extra: Dict[str, Any] = None) -> None:
    """
    Логирует сообщение с дополнительными полями.

    Args:
        logger: Logger instance
        level: Уровень логирования (logging.INFO, etc.)
        message: Сообщение для логирования
        extra: Дополнительные поля для добавления в JSON
    """
    if extra:
        logger.log(level, message, extra={"extra_fields": extra})
    else:
        logger.log(level, message)

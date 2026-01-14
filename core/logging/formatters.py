"""
Форматтеры для логирования.
"""

import logging
import json
from datetime import datetime

from core.context import get_context


class JSONFormatter(logging.Formatter):
    """
    JSON форматтер для структурированных логов (для файлов).
    Без try-except - если контекст невалиден, будет исключение.
    """

    def format(self, record):
        context = get_context()
        trace_id = context.trace_id if context else None

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
            "trace_id": trace_id,
        }

        if context:
            context_info = {}

            if context.user:
                context_info["user"] = {
                    "user_id": context.user.user_id,
                    "name": context.user.name,
                    "status": context.user.status.value if hasattr(context.user.status, 'value') else str(context.user.status)
                }

            if context.active_company:
                context_info["company"] = {
                    "company_id": context.active_company.company_id,
                    "name": context.active_company.name,
                    "subdomain": context.active_company.subdomain
                }

            if context.session_id:
                context_info["session_id"] = context.session_id

            if context.trace_id:
                context_info["trace_id"] = context.trace_id

            if hasattr(context, 'channel') and context.channel:
                context_info["channel"] = context.channel

            if hasattr(context, 'agent_id') and context.agent_id:
                context_info["agent_id"] = context.agent_id

            if context_info:
                log_entry["context"] = context_info

        if hasattr(record, 'exc_info') and record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StructuredConsoleFormatter(logging.Formatter):
    """
    Структурированный форматтер для консоли с цветами.
    """

    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def _colorize(self, text: str, color_code: str) -> str:
        """Применяет цвет к тексту"""
        if not self.use_colors:
            return text
        return f"{color_code}{text}{self.RESET}"

    def format(self, record):
        # 1. Базовые поля
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname
        message = record.getMessage()
        logger_name = record.name
        location = f"{record.module}:{record.lineno}"

        # Цветной уровень
        level_fmt = self._colorize(f"[{level}]", self.COLORS.get(level, ''))
        time_fmt = self._colorize(f"[{timestamp}]", self.DIM)
        logger_fmt = self._colorize(f"[{logger_name}]", self.DIM)
        loc_fmt = self._colorize(f"[{location}]", self.DIM)

        # 2. Сбор контекста
        ctx_parts = []
        ctx = get_context()

        if ctx:
            if ctx.trace_id:
                ctx_parts.append(f"[TRACE:{ctx.trace_id}]")

            if ctx.active_company:
                ctx_parts.append(f"[COMP:{ctx.active_company.company_id}]")

            if ctx.user:
                ctx_parts.append(f"[USER:{ctx.user.user_id}]")

            if hasattr(ctx, 'channel') and ctx.channel:
                ctx_parts.append(f"[CHAN:{ctx.channel}]")

            if ctx.session_id:
                ctx_parts.append(f"[SESS:{ctx.session_id}]")

            if ctx.agent_config:
                agent_id = getattr(ctx.agent_config, 'agent_id', 'unknown')
                ctx_parts.append(f"[AGENT:{agent_id}]")

            if ctx.agent_id:
                ctx_parts.append(f"[AGENT_ID:{ctx.agent_id}]")

        # Собираем контекст в одну строку
        context_str = " ".join(ctx_parts)
        if context_str:
            context_str = self._colorize(context_str, self.DIM)

        # 3. Итоговая сборка
        # [INFO] [Time] [Logger] [Loc] [CTX:...] Message
        if context_str:
            log_line = f"{level_fmt} {time_fmt} {logger_fmt} {loc_fmt} {context_str} {message}"
        else:
            log_line = f"{level_fmt} {time_fmt} {logger_fmt} {loc_fmt} {message}"

        # 4. Exception
        if hasattr(record, 'exc_info') and record.exc_info:
            log_line += self._colorize("\n  Exception:", '\033[31m')
            exception_text = self.formatException(record.exc_info)
            for exc_line in exception_text.split('\n'):
                log_line += self._colorize(f"\n    {exc_line}", '\033[31m')

        return log_line


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

        context = get_context()

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

            context_info["platform"] = context.platform

            if context.agent_config:
                context_info["agent"] = {
                    "agent_id": getattr(context.agent_config, 'agent_id', 'unknown'),
                    "name": getattr(context.agent_config, 'name', 'unknown'),
                    "model": getattr(context.agent_config, 'model', 'unknown')
                }

            if context.flow_config:
                context_info["flow"] = {
                    "flow_id": getattr(context.flow_config, 'flow_id', 'unknown'),
                    "name": getattr(context.flow_config, 'name', 'unknown'),
                }

            if context.flow_variables:
                context_info["flow_variables"] = context.flow_variables

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
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3]
        level = record.levelname
        logger_name = record.name
        location = f"[{record.module}:{record.funcName}:{record.lineno}]"
        message = record.getMessage()

        level_colored = self._colorize(f"{level:8}", self.COLORS.get(level, ''))
        location_colored = self._colorize(location, self.DIM)

        lines = [f"{timestamp} {level_colored} {logger_name} {location_colored}"]
        lines.append(f"  ▸ {message}")

        context = get_context()

        if context:
            context_lines = []
            
            if context.user:
                context_lines.append(f"user: {context.user.name} ({context.user.user_id})")
            
            if context.active_company:
                context_lines.append(f"company: {context.active_company.name} ({context.active_company.company_id})")
            
            if context.session_id:
                context_lines.append(f"session: {context.session_id}")
            
            context_lines.append(f"platform: {context.platform}")
            
            if context.agent_config:
                agent_name = getattr(context.agent_config, 'name', 'unknown')
                agent_id = getattr(context.agent_config, 'agent_id', 'unknown')
                context_lines.append(f"agent: {agent_name} ({agent_id})")
            
            if context.flow_config:
                flow_name = getattr(context.flow_config, 'name', 'unknown')
                flow_id = getattr(context.flow_config, 'flow_id', 'unknown')
                context_lines.append(f"flow: {flow_name} ({flow_id})")

            if context_lines:
                lines.append(self._colorize("  Context:", self.DIM))
                for line in context_lines:
                    lines.append(self._colorize(f"    {line}", self.DIM))

        if hasattr(record, 'exc_info') and record.exc_info:
            lines.append(self._colorize("  Exception:", '\033[31m'))
            exception_text = self.formatException(record.exc_info)
            for exc_line in exception_text.split('\n'):
                lines.append(self._colorize(f"    {exc_line}", '\033[31m'))

        return '\n'.join(lines)


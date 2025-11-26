"""
Модели для OpenTelemetry трейсинга.

Хранение spans в БД через Storage с ключом: otel:{trace_id}:span:{span_id}
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class SpanType(str, Enum):
    """Тип span"""
    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    CHAIN = "chain"
    RETRIEVER = "retriever"
    EMBEDDING = "embedding"
    PARSER = "parser"
    PROMPT = "prompt"
    OTHER = "other"


class SpanStatus(str, Enum):
    """Статус span"""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


class SpanRecord(BaseModel):
    """
    Запись span в БД.

    Сохраняется в storage с ключом: otel:{trace_id}:span:{span_id}
    """

    span_id: str = Field(..., description="Уникальный ID span (hex формат)")
    trace_id: str = Field(..., description="ID трейса (hex формат)")
    parent_span_id: Optional[str] = Field(None, description="ID родительского span")

    name: str = Field(..., description="Название span")
    span_type: SpanType = Field(SpanType.AGENT, description="Тип span")
    status: SpanStatus = Field(SpanStatus.SUCCESS, description="Статус выполнения")

    start_time: datetime = Field(..., description="Время начала")
    end_time: Optional[datetime] = Field(None, description="Время окончания")
    duration_ms: Optional[float] = Field(None, description="Длительность в миллисекундах")

    input_data: Optional[Any] = Field(None, description="Входные данные")
    output_data: Optional[Any] = Field(None, description="Выходные данные")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные метаданные")

    cost: Optional[float] = Field(None, description="Стоимость выполнения")
    usage: Optional[Dict[str, Any]] = Field(None, description="Usage данные (токены и т.д.)")

    error: Optional[str] = Field(None, description="Описание ошибки")

    @field_validator('status', mode='before')
    @classmethod
    def parse_status(cls, v: Union[str, Dict, SpanStatus]) -> SpanStatus:
        """Парсит status из разных форматов (старый и новый)"""
        if isinstance(v, SpanStatus):
            return v
        if isinstance(v, dict):
            # Старый формат: {"status_code": "OK", "description": None}
            status_code = v.get('status_code', 'UNSET')
            if status_code == 'ERROR':
                return SpanStatus.ERROR
            elif status_code in ('OK', 'UNSET'):
                return SpanStatus.SUCCESS
            else:
                return SpanStatus.PENDING
        if isinstance(v, str):
            try:
                return SpanStatus(v.lower())
            except ValueError:
                return SpanStatus.SUCCESS
        return SpanStatus.SUCCESS

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def parse_timestamp(cls, v: Union[int, str, datetime, None]) -> Optional[datetime]:
        """Парсит timestamp из наносекунд (старый формат) или ISO string"""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, int):
            # Наносекунды из старого формата
            return datetime.fromtimestamp(v / 1e9, tz=timezone.utc)
        if isinstance(v, str):
            # ISO format строка
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return None


class TraceInfo(BaseModel):
    """
    Информация о трейсе (группа spans).

    Используется для отображения списка трейсов.
    """

    trace_id: str = Field(..., description="ID трейса")
    name: str = Field(..., description="Название трейса (название root span)")
    status: SpanStatus = Field(..., description="Статус трейса")

    start_time: datetime = Field(..., description="Время начала трейса")
    end_time: Optional[datetime] = Field(None, description="Время окончания трейса")
    duration_ms: Optional[float] = Field(None, description="Общая длительность")

    total_spans: int = Field(..., description="Количество spans в трейсе")
    total_cost: Optional[float] = Field(None, description="Общая стоимость")

    error_count: int = Field(0, description="Количество ошибок в трейсе")

    # Для UI
    root_span_type: SpanType = Field(SpanType.AGENT, description="Тип root span")

    # Метаинформация (объединенная из всех spans)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Метаданные трейса")


class TraceDetail(BaseModel):
    """
    Детальная информация о трейсе со всеми spans.

    Используется для отображения таймлайна трейса.
    """

    trace_info: TraceInfo = Field(..., description="Общая информация о трейсе")
    spans: List[SpanRecord] = Field(..., description="Список всех spans трейса")


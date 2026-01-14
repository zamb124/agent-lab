"""
SpanRepository - репозиторий для сохранения spans в PostgreSQL.

Использует SQLAlchemy 2.0 для работы с нормализованной таблицей spans.
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert

from core.logging import get_logger

if TYPE_CHECKING:
    from core.db import Storage

logger = get_logger(__name__)


class SpanRepository:
    """
    Репозиторий для работы со spans в PostgreSQL.
    
    Использует нормализованную таблицу spans с отдельными колонками
    для быстрого поиска по user_id, agent_id, session и т.д.
    """

    def __init__(self, storage: "Storage"):
        self._storage = storage

    async def save_span(self, span_data: Dict[str, Any]) -> bool:
        """
        Сохраняет span в PostgreSQL.
        
        Args:
            span_data: Данные span
        """
        try:
            from core.db.models import Spans
            
            async with self._storage._get_session() as session:
                stmt = insert(Spans).values(
                    span_id=span_data["span_id"],
                    trace_id=span_data["trace_id"],
                    parent_span_id=span_data.get("parent_span_id"),
                    operation_name=span_data["operation_name"],
                    kind=span_data.get("kind"),
                    start_time=span_data["start_time"],
                    end_time=span_data.get("end_time"),
                    duration_ms=span_data.get("duration_ms"),
                    status=span_data.get("status"),
                    status_message=span_data.get("status_message"),
                    user_id=span_data.get("user_id"),
                    user_name=span_data.get("user_name"),
                    user_groups=span_data.get("user_groups"),
                    session_auth=span_data.get("session_auth"),
                    session_agent=span_data.get("session_agent"),
                    agent_id=span_data.get("agent_id"),
                    task_id=span_data.get("task_id"),
                    context_id=span_data.get("context_id"),
                    skill_id=span_data.get("skill_id"),
                    channel=span_data.get("channel"),
                    node_id=span_data.get("node_id"),
                    agent_name=span_data.get("agent_name"),
                    is_resume=span_data.get("is_resume"),
                    attributes=span_data.get("attributes") or {},
                    events=span_data.get("events") or [],
                ).on_conflict_do_nothing(index_elements=["span_id"])
                
                await session.execute(stmt)
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save span: {e}")
            return False

    async def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """Получает все spans для trace_id."""
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = select(Spans).where(Spans.trace_id == trace_id).order_by(Spans.start_time.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Получает все spans для task_id."""
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = select(Spans).where(Spans.task_id == task_id).order_by(Spans.start_time.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_session(
        self,
        session_agent: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Получает spans для сессии агента."""
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = (
                select(Spans)
                .where(Spans.session_agent == session_agent)
                .order_by(Spans.start_time.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_user(
        self,
        user_id: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Получает spans для пользователя."""
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = select(Spans).where(Spans.user_id == user_id)
            
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
            
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_agent(
        self,
        agent_id: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Получает spans для агента."""
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = select(Spans).where(Spans.agent_id == agent_id)
            
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
            
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_flow(
        self,
        agent_id: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Получает spans для flow (алиас для get_spans_by_agent)."""
        return await self.get_spans_by_agent(agent_id, from_time, to_time, limit)

    async def search_traces(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Поиск traces с фильтрами.
        
        Returns:
            Tuple[List[Dict], int]: (список traces с деревом spans, общее количество)
        """
        from core.db.models import Spans
        
        async with self._storage._get_session() as session:
            stmt = select(Spans)
            count_stmt = select(func.count()).select_from(Spans)
            
            if user_id:
                stmt = stmt.where(Spans.user_id == user_id)
                count_stmt = count_stmt.where(Spans.user_id == user_id)
            if session_id:
                stmt = stmt.where(Spans.session_agent == session_id)
                count_stmt = count_stmt.where(Spans.session_agent == session_id)
            if agent_id:
                stmt = stmt.where(Spans.agent_id == agent_id)
                count_stmt = count_stmt.where(Spans.agent_id == agent_id)
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
                count_stmt = count_stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
                count_stmt = count_stmt.where(Spans.start_time <= to_time)
            
            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar()
            
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit).offset(offset)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            spans = [self._serialize_span(row) for row in rows]
            
            traces_dict = {}
            for span in spans:
                trace_id = span["trace_id"]
                if trace_id not in traces_dict:
                    traces_dict[trace_id] = {
                        "trace_id": trace_id,
                        "spans": []
                    }
                traces_dict[trace_id]["spans"].append(span)
            
            traces = list(traces_dict.values())
            
            return traces, total_count or 0

    def _serialize_span(self, row) -> Dict[str, Any]:
        """Преобразует SQLAlchemy модель в словарь."""
        return {
            "span_id": row.span_id,
            "trace_id": row.trace_id,
            "parent_span_id": row.parent_span_id,
            "operation_name": row.operation_name,
            "kind": row.kind,
            "start_time": row.start_time.isoformat() if row.start_time else None,
            "end_time": row.end_time.isoformat() if row.end_time else None,
            "duration_ms": row.duration_ms,
            "status": row.status,
            "status_message": row.status_message,
            "user_id": row.user_id,
            "user_name": row.user_name,
            "user_groups": row.user_groups,
            "session_auth": row.session_auth,
            "session_agent": row.session_agent,
            "agent_id": row.agent_id,
            "task_id": row.task_id,
            "context_id": row.context_id,
            "skill_id": row.skill_id,
            "channel": row.channel,
            "node_id": row.node_id,
            "agent_name": row.agent_name,
            "is_resume": row.is_resume,
            "attributes": row.attributes or {},
            "events": row.events or [],
        }

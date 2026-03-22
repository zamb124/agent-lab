"""
Типы для каналов коммуникации.
"""

from typing import Any, Dict, List, Optional

from a2a.types import Message


class PreparedTaskParams:
    """Подготовленные параметры для process_task."""
    
    def __init__(
        self,
        task_id: str,
        context_id: str,
        session_id: str,
        content: str,
        skill_id: str,
        is_resume: bool,
        files_data: List[Dict],
        message: Optional[Message],
        metadata: Optional[Dict],
        user_id: Optional[str] = None,
    ):
        self.task_id = task_id
        self.context_id = context_id
        self.session_id = session_id
        self.content = content
        self.skill_id = skill_id
        self.is_resume = is_resume
        self.files_data = files_data
        self.message = message
        self.metadata = metadata
        self.user_id = user_id or context_id


"""
API модели для AccessGrants.
"""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class GrantToUserRequest(BaseModel):
    """Запрос на шаринг конкретному user"""

    user_id: str
    role: str = Field(default="viewer", pattern="^(viewer|editor|admin)$")
    expires_at: datetime | None = None


class GrantToCompanyRequest(BaseModel):
    """Запрос на шаринг целой компании"""

    company_id: str
    role: str = Field(default="viewer", pattern="^(viewer|editor|admin)$")
    expires_at: datetime | None = None


class AccessGrantResponse(BaseModel):
    """Ответ с информацией о гранте"""

    grant_id: str
    company_id: str
    created_by: str
    resource_type: str
    resource_id: str
    grant_type: str
    target_user_id: str | None = None
    target_company_id: str | None = None
    role: str
    expires_at: datetime | None = None
    created_at: datetime

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

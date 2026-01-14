"""
API модели для AccessGrants.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class GrantToUserRequest(BaseModel):
    """Запрос на шаринг конкретному user"""
    user_id: str
    role: str = Field(default="viewer", pattern="^(viewer|editor|admin)$")
    expires_at: Optional[datetime] = None


class GrantToCompanyRequest(BaseModel):
    """Запрос на шаринг целой компании"""
    company_id: str
    role: str = Field(default="viewer", pattern="^(viewer|editor|admin)$")
    expires_at: Optional[datetime] = None


class AccessGrantResponse(BaseModel):
    """Ответ с информацией о гранте"""
    grant_id: str
    company_id: str
    created_by: str
    resource_type: str
    resource_id: str
    grant_type: str
    target_user_id: Optional[str] = None
    target_company_id: Optional[str] = None
    role: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


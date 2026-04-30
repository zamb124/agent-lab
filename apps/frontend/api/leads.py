"""
Заявки с лендинга: запись в shared storage (ключи company:system:request:*).
"""
import json

from core.logging import get_logger
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator, model_validator

from apps.frontend.dependencies import ContainerDep
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID

logger = get_logger(__name__)
REQUEST_STORAGE_PREFIX = f"company:{SYSTEM_COMPANY_ID}:request:"

leads_router = APIRouter(prefix="/api/leads", tags=["leads"])
lead_requests_router = APIRouter(prefix="/api/lead-requests", tags=["lead-requests"])

class LeadCreateBody(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("email", "phone", "company", "comment", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if v == "":
            return None
        return v

    @field_validator("email")
    @classmethod
    def validate_email_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_regex, v):
            raise ValueError("Invalid email format")
        return v

    @model_validator(mode="after")
    def require_email_or_phone(self):
        has_email = self.email is not None
        has_phone = self.phone is not None and str(self.phone).strip() != ""
        if not has_email and not has_phone:
            raise ValueError("Укажите email или телефон")
        return self

@leads_router.post("")
async def create_lead(body: LeadCreateBody, container: ContainerDep):
    rid = str(uuid.uuid4())
    key = f"{REQUEST_STORAGE_PREFIX}{rid}"
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "id": rid,
        "name": body.name,
        "email": body.email,
        "phone": body.phone,
        "company": body.company,
        "comment": body.comment,
        "created_at": now,
    }
    storage = container.shared_storage
    await storage.set(key, json.dumps(payload), force_global=True)
    logger.info("Landing lead saved: %s", key)
    return {
        "success": True,
        "message": "Заявка принята. Мы свяжемся с вами в ближайшее время.",
        "id": rid,
    }

@lead_requests_router.get("")
async def list_lead_requests(request: Request, container: ContainerDep):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = getattr(request.state, "company", None)
    if not company or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")
    storage = container.shared_storage
    raw = await storage.get_all_by_prefix(REQUEST_STORAGE_PREFIX, limit=2000, force_global=True)
    items: list[dict[str, Any]] = []
    for key, val_json in raw.items():
        try:
            if isinstance(val_json, str):
                d = json.loads(val_json)
            elif isinstance(val_json, dict):
                d = val_json
            else:
                continue
            if isinstance(d, dict):
                row = {"storage_key": key, **d}
                items.append(row)
        except json.JSONDecodeError:
            logger.warning("list_lead_requests: skip bad JSON for key=%s", key)
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {"items": items}

"""Wire-контракт CRM grants (OpenFGA tuples, без SQL AccessGrant)."""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

GrantRole = Literal["viewer", "editor", "admin", "owner"]
GrantSubjectKind = Literal["user", "public", "company"]
GrantResourceType = Literal["entity", "namespace"]


class AccessGrantResponse(BaseModel):
    """Один tuple OpenFGA как grant для API/UI."""

    grant_id: str
    resource_type: GrantResourceType
    resource_id: str
    resource_company_id: str | None = None
    grant_type: GrantSubjectKind
    target_user_id: str | None = None
    target_company_id: str | None = None
    role: GrantRole

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

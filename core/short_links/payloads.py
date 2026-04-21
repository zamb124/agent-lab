from pydantic import BaseModel, Field


class SyncCallJoinPayload(BaseModel):
    link_token: str = Field(min_length=1)
    company_id: str = Field(min_length=1)


class CompanyInvitePayload(BaseModel):
    jwt: str = Field(min_length=1)

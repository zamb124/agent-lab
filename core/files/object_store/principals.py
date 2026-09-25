"""Кто просит байты. Флагов нет: каждый вызывающий — свой тип."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionPrincipal:
    user_id: str
    company_id: str


@dataclass(frozen=True, slots=True)
class ExecutionPrincipal:
    company_id: str
    flow_id: str


@dataclass(frozen=True, slots=True)
class SystemPrincipal:
    company_id: str


@dataclass(frozen=True, slots=True)
class SignedFileGrant:
    file_id: str
    company_id: str


@dataclass(frozen=True, slots=True)
class AnonymousPrincipal:
    pass


FilePrincipal = (
    SessionPrincipal | ExecutionPrincipal | SystemPrincipal | SignedFileGrant | AnonymousPrincipal
)


def principal_company_id(principal: FilePrincipal) -> str | None:
    if isinstance(principal, AnonymousPrincipal):
        return None
    return principal.company_id

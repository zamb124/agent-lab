"""
Репозиторий версионируемых переменных `platform_secrets`.

Шифрование симметрично для всех переменных: секретная переменная хранит payload как
Fernet-ciphertext (`value_encrypted`), несекретная — plaintext JSONB (`value_payload`).
Расшифровка ленивая: `include_secret_values=True` запрашивается только на резолве/по
явному запросу с проверкой доступа в сервисе.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from core.db.utils import get_rowcount
from core.secrets.crypto import decrypt_secret, encrypt_secret
from core.secrets.db import SecretsDatabase
from core.secrets.db_models import SecretVariableRow, SecretVariableVersionRow
from core.types import JsonObject, require_json_object
from core.variables.models import PlatformVariable, VariableValuePayload

_MASKED_PAYLOAD: VariableValuePayload = VariableValuePayload()


def _payload_from_row(
    row: SecretVariableRow | SecretVariableVersionRow,
    include_secret_values: bool,
) -> VariableValuePayload:
    if row.secret:
        if not include_secret_values:
            return _MASKED_PAYLOAD.model_copy(deep=True)
        if row.value_encrypted is None:
            raise ValueError(
                f"Секретная переменная '{row.variable_key}' без value_encrypted"
            )
        return VariableValuePayload.model_validate_json(decrypt_secret(row.value_encrypted))
    return VariableValuePayload.model_validate(require_json_object(row.value_payload, "value_payload"))


def _row_to_variable(
    row: SecretVariableRow,
    include_secret_values: bool,
) -> PlatformVariable:
    return PlatformVariable(
        variable_key=row.variable_key,
        company_id=row.company_id,
        version=row.version,
        payload=_payload_from_row(row, include_secret_values),
        secret=row.secret,
        shared_for_execution=row.shared_for_execution,
        public=row.public,
        created_by=row.created_by,
        title=row.title,
        description=row.description,
        order=row.order_index,
        groups=[str(group) for group in row.groups],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _encode_payload(variable: PlatformVariable) -> tuple[JsonObject | None, str | None]:
    """Возвращает (value_payload JSONB, value_encrypted) по признаку секрета."""
    if variable.secret:
        return None, encrypt_secret(variable.payload.model_dump_json())
    return require_json_object(variable.payload.model_dump(mode="json"), "payload"), None


class SecretsRepository:
    """CRUD + версионирование переменных компании."""

    def __init__(self, db: SecretsDatabase) -> None:
        self._db: SecretsDatabase = db

    async def upsert(self, variable: PlatformVariable) -> PlatformVariable:
        value_payload, value_encrypted = _encode_payload(variable)
        async with self._db.session() as session:
            existing = (
                await session.execute(
                    select(SecretVariableRow.version).where(
                        SecretVariableRow.company_id == variable.company_id,
                        SecretVariableRow.variable_key == variable.variable_key,
                    )
                )
            ).scalar_one_or_none()
            next_version = 1 if existing is None else existing + 1

            row = SecretVariableRow(
                company_id=variable.company_id,
                variable_key=variable.variable_key,
                version=next_version,
                secret=variable.secret,
                shared_for_execution=variable.shared_for_execution,
                public=variable.public,
                created_by=variable.created_by,
                title=variable.title,
                description=variable.description,
                order_index=variable.order,
                groups=list(variable.groups),
                value_payload=value_payload,
                value_encrypted=value_encrypted,
            )
            merged = await session.merge(row)
            session.add(
                SecretVariableVersionRow(
                    company_id=variable.company_id,
                    variable_key=variable.variable_key,
                    version=next_version,
                    secret=variable.secret,
                    shared_for_execution=variable.shared_for_execution,
                    public=variable.public,
                    created_by=variable.created_by,
                    title=variable.title,
                    description=variable.description,
                    order_index=variable.order,
                    groups=list(variable.groups),
                    value_payload=value_payload,
                    value_encrypted=value_encrypted,
                )
            )
            await session.commit()
            await session.refresh(merged)
            return _row_to_variable(merged, include_secret_values=True)

    async def get(
        self,
        company_id: str,
        variable_key: str,
        *,
        include_secret_values: bool,
    ) -> PlatformVariable | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(SecretVariableRow).where(
                        SecretVariableRow.company_id == company_id,
                        SecretVariableRow.variable_key == variable_key,
                    )
                )
            ).scalar_one_or_none()
            return _row_to_variable(row, include_secret_values) if row is not None else None

    async def list(
        self,
        company_id: str,
        *,
        include_secret_values: bool,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[PlatformVariable]:
        async with self._db.session() as session:
            stmt = (
                select(SecretVariableRow)
                .where(SecretVariableRow.company_id == company_id)
                .order_by(SecretVariableRow.variable_key.asc())
                .limit(limit)
                .offset(offset)
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [_row_to_variable(row, include_secret_values) for row in rows]

    async def count(self, company_id: str) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(
                select(SecretVariableRow)
                .where(SecretVariableRow.company_id == company_id)
                .subquery()
            )
            return (await session.execute(stmt)).scalar_one()

    async def delete(self, company_id: str, variable_key: str) -> bool:
        async with self._db.session() as session:
            _ = await session.execute(
                delete(SecretVariableVersionRow).where(
                    SecretVariableVersionRow.company_id == company_id,
                    SecretVariableVersionRow.variable_key == variable_key,
                )
            )
            result = await session.execute(
                delete(SecretVariableRow).where(
                    SecretVariableRow.company_id == company_id,
                    SecretVariableRow.variable_key == variable_key,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0

    async def list_versions(
        self,
        company_id: str,
        variable_key: str,
        *,
        include_secret_values: bool,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PlatformVariable]:
        async with self._db.session() as session:
            stmt = (
                select(SecretVariableVersionRow)
                .where(
                    SecretVariableVersionRow.company_id == company_id,
                    SecretVariableVersionRow.variable_key == variable_key,
                )
                .order_by(SecretVariableVersionRow.version.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = list((await session.execute(stmt)).scalars().all())
            return [
                PlatformVariable(
                    variable_key=row.variable_key,
                    company_id=row.company_id,
                    version=row.version,
                    payload=_payload_from_row(row, include_secret_values),
                    secret=row.secret,
                    shared_for_execution=row.shared_for_execution,
                    public=row.public,
                    created_by=row.created_by,
                    title=row.title,
                    description=row.description,
                    order=row.order_index,
                    groups=[str(group) for group in row.groups],
                    created_at=row.created_at,
                    updated_at=row.created_at,
                )
                for row in rows
            ]

    async def count_versions(self, company_id: str, variable_key: str) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(
                select(SecretVariableVersionRow)
                .where(
                    SecretVariableVersionRow.company_id == company_id,
                    SecretVariableVersionRow.variable_key == variable_key,
                )
                .subquery()
            )
            return (await session.execute(stmt)).scalar_one()


__all__ = ["SecretsRepository"]

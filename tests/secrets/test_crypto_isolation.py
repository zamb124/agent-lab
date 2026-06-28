"""Fernet round-trip и изоляция переменных по company_id."""

from __future__ import annotations

import pytest

from core.secrets.crypto import decrypt_secret, encrypt_secret
from core.variables.models import (
    PlatformVariable,
    VariableValueKind,
    VariableValuePayload,
    VariableValueSpec,
)


def test_encrypt_decrypt_round_trip() -> None:
    plaintext = "demo-shared-api-key-12345"
    token = encrypt_secret(plaintext)
    assert token != plaintext
    assert decrypt_secret(token) == plaintext


@pytest.mark.asyncio
async def test_repository_company_isolation(secrets_repository, unique_id: str) -> None:
    company_a = f"company_a_{unique_id}"
    company_b = f"company_b_{unique_id}"
    variable_key = f"isolated_{unique_id}"
    value_a = f"secret-a-{unique_id}"
    value_b = f"secret-b-{unique_id}"

    await secrets_repository.upsert(
        PlatformVariable(
            variable_key=variable_key,
            company_id=company_a,
            secret=True,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value_a)
            ),
        )
    )
    await secrets_repository.upsert(
        PlatformVariable(
            variable_key=variable_key,
            company_id=company_b,
            secret=True,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value_b)
            ),
        )
    )

    fetched_a = await secrets_repository.get(company_a, variable_key, include_secret_values=True)
    fetched_b = await secrets_repository.get(company_b, variable_key, include_secret_values=True)
    assert fetched_a is not None
    assert fetched_b is not None
    assert fetched_a.payload.base.value == value_a
    assert fetched_b.payload.base.value == value_b

    list_a = await secrets_repository.list(company_a, include_secret_values=False)
    list_b = await secrets_repository.list(company_b, include_secret_values=False)
    masked_a = next(item for item in list_a if item.variable_key == variable_key)
    masked_b = next(item for item in list_b if item.variable_key == variable_key)
    assert masked_a.payload.base.value is None
    assert masked_b.payload.base.value is None

    await secrets_repository.delete(company_a, variable_key)
    await secrets_repository.delete(company_b, variable_key)

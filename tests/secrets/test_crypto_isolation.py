"""Fernet round-trip и изоляция переменных по company_id."""

from __future__ import annotations

import pytest

from core.secrets.crypto import decrypt_secret, encrypt_secret
from core.secrets.models import SecretVariable, SecretVariableVersion
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
async def test_repository_company_isolation(unique_id: str) -> None:
    company_a = f"company_a_{unique_id}"
    company_b = f"company_b_{unique_id}"
    variable_key = f"isolated_{unique_id}"
    value_a = f"secret-a-{unique_id}"
    value_b = f"secret-b-{unique_id}"

    _ = await SecretVariable.append_version(
        PlatformVariable(
            variable_key=variable_key,
            company_id=company_a,
            secret=True,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value_a)
            ),
        )
    )
    _ = await SecretVariable.append_version(
        PlatformVariable(
            variable_key=variable_key,
            company_id=company_b,
            secret=True,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=value_b)
            ),
        )
    )

    fetched_a = await SecretVariable.current_for_variable_key(company_a, variable_key, include_secret_values=True)
    fetched_b = await SecretVariable.current_for_variable_key(company_b, variable_key, include_secret_values=True)
    assert fetched_a is not None
    assert fetched_b is not None
    assert fetched_a.payload.base.value == value_a
    assert fetched_b.payload.base.value == value_b
    masked = await SecretVariable.current_for_variable_key(
        company_a,
        variable_key,
        include_secret_values=False,
    )
    assert masked is not None
    assert masked.payload.base.value is None

    list_a = await SecretVariable.list_for_company(company_a)
    list_b = await SecretVariable.list_for_company(company_b)
    masked_a = next(item for item in list_a if item.variable_key == variable_key)
    masked_b = next(item for item in list_b if item.variable_key == variable_key)
    assert masked_a.payload.base.value is None
    assert masked_b.payload.base.value is None

    rewritten = await SecretVariable.append_version(
        PlatformVariable(
            variable_key=variable_key,
            company_id=company_a,
            secret=True,
            payload=VariableValuePayload(
                base=VariableValueSpec(value_kind=VariableValueKind.STATIC, value=f"{value_a}-v2")
            ),
        )
    )
    assert rewritten.version == 2
    deleted_a = await SecretVariable.delete_by_company_and_variable_key(company_a, variable_key)
    assert deleted_a is True
    assert await SecretVariable.delete_by_company_and_variable_key(company_a, variable_key) is False
    assert await SecretVariable.current_for_variable_key(company_a, variable_key, include_secret_values=True) is None
    assert (
        await SecretVariableVersion.objects.filter(
            company_id=company_a,
            variable_key=variable_key,
        ).count()
        == 0
    )
    still_b = await SecretVariable.current_for_variable_key(company_b, variable_key, include_secret_values=True)
    assert still_b is not None
    assert still_b.payload.base.value == value_b
    deleted_b = await SecretVariable.delete_by_company_and_variable_key(company_b, variable_key)
    assert deleted_b is True

"""
Pydantic-модели HumanitecAgent.
"""

import pytest
from pydantic import ValidationError

from apps.agent.models import AgentDeviceRecord, DevicePolicy, DeviceRegisterRequest


def test_device_policy_defaults() -> None:
    policy = DevicePolicy()
    assert policy.shell_enabled is False
    assert policy.exec_require_confirm is True
    assert policy.browser_enabled is True
    assert policy.max_file_size_mb == 50


def test_agent_device_record_round_trip() -> None:
    payload = {
        "device_id": "dev-1",
        "device_name": "MacBook",
        "user_id": "user-1",
        "company_id": "company-1",
        "os": "darwin",
        "hostname": "mac.local",
        "is_active": True,
        "policy": {
            "allowed_roots": ["/Users/test"],
            "exec_whitelist": [],
            "exec_require_confirm": True,
            "shell_enabled": False,
            "browser_enabled": True,
            "max_file_size_mb": 50,
            "audit_retention_days": 30,
        },
    }
    record = AgentDeviceRecord.model_validate(payload)
    restored = AgentDeviceRecord.model_validate_json(record.model_dump_json())
    assert restored.device_id == "dev-1"
    assert restored.policy.allowed_roots == ["/Users/test"]


def test_device_register_request_pairing_code_length() -> None:
    with pytest.raises(ValidationError):
        DeviceRegisterRequest.model_validate(
            {
                "pairing_code": "12345",
                "device_id": "dev-1",
                "device_name": "Test",
                "os": "darwin",
                "hostname": "host",
            }
        )

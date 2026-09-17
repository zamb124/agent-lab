import pytest

from core.clients.guest_runtime_client import reraise_farm_error
from core.clients.service_client import ServiceClientError
from core.guest_runtime.models import GuestRuntimeUnavailableError


def test_connect_error_is_unavailable() -> None:
    exc = ServiceClientError("Ошибка запроса к guest_runtime: All connection attempts failed")
    assert exc.status_code is None
    with pytest.raises(GuestRuntimeUnavailableError, match="unreachable"):
        reraise_farm_error(exc)

"""Sync DB repository tests: под нагрузкой -n10 операции с БД/S3 дольше глобальных 5s."""

import pytest

pytestmark = pytest.mark.timeout(30)

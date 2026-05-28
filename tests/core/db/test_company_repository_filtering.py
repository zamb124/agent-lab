from __future__ import annotations

import pytest

from core.db.repositories.company_repository import CompanyRepository
from core.models.identity_models import Company


class _FakeStorage:
    async def get_all_by_prefix_and_table(self, prefix: str, table_name: str, limit: int, offset: int):
        assert prefix == "company:"
        assert table_name == "storage"
        return {
            "company:smr": Company(company_id="smr", name="SMR").model_dump_json(),
            "company:smr:embed_config:embed_a9c63630203b4f1f": '{"name":"Test","theme":"dark"}',
        }


@pytest.mark.asyncio
async def test_company_repository_list_skips_nested_company_prefix_entities() -> None:
    repo = CompanyRepository(storage=_FakeStorage())  # pyright: ignore[reportArgumentType]

    companies = await repo.list(limit=100, offset=0)

    assert len(companies) == 1
    assert companies[0].company_id == "smr"

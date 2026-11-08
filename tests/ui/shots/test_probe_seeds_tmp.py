import json

import pytest


@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_dump_seeds(marketing_seeded) -> None:
    print("\nSEEDS:", json.dumps(marketing_seeded, ensure_ascii=False, default=str))

"""REST-тесты Stock API: те же `op_*`, что и WS-команды (REST-зеркало).

`stock_client` — владелец `system`; `stock_client_company2` — чужая компания.
`stock_init` инициализирует `system` через DI до HTTP-вызовов.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.fixtures.stock import API_PREFIX

_WAREHOUSES = f"{API_PREFIX}/warehouses"
_PRODUCTS = f"{API_PREFIX}/products"
_LOCATIONS = f"{API_PREFIX}/locations"
_TRANSFERS = f"{API_PREFIX}/transfers"
_QUANTS = f"{API_PREFIX}/quants"
_UOMS = f"{API_PREFIX}/uoms"
_OPTYPES = f"{API_PREFIX}/operation-types"
_VALUATION = f"{API_PREFIX}/valuation"


async def _make_warehouse(client: AsyncClient, code: str) -> dict:
    resp = await client.post(
        _WAREHOUSES, json={"code": code, "name": f"WH {code}"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_product(
    client: AsyncClient, sku: str, *, valuation: str = "fifo"
) -> dict:
    uoms = (await client.get(_UOMS)).json()["items"]
    uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")
    resp = await client.post(
        _PRODUCTS,
        json={
            "name": f"Widget {sku}",
            "sku": sku,
            "uom_id": uom_id,
            "valuation_method": valuation,
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _op_type_id(
    client: AsyncClient, warehouse_id: str, code: str
) -> str:
    resp = await client.get(_OPTYPES, params={"warehouse_id": warehouse_id})
    assert resp.status_code == 200, resp.text
    return next(
        op["operation_type_id"]
        for op in resp.json()["items"]
        if op["code"] == code
    )


class TestWarehouseApi:
    async def test_create_list_get_warehouse(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        code = f"A{unique_id[:6]}"
        created = await _make_warehouse(stock_client, code)
        assert created["code"] == code
        listed = (await stock_client.get(_WAREHOUSES)).json()
        assert any(w["warehouse_id"] == created["warehouse_id"] for w in listed["items"])
        got = (
            await stock_client.get(f"{_WAREHOUSES}/{created['warehouse_id']}")
        ).json()
        assert got["stock_location_id"]

    async def test_warehouse_code_conflict(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        code = f"D{unique_id[:6]}"
        _ = await _make_warehouse(stock_client, code)
        resp = await stock_client.post(
            _WAREHOUSES, json={"code": code, "name": "Dup"}
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "warehouse_code_conflict"


class TestLocationsApi:
    async def test_create_and_list_locations(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"L{unique_id[:6]}")
        resp = await stock_client.post(
            _LOCATIONS,
            json={
                "warehouse_id": warehouse["warehouse_id"],
                "parent_id": warehouse["stock_location_id"],
                "name": "Zone A",
                "usage": "internal",
            },
        )
        assert resp.status_code == 200, resp.text
        listed = (
            await stock_client.get(
                _LOCATIONS, params={"warehouse_id": warehouse["warehouse_id"]}
            )
        ).json()
        names = {loc["name"] for loc in listed["items"]}
        assert "Zone A" in names


class TestProductsApi:
    async def test_product_crud_and_barcode(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        sku = f"P-{unique_id[:8]}"
        product = await _make_product(stock_client, sku)
        got = (await stock_client.get(f"{_PRODUCTS}/{product['product_id']}")).json()
        assert got["product"]["sku"] == sku
        listed = (await stock_client.get(_PRODUCTS)).json()
        assert any(
            p["product"]["product_id"] == product["product_id"]
            for p in listed["items"]
        )
        # barcode resolve → product
        resp = await stock_client.post(
            f"{API_PREFIX}/lots",
            json={
                "product_id": product["product_id"],
                "name": f"LOT-{unique_id[:6]}",
                "barcode": "48151623",
            },
        )
        assert resp.status_code == 200, resp.text
        resolved = (await stock_client.get(f"{API_PREFIX}/barcode/48151623")).json()
        assert resolved["entity_type"] == "lot"


class TestTransfersApi:
    async def test_full_transfer_lifecycle_over_rest(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"T{unique_id[:6]}")
        product = await _make_product(stock_client, f"T-{unique_id[:8]}")
        op_in = await _op_type_id(
            stock_client, warehouse["warehouse_id"], "incoming"
        )
        uoms = (await stock_client.get(_UOMS)).json()["items"]
        uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")
        resp = await stock_client.post(
            _TRANSFERS,
            json={
                "warehouse_id": warehouse["warehouse_id"],
                "operation_type_id": op_in,
                "moves": [
                    {
                        "product_id": product["product_id"],
                        "product_qty": "7",
                        "uom_id": uom_id,
                        "unit_price": "11",
                    }
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        transfer = resp.json()
        assert transfer["state"] == "draft"
        tid = transfer["transfer_id"]
        for step in ("confirm", "assign", "validate"):
            resp = await stock_client.post(f"{_TRANSFERS}/{tid}/{step}")
            assert resp.status_code == 200, f"{step}: {resp.text}"
        done = (await stock_client.get(f"{_TRANSFERS}/{tid}")).json()
        assert done["transfer"]["state"] == "done"
        # Остаток появился, слой INBOUND записан.
        quants = (
            await stock_client.get(
                _QUANTS, params={"product_id": product["product_id"]}
            )
        ).json()
        assert quants["items"][0]["quantity"] == "7"
        layers = (
            await stock_client.get(
                f"{_VALUATION}/layers",
                params={"product_id": product["product_id"]},
            )
        ).json()
        assert layers["items"][0]["entry_kind"] == "inbound"
        assert layers["items"][0]["unit_cost"] == "11"
        # Пульс видит перевод.
        pulse = (
            await stock_client.get(
                f"{_WAREHOUSES}/{warehouse['warehouse_id']}/pulse"
            )
        ).json()
        assert any(t["transfer_id"] == tid for t in pulse["transfers"])


class TestIsolationApi:
    async def test_company2_sees_no_system_data(
        self,
        stock_client: AsyncClient,
        stock_client_company2: AsyncClient,
        stock_init,
        unique_id: str,
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"I{unique_id[:6]}")
        wid = warehouse["warehouse_id"]
        resp = await stock_client_company2.get(f"{_WAREHOUSES}/{wid}")
        assert resp.status_code in {403, 404}
        listed = (await stock_client_company2.get(_WAREHOUSES)).json()
        assert all(w["warehouse_id"] != wid for w in listed["items"])
        resp = await stock_client_company2.post(
            _WAREHOUSES, json={"code": "XX", "name": "nope"}
        )
        assert resp.status_code == 403

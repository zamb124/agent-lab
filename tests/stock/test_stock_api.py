"""REST-тесты Stock API: те же `op_*`, что и WS-команды (REST-зеркало).

`stock_client` — владелец `system`; `stock_client_company2` — чужая компания.
`stock_init` инициализирует `system` через DI до HTTP-вызовов.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.stock import API_PREFIX

_WAREHOUSES = f"{API_PREFIX}/warehouses"
_PRODUCTS = f"{API_PREFIX}/products"
_LOCATIONS = f"{API_PREFIX}/locations"
_TRANSFERS = f"{API_PREFIX}/transfers"
_QUANTS = f"{API_PREFIX}/quants"
_UOMS = f"{API_PREFIX}/uoms"
_OPTYPES = f"{API_PREFIX}/operation-types"
_VALUATION = f"{API_PREFIX}/valuation"


async def _make_warehouse(client: AsyncClient, code: str) -> dict[str, Any]:
    resp = await client.post(_WAREHOUSES, json={"code": code, "name": f"WH {code}"})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_product(
    client: AsyncClient, sku: str, *, valuation: str = "fifo"
) -> dict[str, Any]:
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


async def _op_type_id(client: AsyncClient, warehouse_id: str, code: str) -> str:
    resp = await client.get(_OPTYPES, params={"warehouse_id": warehouse_id})
    assert resp.status_code == 200, resp.text
    return next(op["operation_type_id"] for op in resp.json()["items"] if op["code"] == code)


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
        got = (await stock_client.get(f"{_WAREHOUSES}/{created['warehouse_id']}")).json()
        assert got["stock_location_id"]

    async def test_warehouse_code_conflict(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        code = f"D{unique_id[:6]}"
        _ = await _make_warehouse(stock_client, code)
        resp = await stock_client.post(_WAREHOUSES, json={"code": code, "name": "Dup"})
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
                "parent_id": warehouse["view_location_id"],
                "name": "Zone A",
                "usage": "view",
            },
        )
        assert resp.status_code == 200, resp.text
        listed = (
            await stock_client.get(_LOCATIONS, params={"warehouse_id": warehouse["warehouse_id"]})
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
        assert got["sku"] == sku
        listed = (await stock_client.get(_PRODUCTS)).json()
        assert any(p["product_id"] == product["product_id"] for p in listed["items"])
        # barcode resolve → product
        barcode = f"9{int(unique_id[:12], 16):012d}"[-13:]
        resp = await stock_client.post(
            f"{API_PREFIX}/lots",
            json={
                "product_id": product["product_id"],
                "name": f"LOT-{unique_id[:6]}",
                "barcode": barcode,
            },
        )
        assert resp.status_code == 200, resp.text
        resolved = (await stock_client.get(f"{API_PREFIX}/barcode/{barcode}")).json()
        assert resolved["entity_type"] == "lot"


class TestTransfersApi:
    async def test_full_transfer_lifecycle_over_rest(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"T{unique_id[:6]}")
        product = await _make_product(stock_client, f"T-{unique_id[:8]}")
        op_in = await _op_type_id(stock_client, warehouse["warehouse_id"], "incoming")
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
            resp = await stock_client.post(
                f"{_TRANSFERS}/{tid}/{step}",
                json={"transfer_id": tid} if step == "validate" else None,
            )
            assert resp.status_code == 200, f"{step}: {resp.text}"
        done = (await stock_client.get(f"{_TRANSFERS}/{tid}")).json()
        assert done["transfer"]["state"] == "done"
        # Остаток появился, слой INBOUND записан.
        quants = (
            await stock_client.get(_QUANTS, params={"product_id": product["product_id"]})
        ).json()
        assert Decimal(quants["items"][0]["quantity"]) == 7
        layers = (
            await stock_client.get(
                f"{_VALUATION}/layers",
                params={"product_id": product["product_id"]},
            )
        ).json()
        assert layers["items"][0]["entry_kind"] == "inbound"
        assert Decimal(layers["items"][0]["unit_cost"]) == 11
        # Пульс видит перевод.
        pulse = (await stock_client.get(f"{_WAREHOUSES}/{warehouse['warehouse_id']}/pulse")).json()
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
        # company2 создаёт склад в своей компании — изоляция по company_id
        await stock_init.company_init_service.init_company_stock(company_id="company2")
        created = await stock_client_company2.post(
            _WAREHOUSES, json={"code": f"X{unique_id[:6]}", "name": "C2 WH"}
        )
        assert created.status_code == 200, created.text
        c2_wid = created.json()["warehouse_id"]
        resp = await stock_client.get(f"{_WAREHOUSES}/{c2_wid}")
        assert resp.status_code in {403, 404}


class TestErrorEnvelope:
    """Граничные коды ошибок REST-зеркала: конверт и status."""

    async def test_path_id_mismatch(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        """Path id ≠ body id → 400 + path_id_mismatch (защита от
        «адрес одной записи, тело другой»)."""
        _ = stock_init
        product = await _make_product(stock_client, f"PM-{unique_id}")
        resp = await stock_client.patch(
            f"{_PRODUCTS}/{product['product_id']}",
            json={"product_id": f"prod_other_{unique_id}"},
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "path_id_mismatch"

    async def test_putaway_rule_not_found(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        ghost = f"rule_ghost_{unique_id}"
        resp = await stock_client.patch(
            f"{API_PREFIX}/putaway-rules/{ghost}",
            json={"rule_id": ghost, "is_active": False},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "putaway_rule_not_found"

    async def test_reorder_rule_not_found(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        ghost = f"rule_ghost_{unique_id}"
        resp = await stock_client.patch(
            f"{API_PREFIX}/reorder-rules/{ghost}/active",
            json={"rule_id": ghost, "is_active": False},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "reorder_rule_not_found"


async def _done_inbound(
    client: AsyncClient, warehouse: dict[str, Any], product: dict[str, Any]
) -> dict[str, Any]:
    """Проводит приход единицы товара до состояния done."""
    op_in = await _op_type_id(client, warehouse["warehouse_id"], "incoming")
    uoms = (await client.get(_UOMS)).json()["items"]
    uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")
    resp = await client.post(
        _TRANSFERS,
        json={
            "warehouse_id": warehouse["warehouse_id"],
            "operation_type_id": op_in,
            "moves": [
                {
                    "product_id": product["product_id"],
                    "product_qty": "1",
                    "uom_id": uom_id,
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    tid = resp.json()["transfer_id"]
    for step in ("confirm", "assign", "validate"):
        resp = await client.post(
            f"{_TRANSFERS}/{tid}/{step}",
            json={"transfer_id": tid} if step == "validate" else None,
        )
        assert resp.status_code == 200, f"{step}: {resp.text}"
    return resp.json()


class TestMovesJournalApi:
    """`GET /moves` — журнал движений с keyset-пагинацией."""

    async def test_moves_list_filters_and_cursor(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"MJ{unique_id[:5]}")
        wid = warehouse["warehouse_id"]
        product = await _make_product(stock_client, f"MJ-{unique_id[:8]}")
        await _done_inbound(stock_client, warehouse, product)
        await _done_inbound(stock_client, warehouse, product)

        # Все done-движения склада — обе приходные проводки.
        moves = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={"warehouse_id": wid, "state": "done"},
            )
        ).json()
        mine = [
            m for m in moves["items"] if m["product_id"] == product["product_id"]
        ]
        assert len(mine) >= 2
        assert all(m["state"] == "done" for m in mine)

        # Фильтр по продукту и по ячейке-приёмнику.
        dest = mine[0]["location_dest_id"]
        by_product = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={"warehouse_id": wid, "product_id": product["product_id"]},
            )
        ).json()
        assert all(
            m["product_id"] == product["product_id"] for m in by_product["items"]
        )
        by_location = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={"warehouse_id": wid, "location_id": dest},
            )
        ).json()
        assert any(
            m["move_id"] == mine[0]["move_id"] for m in by_location["items"]
        )

        # Keyset: вторая страница не повторяет первую.
        page1 = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={"warehouse_id": wid, "limit": 1},
            )
        ).json()
        assert page1["has_more"] is True
        page2 = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={
                    "warehouse_id": wid,
                    "limit": 1,
                    "cursor": page1["next_cursor"],
                },
            )
        ).json()
        assert page1["items"][0]["move_id"] != page2["items"][0]["move_id"]

        # Несуществующий state — не done, журнал их не видит.
        none_done = (
            await stock_client.get(
                f"{API_PREFIX}/moves",
                params={"warehouse_id": wid, "state": "cancel"},
            )
        ).json()
        assert all(
            m["product_id"] != product["product_id"] for m in none_done["items"]
        )


class TestQuantsFiltersApi:
    """`GET /quants` — фильтры warehouse_id и subtree_location_id."""

    async def test_quants_warehouse_and_subtree(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"QF{unique_id[:5]}")
        wid = warehouse["warehouse_id"]
        product = await _make_product(stock_client, f"QF-{unique_id[:8]}")
        await _done_inbound(stock_client, warehouse, product)

        quant = (
            await stock_client.get(
                _QUANTS, params={"product_id": product["product_id"]}
            )
        ).json()["items"][0]
        assert quant["warehouse_id"] == wid

        by_wh = (
            await stock_client.get(
                _QUANTS,
                params={"warehouse_id": wid, "product_id": product["product_id"]},
            )
        ).json()
        assert any(q["quant_id"] == quant["quant_id"] for q in by_wh["items"])

        # Поддерево корня склада содержит остаток; чужая зона — нет.
        root = warehouse["view_location_id"]
        by_root = (
            await stock_client.get(
                _QUANTS,
                params={
                    "warehouse_id": wid,
                    "subtree_location_id": root,
                    "product_id": product["product_id"],
                },
            )
        ).json()
        assert any(q["quant_id"] == quant["quant_id"] for q in by_root["items"])

        zone = (
            await stock_client.post(
                _LOCATIONS,
                json={
                    "warehouse_id": wid,
                    "parent_id": root,
                    "name": "Empty Zone",
                    "usage": "view",
                },
            )
        ).json()
        by_empty = (
            await stock_client.get(
                _QUANTS,
                params={
                    "warehouse_id": wid,
                    "subtree_location_id": zone["location_id"],
                },
            )
        ).json()
        assert by_empty["items"] == []
        assert by_empty["total"] == 0


class TestCountDueApi:
    """`GET /locations/count-due` — ячейки с просроченным пересчётом."""

    async def test_new_bin_is_due(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"CD{unique_id[:5]}")
        wid = warehouse["warehouse_id"]
        zone = (
            await stock_client.post(
                _LOCATIONS,
                json={
                    "warehouse_id": wid,
                    "parent_id": warehouse["view_location_id"],
                    "name": "Zone CD",
                    "usage": "view",
                },
            )
        ).json()
        bin_loc = (
            await stock_client.post(
                _LOCATIONS,
                json={
                    "warehouse_id": wid,
                    "parent_id": zone["location_id"],
                    "name": "Bin CD-1",
                    "usage": "bin",
                },
            )
        ).json()
        due = (
            await stock_client.get(
                f"{API_PREFIX}/locations/count-due",
                params={"warehouse_id": wid},
            )
        ).json()
        assert any(
            loc["location_id"] == bin_loc["location_id"]
            for loc in due["items"]
        )
        # Зона (usage=view) — не ячейка, в список не входит.
        assert all(
            loc["location_id"] != zone["location_id"] for loc in due["items"]
        )


class TestTopologyUpdateApi:
    """PATCH-зеркала update-ops справочников топологии."""

    async def test_storage_type_update(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"ST{unique_id[:5]}")
        created = (
            await stock_client.post(
                f"{API_PREFIX}/storage-types",
                json={"warehouse_id": warehouse["warehouse_id"], "name": "Rack"},
            )
        ).json()
        sid = created["storage_type_id"]
        resp = await stock_client.patch(
            f"{API_PREFIX}/storage-types/{sid}",
            json={
                "storage_type_id": sid,
                "name": "Rack heavy",
                "cycle_count_days": 7,
                "allow_mixed_lots": False,
            },
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["name"] == "Rack heavy"
        assert updated["cycle_count_days"] == 7
        assert updated["allow_mixed_lots"] is False
        # Не переданные поля не обнулились.
        assert updated["putaway_strategies"] == created["putaway_strategies"]

    async def test_storage_type_update_not_found(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        ghost = f"sst_ghost_{unique_id}"
        resp = await stock_client.patch(
            f"{API_PREFIX}/storage-types/{ghost}",
            json={"storage_type_id": ghost, "name": "X"},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "storage_type_not_found"

    async def test_container_type_update(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"CT{unique_id[:5]}")
        created = (
            await stock_client.post(
                f"{API_PREFIX}/container-types",
                json={
                    "warehouse_id": warehouse["warehouse_id"],
                    "name": "Pallet",
                    "kind": "pallet",
                },
            )
        ).json()
        cid = created["container_type_id"]
        resp = await stock_client.patch(
            f"{API_PREFIX}/container-types/{cid}",
            json={
                "container_type_id": cid,
                "name": "Euro pallet",
                "is_reusable": True,
                "max_weight": "1500",
            },
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["name"] == "Euro pallet"
        assert updated["is_reusable"] is True
        assert Decimal(updated["max_weight"]) == 1500
        assert updated["kind"] == "pallet"

    async def test_resource_type_and_resource_update(
        self, stock_client: AsyncClient, stock_init, unique_id: str
    ) -> None:
        _ = stock_init
        warehouse = await _make_warehouse(stock_client, f"RT{unique_id[:5]}")
        wid = warehouse["warehouse_id"]
        rtype = (
            await stock_client.post(
                f"{API_PREFIX}/resource-types",
                json={"warehouse_id": wid, "name": "Forklift"},
            )
        ).json()
        rtid = rtype["resource_type_id"]
        resp = await stock_client.patch(
            f"{API_PREFIX}/resource-types/{rtid}",
            json={
                "resource_type_id": rtid,
                "name": "Reach truck",
                "max_level": 5,
                "handles_loose": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Reach truck"
        assert resp.json()["max_level"] == 5
        assert resp.json()["handles_loose"] is False

        resource = (
            await stock_client.post(
                f"{API_PREFIX}/resources",
                json={
                    "warehouse_id": wid,
                    "resource_type_id": rtid,
                    "code": "FL-1",
                },
            )
        ).json()
        rid = resource["resource_id"]
        resp = await stock_client.patch(
            f"{API_PREFIX}/resources/{rid}",
            json={"resource_id": rid, "code": "FL-01"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == "FL-01"
        assert resp.json()["resource_type_id"] == rtid

"""HTTP client for flows datasource API on top of ServiceClient."""

from __future__ import annotations

from urllib.parse import quote

from core.clients.service_client import ServiceClient
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectionCreate,
    DatasourceConnectionPatch,
    DatasourceConnectorSpec,
    DatasourceConnectorUpsert,
    DatasourceExecuteResult,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceSqlRequest,
    DatasourceTestResult,
)
from core.pagination import OffsetPage
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_API = "/flows/api/v1"
_SERVICE = "flows"


class DatasourceClient:
    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def _object(self, value: JsonValue, label: str) -> JsonObject:
        return require_json_object(value, label)

    async def list_connectors(self) -> list[DatasourceConnectorSpec]:
        raw = await self._http.get(_SERVICE, f"{_API}/datasources/connectors")
        payload = self._object(raw, "DatasourceClient.list_connectors")
        if "items" not in payload:
            raise ValueError("DatasourceClient.list_connectors: items required")
        items = require_json_array(payload["items"], "DatasourceClient.list_connectors.items")
        return [
            DatasourceConnectorSpec.model_validate(
                self._object(item, f"DatasourceClient.list_connectors[{index}]")
            )
            for index, item in enumerate(items)
        ]

    async def upsert_connector(
        self, payload: DatasourceConnectorUpsert
    ) -> DatasourceConnectorSpec:
        raw = await self._http.put(
            _SERVICE,
            f"{_API}/datasources/connectors",
            json=require_json_object(
                payload.model_dump(mode="json"), "DatasourceClient.upsert_connector.body"
            ),
        )
        return DatasourceConnectorSpec.model_validate(
            self._object(raw, "DatasourceClient.upsert_connector")
        )

    async def list_connections(self) -> list[DatasourceConnection]:
        raw = await self._http.get(_SERVICE, f"{_API}/datasources")
        page = OffsetPage[DatasourceConnection].model_validate(raw)
        return page.items

    async def get_connection(self, datasource_id: str) -> DatasourceConnection:
        raw = await self._http.get(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}",
        )
        return DatasourceConnection.model_validate(
            self._object(raw, "DatasourceClient.get_connection")
        )

    async def create_connection(
        self, payload: DatasourceConnectionCreate
    ) -> DatasourceConnection:
        raw = await self._http.post(
            _SERVICE,
            f"{_API}/datasources",
            json=require_json_object(
                payload.model_dump(mode="json"), "DatasourceClient.create_connection.body"
            ),
        )
        return DatasourceConnection.model_validate(
            self._object(raw, "DatasourceClient.create_connection")
        )

    async def patch_connection(
        self, datasource_id: str, payload: DatasourceConnectionPatch
    ) -> DatasourceConnection:
        raw = await self._http.patch(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}",
            json=require_json_object(
                payload.model_dump(mode="json"), "DatasourceClient.patch_connection.body"
            ),
        )
        return DatasourceConnection.model_validate(
            self._object(raw, "DatasourceClient.patch_connection")
        )

    async def delete_connection(self, datasource_id: str) -> None:
        _ = await self._http.delete(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}",
        )

    async def test(self, datasource_id: str) -> DatasourceTestResult:
        raw = await self._http.post(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}/test",
            json={},
        )
        return DatasourceTestResult.model_validate(
            self._object(raw, "DatasourceClient.test")
        )

    async def introspect(self, datasource_id: str) -> DatasourceSchemaSnapshot:
        raw = await self._http.post(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}/introspect",
            json={},
        )
        return DatasourceSchemaSnapshot.model_validate(
            self._object(raw, "DatasourceClient.introspect")
        )

    async def query(
        self, datasource_id: str, sql: str, params: JsonObject
    ) -> DatasourceQueryResult:
        request = DatasourceSqlRequest(sql=sql, params=params)
        raw = await self._http.post(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}/query",
            json=require_json_object(
                request.model_dump(mode="json"), "DatasourceClient.query.body"
            ),
        )
        return DatasourceQueryResult.model_validate(
            self._object(raw, "DatasourceClient.query")
        )

    async def execute(
        self, datasource_id: str, sql: str, params: JsonObject
    ) -> DatasourceExecuteResult:
        request = DatasourceSqlRequest(sql=sql, params=params)
        raw = await self._http.post(
            _SERVICE,
            f"{_API}/datasources/{quote(datasource_id, safe='')}/execute",
            json=require_json_object(
                request.model_dump(mode="json"), "DatasourceClient.execute.body"
            ),
        )
        return DatasourceExecuteResult.model_validate(
            self._object(raw, "DatasourceClient.execute")
        )

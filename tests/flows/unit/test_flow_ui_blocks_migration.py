"""Ревизия 20260910_0035: DataTable становится блоком data_table."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from apps.flows.src.durable_execution.models import ExecutionStateDelta
from apps.flows.src.durable_execution.state_delta import apply_state_delta
from core.flow_ui.document import FlowUIDataTable, FlowUIDocument
from core.types import JsonObject, require_json_object

pytestmark = [pytest.mark.no_test_doubles]

MIGRATION_PATH = Path("migrations/flows/versions/20260910_0035_flow_ui_blocks.py")


def _load_migration() -> ModuleType:
    name = "_flow_ui_blocks_migration"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(name, MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load migration {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _surface_context(migration: ModuleType, flow_id: str) -> object:
    return migration._SurfaceContext(  # pyright: ignore[reportAny]
        flow_id=flow_id,
        components={},
        content={},
        policy={},
        used_ids=set(),
    )


def _empty_datatable() -> JsonObject:
    return {
        "kind": "leaf",
        "type": "DataTable",
        "bindings": {},
        "children": [],
        "properties": {"rows": [], "columns": [], "file_id": "", "table_name": ""},
        "component_id": "data-table",
    }


def test_empty_datatable_becomes_data_table_with_default_rows_path() -> None:
    migration = _load_migration()
    block = require_json_object(
        migration._leaf(_surface_context(migration, "react_flow_msx0vu12"), "data-table", _empty_datatable()),  # pyright: ignore[reportAny]
        "converted DataTable",
    )
    assert block == {
        "type": "data_table",
        "block_id": "data-table",
        "columns": [],
        "rows": "rows",
    }
    _ = FlowUIDataTable.model_validate(block)


def test_datatable_file_id_becomes_data_table_file_source() -> None:
    migration = _load_migration()
    component: JsonObject = {
        "type": "DataTable",
        "bindings": {},
        "properties": {"file_id": "{table_file}", "columns": []},
    }
    block = require_json_object(
        migration._leaf(_surface_context(migration, "flow_file_table"), "orders", component),  # pyright: ignore[reportAny]
        "converted DataTable file_id",
    )
    assert block == {
        "type": "data_table",
        "block_id": "orders",
        "columns": [],
        "file_id": "{table_file}",
    }
    _ = FlowUIDataTable.model_validate(block)


def test_convert_interface_keeps_empty_datatable_publishable() -> None:
    migration = _load_migration()
    converted = require_json_object(
        migration._convert_interface(  # pyright: ignore[reportAny]
        "react_flow_msx0vu12",
        {
            "template": {
                "template_id": "custom",
                "document": {
                    "active_page_id": "main",
                    "pages": {
                        "main": {
                            "page_id": "main",
                            "title": "Main",
                            "root_surface_id": "main",
                        }
                    },
                    "surfaces": {
                        "main": {
                            "root_component_id": "root",
                            "data_model": {"content": {}},
                            "components": {
                                "root": {
                                    "type": "PageShell",
                                    "children": ["data-table"],
                                },
                                "data-table": _empty_datatable(),
                            },
                        }
                    },
                },
            }
        },
        ),
        "converted interface",
    )
    document = FlowUIDocument.model_validate(converted)
    assert document.start_page_id == "main"
    assert document.pages[0].blocks[0].model_dump(mode="json") == {
        "type": "data_table",
        "block_id": "data-table",
        "visible_when": None,
        "span": 12,
        "align": "start",
        "valign": "start",
        "rows": "rows",
        "file_id": "",
        "columns": [],
        "row_action": None,
    }


def test_strip_delta_drops_onlyoffice_binding_id_from_files() -> None:
    migration = _load_migration()
    stripped = migration._strip_delta(  # pyright: ignore[reportAny]
        {
            "fields_set": {
                "session_id": "public_search:ctx",
                "task_id": "task-public-search",
                "context_id": "ctx",
                "user_id": "user-public-search",
                "files": [
                    {
                        "file_id": "file_485d3c279c6b",
                        "original_name": "contract.docx",
                        "url": "https://files.test/contract.docx",
                        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "file_size": 12,
                        "capabilities": {
                            "document": {
                                "kind": "onlyoffice",
                                "title": "contract.docx",
                                "file_id": "file_485d3c279c6b",
                                "editable": True,
                                "namespace": "default",
                                "binding_id": "22ed768fd38749ae8674c24f6207074d",
                                "catalog_id": "2c0bff6298da4ac89fc4e9199006b71f",
                                "editor_url": "/documents/embed/edit/22ed768fd38749ae8674c24f6207074d?namespace=default",
                                "document_type": "word",
                            }
                        },
                    }
                ],
            }
        }
    )
    if not isinstance(stripped, ExecutionStateDelta):
        raise TypeError("migration _strip_delta must return ExecutionStateDelta")
    state = apply_state_delta(None, stripped)
    document = state.files[0].capabilities.document
    assert document is not None
    assert document.file_id == "file_485d3c279c6b"
    assert "binding_id" not in document.model_dump()

from core.capabilities.sandbox_libraries import (
    is_allowed_go_import,
    is_allowed_python_import,
    sandbox_builtins_for_language,
    sandbox_modules_for_language,
)


def test_python_import_allowlist_accepts_stdlib_and_data_libraries() -> None:
    assert is_allowed_python_import("csv")
    assert is_allowed_python_import("json")
    assert is_allowed_python_import("pathlib")
    assert is_allowed_python_import("urllib.parse")
    assert is_allowed_python_import("pandas")
    assert is_allowed_python_import("hmac")
    assert is_allowed_python_import("tomllib")
    assert is_allowed_python_import("wiki", extra_roots=frozenset({"wiki"}))


def test_python_import_allowlist_rejects_net_fs_and_platform() -> None:
    assert is_allowed_python_import("urllib.request") is False
    assert is_allowed_python_import("requests") is False
    assert is_allowed_python_import("httpx") is False
    assert is_allowed_python_import("os") is False
    assert is_allowed_python_import("apps.flows.src.runtime.exceptions") is False
    assert is_allowed_python_import("core.capabilities") is False


def test_sandbox_modules_include_familiar_libraries() -> None:
    python_modules = sandbox_modules_for_language("python")
    assert "csv" in python_modules
    assert "pandas" in python_modules
    assert "urllib.parse" in python_modules
    assert "hmac" in python_modules
    assert "secrets" in python_modules
    assert "zipfile" in python_modules
    assert "bs4" in python_modules
    assert "struct" in python_modules
    node_modules = sandbox_modules_for_language("javascript")
    assert "lodash" in node_modules
    assert "csv-parse/sync" in node_modules
    assert "uuid" in node_modules
    assert "date-fns" in node_modules
    go_modules = sandbox_modules_for_language("go")
    assert "encoding/json" in go_modules
    assert "encoding/xml" in go_modules
    csharp_usings = sandbox_modules_for_language("csharp")
    assert "System.Text.Json" in csharp_usings
    assert "System.Xml.Linq" in csharp_usings
    assert "System.Collections.Immutable" in csharp_usings
    assert "FlowInterrupt" in sandbox_builtins_for_language("python")
    python_builtins = sandbox_builtins_for_language("python")
    assert "frozenset" in python_builtins
    assert "hash" in python_builtins
    assert "slice" in python_builtins
    js_builtins = sandbox_builtins_for_language("javascript")
    assert "JSON" in js_builtins
    assert "ArrayBuffer" in js_builtins
    assert "Uint8Array" in js_builtins
    assert "Intl" in js_builtins
    assert "crypto" in js_builtins
    assert "BigInt" in js_builtins
    assert "structuredClone" in js_builtins
    assert "fetch" not in js_builtins


def test_go_import_allowlist_matches_runtime() -> None:
    assert is_allowed_go_import("encoding/json") is True
    assert is_allowed_go_import("encoding/csv") is True
    assert is_allowed_go_import("encoding/xml") is True
    assert is_allowed_go_import("encoding/binary") is True
    assert is_allowed_go_import("net/http") is False
    assert is_allowed_go_import("os") is False

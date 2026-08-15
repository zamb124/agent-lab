import pytest

from core.capabilities.lsp_workspace import build_lsp_workspace
from core.capabilities.models import (
    CAPABILITY_LANGUAGES,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityNamespaceDocumentation,
    CapabilitySchemaFieldDocumentation,
    CapabilitySdkMethodDocumentation,
    CodeLspSessionCreateRequest,
)
from core.capabilities.sandbox_libraries import PYTHON_ALLOWED_IMPORT_ROOTS
from tests.capabilities.capability_language_helpers import fetch_capability_documentation
from tests.capabilities.code_lsp_helpers import session_request


def _documentation(language: CapabilityLanguage, *, method: str) -> CapabilityDocumentation:
    crm_method = "create_entity" if method == "create" else "CreateEntity"
    files_method = method
    return CapabilityDocumentation(
        version="test",
        markdown="# sdk",
        language=language,
        namespaces=[
            CapabilityNamespaceDocumentation(
                name="files",
                type="namespace",
                methods=[files_method],
                capability_names=["files.create"],
            ),
            CapabilityNamespaceDocumentation(
                name="crm",
                type="namespace",
                methods=[crm_method],
                capability_names=["crm.create_entity"],
            ),
        ],
        capabilities=[
            CapabilitySdkMethodDocumentation(
                capability_name="files.create",
                namespace="files",
                method=files_method,
                label="files.create",
                title="create",
                description="Create a file",
                signature="await files.create(content: string)",
                insert_text="await files.create(content='x')",
                documentation="Create a file",
                input_fields=[
                    CapabilitySchemaFieldDocumentation(
                        name="content",
                        path="content",
                        type="string",
                        required=True,
                    )
                ],
            ),
            CapabilitySdkMethodDocumentation(
                capability_name="crm.create_entity",
                namespace="crm",
                method=crm_method,
                label="crm.create_entity",
                title="create_entity",
                description="Create CRM entity",
                signature="await crm.create_entity(entity_type: string)",
                insert_text="await crm.create_entity(entity_type='person')",
                documentation="Create CRM entity",
                input_fields=[
                    CapabilitySchemaFieldDocumentation(
                        name="entity_type",
                        path="entity_type",
                        type="string",
                        required=True,
                    )
                ],
            ),
        ],
    )


def _files(language: CapabilityLanguage, *, method: str = "create") -> dict[str, str]:
    workspace = build_lsp_workspace(
        _documentation(language, method=method),
        CodeLspSessionCreateRequest(
            language=language,
            source="pass" if language == "python" else "// source",
            parameters_schema={
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
            variable_keys=["api_token"],
        ),
    )
    assert workspace.document_path in {item.path for item in workspace.files}
    return {item.path: item.content for item in workspace.files}


def test_python_workspace_contains_sdk_and_runtime_stubs() -> None:
    files = _files("python")
    runtime = files["typings/runtime.pyi"]
    files_stub = files["typings/files.pyi"]
    crm_stub = files["typings/crm.pyi"]
    builtins_stub = files["typings/__builtins__.pyi"]
    assert "file_id: str" in runtime
    assert "api_token: Any" in runtime
    assert "async def create(self, *, content: str)" in files_stub
    assert "async def create(*, content: str)" in files_stub
    assert "async def create_entity(self, *, entity_type: str)" in crm_stub
    assert "args: Args" in builtins_stub
    assert "files: FilesNamespace" in builtins_stub
    assert "main.py" in files


def test_python_workspace_does_not_hand_curate_stdlib_members() -> None:
    files = _files("python")
    assert "json" in PYTHON_ALLOWED_IMPORT_ROOTS
    assert "typings/json.pyi" not in files
    assert "typings/files.pyi" in files


def test_javascript_workspace_declares_sdk_and_args() -> None:
    files = _files("javascript")
    sdk = files["types/sdk.d.ts"]
    assert "declare const files: FilesNamespace" in sdk
    assert "create(kwargs: { content: string })" in sdk
    assert "file_id: string" in sdk
    assert "declare const args: Args" in sdk
    assert "tsconfig.json" in files


def test_go_workspace_uses_pascal_case_methods() -> None:
    files = _files("go", method="Create")
    sdk = files["sdk.go"]
    assert "func (filesNamespace) Create(kwargs kwargs) (any, error)" in sdk
    assert "func (crmNamespace) CreateEntity(kwargs kwargs) (any, error)" in sdk
    assert "var files filesNamespace" in sdk
    assert files["main.go"].startswith("package main")


def test_csharp_workspace_wraps_user_code_and_exposes_sdk() -> None:
    files = _files("csharp", method="Create")
    sdk = files["Sdk.cs"]
    user = files["UserCode.cs"]
    assert "public static class files" in sdk
    assert "public static Task<object?> Create(Dictionary<string, object?> kwargs)" in sdk
    assert "UserCode.sln" in files
    assert "public sealed partial class UserCode" in user


def _sdk_stub_blob(files: dict[str, str], language: CapabilityLanguage) -> str:
    if language == "python":
        return "\n".join(
            content
            for path, content in sorted(files.items())
            if path.startswith("typings/") and path.endswith(".pyi")
        )
    if language in {"javascript", "typescript"}:
        return files["types/sdk.d.ts"]
    if language == "go":
        return files["sdk.go"]
    return files["Sdk.cs"]


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_live_gateway_documentation_methods_appear_in_stubs(
    sandbox_services: dict[str, str],
    unique_id: str,
) -> None:
    variable_key = f"var_{unique_id}"
    for language in CAPABILITY_LANGUAGES:
        documentation = await fetch_capability_documentation(sandbox_services, language)
        request = session_request(language, unique_id)
        workspace = build_lsp_workspace(documentation, request)
        files = {item.path: item.content for item in workspace.files}
        stub = _sdk_stub_blob(files, language)
        assert documentation.capabilities, f"{language}: empty live documentation"
        for method in documentation.capabilities:
            assert method.method in stub, (
                f"{language}: SDK method {method.capability_name}.{method.method} missing from stubs"
            )
        if language == "python":
            runtime = files["typings/runtime.pyi"]
            assert "file_id: str" in runtime
            assert f"{variable_key}: Any" in runtime
        elif language in {"javascript", "typescript"}:
            sdk = files["types/sdk.d.ts"]
            assert "file_id: string" in sdk
            assert f"{variable_key}?: unknown" in sdk

"""Генерация language-native virtual workspace для code_node language servers.

Источник правды — CapabilityDocumentation + sandbox allowlist + per-session
args/state schema. Редактор не читает параллельный JSON-каталог имён.
"""

from __future__ import annotations

import json
import keyword
import re
from typing import Final

from core.capabilities.models import (
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilitySchemaFieldDocumentation,
    CapabilitySdkMethodDocumentation,
    CodeLspSessionCreateRequest,
    LspWorkspace,
    LspWorkspaceFile,
)
from core.types import JsonObject, require_json_object

_IDENT_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CSHARP_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "abstract",
        "as",
        "base",
        "bool",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "checked",
        "class",
        "const",
        "continue",
        "decimal",
        "default",
        "delegate",
        "do",
        "double",
        "else",
        "enum",
        "event",
        "explicit",
        "extern",
        "false",
        "finally",
        "fixed",
        "float",
        "for",
        "foreach",
        "goto",
        "if",
        "implicit",
        "in",
        "int",
        "interface",
        "internal",
        "is",
        "lock",
        "long",
        "namespace",
        "new",
        "null",
        "object",
        "operator",
        "out",
        "override",
        "params",
        "private",
        "protected",
        "public",
        "readonly",
        "ref",
        "return",
        "sbyte",
        "sealed",
        "short",
        "sizeof",
        "stackalloc",
        "static",
        "string",
        "struct",
        "switch",
        "this",
        "throw",
        "true",
        "try",
        "typeof",
        "uint",
        "ulong",
        "unchecked",
        "unsafe",
        "ushort",
        "using",
        "virtual",
        "void",
        "volatile",
        "while",
    }
)

RUNTIME_STATE_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("content", "str | None"),
    ("response", "str | None"),
    ("result", "Any"),
    ("validation", "dict[str, Any] | None"),
    ("messages", "list[Any]"),
    ("variables", "dict[str, Any]"),
    ("files", "list[Any]"),
    ("triggers", "dict[str, Any]"),
    ("tool_results", "dict[str, Any]"),
    ("node_history", "dict[str, Any]"),
    ("current_nodes", "list[str]"),
    ("branch_id", "str"),
    ("session_id", "str"),
    ("flow_config_version", "str | None"),
)

_LANGUAGE_IDS: Final[dict[CapabilityLanguage, str]] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "csharp": "csharp",
}

_DOCUMENT_PATHS: Final[dict[CapabilityLanguage, str]] = {
    "python": "main.py",
    "javascript": "main.js",
    "typescript": "main.ts",
    "go": "main.go",
    "csharp": "UserCode.cs",
}


def build_lsp_workspace(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
) -> LspWorkspace:
    language = request.language
    document_path = _DOCUMENT_PATHS[language]
    files: list[LspWorkspaceFile]
    if language == "python":
        files = _python_files(documentation, request, document_path)
    elif language in {"javascript", "typescript"}:
        files = _javascript_files(documentation, request, document_path)
    elif language == "go":
        files = _go_files(documentation, request, document_path)
    else:
        files = _csharp_files(documentation, request, document_path)
    return LspWorkspace(
        language=language,
        language_id=_LANGUAGE_IDS[language],
        document_path=document_path,
        files=files,
    )


def _is_ident(name: str) -> bool:
    return bool(_IDENT_RE.fullmatch(name)) and not keyword.iskeyword(name)


def _python_type(schema_type: str) -> str:
    mapping = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "dict[str, Any]",
        "array": "list[Any]",
        "null": "None",
        "any": "Any",
    }
    if schema_type in mapping:
        return mapping[schema_type]
    if schema_type.startswith("array<"):
        inner = schema_type.removeprefix("array<").removesuffix(">")
        return f"list[{_python_type(inner)}]"
    if " | " in schema_type:
        parts = [_python_type(part.strip()) for part in schema_type.split("|")]
        return " | ".join(parts)
    if _is_ident(schema_type):
        return "Any"
    return "Any"


def _ts_type(schema_type: str) -> str:
    mapping = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "object": "Record<string, unknown>",
        "array": "unknown[]",
        "null": "null",
        "any": "unknown",
    }
    if schema_type in mapping:
        return mapping[schema_type]
    if schema_type.startswith("array<"):
        inner = schema_type.removeprefix("array<").removesuffix(">")
        return f"Array<{_ts_type(inner)}>"
    if " | " in schema_type:
        return " | ".join(_ts_type(part.strip()) for part in schema_type.split("|"))
    return "unknown"


def _top_level_fields(
    fields: list[CapabilitySchemaFieldDocumentation],
) -> list[CapabilitySchemaFieldDocumentation]:
    return [field for field in fields if "." not in field.path and "[]" not in field.path]


def _schema_properties(schema: JsonObject) -> dict[str, JsonObject]:
    if "properties" not in schema:
        return {}
    raw = require_json_object(schema["properties"], "parameters_schema.properties")
    out: dict[str, JsonObject] = {}
    for name, value in raw.items():
        out[name] = require_json_object(value, f"parameters_schema.properties.{name}")
    return out


def _schema_required(schema: JsonObject) -> set[str]:
    raw = schema.get("required")
    if not isinstance(raw, list):
        return set()
    return {item for item in raw if isinstance(item, str)}


def _schema_declared_type(prop: JsonObject) -> str:
    raw_type = prop.get("type")
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw_type, list):
        return " | ".join(str(item) for item in raw_type if isinstance(item, str))
    return "any"


def _python_kwonly(fields: list[CapabilitySchemaFieldDocumentation]) -> str:
    parts: list[str] = []
    for field in fields:
        if not _is_ident(field.name):
            continue
        py_type = _python_type(field.type)
        if field.required:
            parts.append(f"{field.name}: {py_type}")
        else:
            parts.append(f"{field.name}: {py_type} = ...")
    if not parts:
        return "*kwargs: Any"
    return "*, " + ", ".join(parts)


def _ts_kwargs(fields: list[CapabilitySchemaFieldDocumentation]) -> str:
    parts: list[str] = []
    for field in fields:
        if not _is_ident(field.name):
            continue
        optional = "" if field.required else "?"
        parts.append(f"{field.name}{optional}: {_ts_type(field.type)}")
    if not parts:
        return "kwargs?: Record<string, unknown>"
    return "kwargs: { " + "; ".join(parts) + " }"


def _escape_py_doc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _python_files(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
    document_path: str,
) -> list[LspWorkspaceFile]:
    files: list[LspWorkspaceFile] = [
        LspWorkspaceFile(path=document_path, content=request.source),
        LspWorkspaceFile(path="pyrightconfig.json", content=_pyrightconfig()),
        LspWorkspaceFile(
            path="typings/runtime.pyi",
            content=_python_runtime_stub(request),
        ),
        LspWorkspaceFile(
            path="typings/__builtins__.pyi",
            content=_python_builtins_stub(documentation),
        ),
    ]
    for namespace in documentation.namespaces:
        methods = [
            method
            for method in documentation.capabilities
            if method.namespace == namespace.name
        ]
        files.append(
            LspWorkspaceFile(
                path=f"typings/{namespace.name}.pyi",
                content=_python_namespace_module(namespace.name, methods),
            )
        )
    return files


def _pyrightconfig() -> str:
    return json.dumps(
        {
            "include": ["."],
            "stubPath": "typings",
            "pythonVersion": "3.14",
            "typeCheckingMode": "basic",
            "reportMissingImports": "error",
            "reportMissingModuleSource": "none",
        },
        indent=2,
    )


def _python_runtime_stub(request: CodeLspSessionCreateRequest) -> str:
    lines = [
        "from typing import Any, TypedDict",
        "",
        "class Args(TypedDict, total=False):",
    ]
    properties = _schema_properties(request.parameters_schema)
    required = _schema_required(request.parameters_schema)
    if not properties:
        lines.append("    pass")
    else:
        for name, prop in properties.items():
            if not _is_ident(name):
                continue
            py_type = _python_type(_schema_declared_type(prop))
            if name in required:
                lines.append(f"    {name}: {py_type}")
            else:
                lines.append(f"    {name}: {py_type}")
    lines.extend(["", "class Variables(TypedDict, total=False):"])
    variable_keys = [key for key in request.variable_keys if _is_ident(key)]
    if not variable_keys:
        lines.append("    pass")
    else:
        for key in variable_keys:
            lines.append(f"    {key}: Any")
    lines.extend(["", "class State:"])
    for name, py_type in RUNTIME_STATE_FIELDS:
        if name == "variables":
            lines.append("    variables: Variables")
        else:
            lines.append(f"    {name}: {py_type}")
    lines.extend(
        [
            "    def __getattr__(self, name: str) -> Any: ...",
            "    def __setattr__(self, name: str, value: Any) -> None: ...",
            "    def __getitem__(self, key: str) -> Any: ...",
            "    def __setitem__(self, key: str, value: Any) -> None: ...",
            "    def get(self, key: str, default: Any = None) -> Any: ...",
            "",
            "args: Args",
            "state: State",
            "variables: Variables",
            "",
        ]
    )
    return "\n".join(lines)


def _python_builtins_stub(documentation: CapabilityDocumentation) -> str:
    lines = [
        "from typing import Any",
        "from runtime import Args, State, Variables",
        "",
        "args: Args",
        "state: State",
        "variables: Variables",
        "",
        "class FlowInterrupt(Exception):",
        "    def __init__(self, *args: Any, question: str = ..., **kwargs: Any) -> None: ...",
        "",
    ]
    for namespace in documentation.namespaces:
        class_name = _namespace_class_name(namespace.name)
        lines.append(f"from {namespace.name} import {class_name}")
        lines.append(f"{namespace.name}: {class_name}")
    lines.append("")
    return "\n".join(lines)


def _namespace_class_name(namespace: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in namespace.split("_") if part) + "Namespace"


def _python_namespace_module(
    namespace: str,
    methods: list[CapabilitySdkMethodDocumentation],
) -> str:
    class_name = _namespace_class_name(namespace)
    lines = [
        "from typing import Any",
        "",
        f"class {class_name}:",
    ]
    if not methods:
        lines.append("    async def call(self, method: str, **kwargs: Any) -> Any: ...")
    for method in methods:
        fields = _top_level_fields(method.input_fields)
        signature = _python_kwonly(fields)
        doc = _escape_py_doc(method.description)
        lines.append(f"    async def {method.method}(self, {signature}) -> dict[str, Any]:")
        lines.append(f'        """{doc}"""')
        lines.append("        ...")
        lines.append("")
        lines.append(f"async def {method.method}({signature}) -> dict[str, Any]:")
        lines.append(f'    """{doc}"""')
        lines.append("    ...")
        lines.append("")
    return "\n".join(lines)


def _javascript_files(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
    document_path: str,
) -> list[LspWorkspaceFile]:
    return [
        LspWorkspaceFile(path=document_path, content=request.source),
        LspWorkspaceFile(path="tsconfig.json", content=_tsconfig(document_path)),
        LspWorkspaceFile(path="types/sdk.d.ts", content=_typescript_sdk(documentation, request)),
    ]


def _tsconfig(document_path: str) -> str:
    return json.dumps(
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "bundler",
                "lib": ["ES2022"],
                "strict": False,
                "noEmit": True,
                "allowJs": True,
                "checkJs": True,
                "skipLibCheck": True,
                "typeRoots": ["./types", "./node_modules/@types"],
            },
            "include": [document_path, "types/**/*.d.ts"],
        },
        indent=2,
    )


def _typescript_sdk(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
) -> str:
    lines = [
        "export {};",
        "",
        "type JsonObject = Record<string, unknown>;",
        "",
        "interface Args {",
    ]
    properties = _schema_properties(request.parameters_schema)
    required = _schema_required(request.parameters_schema)
    if not properties:
        lines.append("  [key: string]: unknown;")
    else:
        for name, prop in properties.items():
            if not _is_ident(name):
                continue
            optional = "" if name in required else "?"
            lines.append(f"  {name}{optional}: {_ts_type(_schema_declared_type(prop))};")
    lines.append("}")
    lines.append("")
    lines.append("interface Variables {")
    variable_keys = [key for key in request.variable_keys if _is_ident(key)]
    if not variable_keys:
        lines.append("  [key: string]: unknown;")
    else:
        for key in variable_keys:
            lines.append(f"  {key}?: unknown;")
    lines.append("}")
    lines.append("")
    lines.append("interface State {")
    for name, py_type in RUNTIME_STATE_FIELDS:
        ts_type = "Variables" if name == "variables" else _python_type_to_ts_runtime(py_type)
        lines.append(f"  {name}?: {ts_type};")
    lines.append("}")
    lines.append("")
    for namespace in documentation.namespaces:
        methods = [
            method
            for method in documentation.capabilities
            if method.namespace == namespace.name
        ]
        lines.append(f"interface {_namespace_class_name(namespace.name)} {{")
        lines.append("  call(method: string, kwargs?: JsonObject): Promise<unknown>;")
        for method in methods:
            fields = _top_level_fields(method.input_fields)
            lines.append(
                f"  {method.method}({_ts_kwargs(fields)}): Promise<JsonObject>;"
            )
        lines.append("}")
        lines.append("")
        lines.append(
            f"declare const {namespace.name}: {_namespace_class_name(namespace.name)};"
        )
        lines.append("")
    lines.extend(
        [
            "declare const args: Args;",
            "declare const state: State;",
            "declare const variables: Variables;",
            "",
        ]
    )
    return "\n".join(lines)


def _python_type_to_ts_runtime(py_type: str) -> str:
    mapping = {
        "str | None": "string | null",
        "str": "string",
        "Any": "unknown",
        "dict[str, Any] | None": "JsonObject | null",
        "list[Any]": "unknown[]",
        "dict[str, Any]": "JsonObject",
        "list[str]": "string[]",
    }
    if py_type in mapping:
        return mapping[py_type]
    return "unknown"


def _go_files(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
    document_path: str,
) -> list[LspWorkspaceFile]:
    return [
        LspWorkspaceFile(path="go.mod", content="module sandbox\n\ngo 1.26\n"),
        LspWorkspaceFile(path="sdk.go", content=_go_sdk(documentation)),
        LspWorkspaceFile(path=document_path, content=_ensure_go_package(request.source)),
    ]


def _ensure_go_package(source: str) -> str:
    stripped = source.lstrip()
    if stripped.startswith("package "):
        return source
    return "package main\n\n" + source


def _go_sdk(documentation: CapabilityDocumentation) -> str:
    lines = ["package main", "", 'type kwargs = map[string]any', ""]
    for namespace in documentation.namespaces:
        methods = [
            method
            for method in documentation.capabilities
            if method.namespace == namespace.name
        ]
        type_name = f"{namespace.name}Namespace"
        lines.append(f"type {type_name} struct{{}}")
        lines.append(f"var {namespace.name} {type_name}")
        lines.append("")
        lines.append(f"func ({type_name}) Call(method string, kwargs kwargs) (any, error) {{")
        lines.append("    return nil, nil")
        lines.append("}")
        lines.append("")
        for method in methods:
            lines.append(
                f"func ({type_name}) {method.method}(kwargs kwargs) (any, error) {{"
            )
            lines.append("    return nil, nil")
            lines.append("}")
            lines.append("")
    lines.extend(
        [
            "var args = map[string]any{}",
            "var state = map[string]any{}",
            "var variables = map[string]any{}",
            "",
        ]
    )
    return "\n".join(lines)


def _csharp_files(
    documentation: CapabilityDocumentation,
    request: CodeLspSessionCreateRequest,
    document_path: str,
) -> list[LspWorkspaceFile]:
    return [
        LspWorkspaceFile(path="UserCode.csproj", content=_csharp_csproj()),
        LspWorkspaceFile(path="UserCode.sln", content=_csharp_sln()),
        LspWorkspaceFile(path="Sdk.cs", content=_csharp_sdk(documentation)),
        LspWorkspaceFile(path=document_path, content=_csharp_user_source(request.source)),
    ]


def _csharp_csproj() -> str:
    return """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <LangVersion>14.0</LangVersion>
    <Nullable>enable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
  </PropertyGroup>
</Project>
"""


def _csharp_sln() -> str:
    return """Microsoft Visual Studio Solution File, Format Version 12.00
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "UserCode", "UserCode.csproj", "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Debug|Any CPU = Debug|Any CPU
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}.Release|Any CPU.Build.0 = Release|Any CPU
	EndGlobalSection
EndGlobal
"""


def _csharp_sdk(documentation: CapabilityDocumentation) -> str:
    """Отдельный файл: didOpen UserCode.cs не затирает SDK. `files.Create` — static class files."""
    lines = [
        "using System.Collections.Generic;",
        "using System.Threading.Tasks;",
        "",
    ]
    for namespace in documentation.namespaces:
        methods = [
            method
            for method in documentation.capabilities
            if method.namespace == namespace.name
        ]
        class_name = _csharp_static_class_name(namespace.name)
        lines.append(f"public static class {class_name}")
        lines.append("{")
        lines.append(
            "    public static Task<object?> Call(string method, Dictionary<string, object?> kwargs) => Task.FromResult<object?>(null);"
        )
        for method in methods:
            lines.append(
                f"    public static Task<object?> {method.method}(Dictionary<string, object?> kwargs) => Task.FromResult<object?>(null);"
            )
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def _csharp_static_class_name(namespace: str) -> str:
    if not _IDENT_RE.match(namespace):
        raise ValueError(f"csharp SDK namespace is not a valid identifier: {namespace!r}")
    if namespace in _CSHARP_KEYWORDS:
        return f"@{namespace}"
    return namespace


def _csharp_user_source(source: str) -> str:
    if re.search(r"\b(class|record|struct)\b", source):
        return source
    using_pattern = re.compile(r"(?m)^\s*using\s+[^;]+;\s*$")
    using_lines = [match.group(0).strip() for match in using_pattern.finditer(source)]
    body = using_pattern.sub("", source).strip()
    indent = "    " + body.replace("\n", "\n    ") if body else ""
    prefix = "\n".join(dict.fromkeys(using_lines))
    if prefix:
        prefix = f"{prefix}\n\n"
    return f"{prefix}public sealed partial class UserCode\n{{\n{indent}\n}}\n"

"""Сборка и раскладка bundle агента для CLI. Сервер читает bundle своей копией в FlowsLoader."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from platform_sdk.errors import bundle_error
from platform_sdk.json_types import JsonObject, JsonValue, as_json, require_object

FLOW_CONFIG_FILE_NAMES: tuple[str, ...] = ("flow.yaml", "flow.yml", "flow.json")
SCHEMA_COMMENT = "# yaml-language-server: $schema=.platform/schema/flow.schema.json\n"
CODE_SUFFIX_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".cs": "csharp",
}
LANGUAGE_TO_CODE_SUFFIX: dict[str, str] = {
    language: suffix for suffix, language in CODE_SUFFIX_TO_LANGUAGE.items()
}


class BundleNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str | None = None
    prompt_file: str | None = None
    code: str | None = None
    language: str | None = None
    function: JsonValue | None = None
    output_schema: JsonValue | None = None
    output_schema_file: str | None = None


class BundleBranch(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodes: dict[str, BundleNode] | None = None


class FlowDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodes: dict[str, BundleNode] | None = None
    branches: dict[str, BundleBranch] | None = None


def find_bundle_flow_config(bundle_dir: Path) -> Path | None:
    """Единственный flow-конфиг: flow.yaml | flow.yml | flow.json."""
    found = [bundle_dir / name for name in FLOW_CONFIG_FILE_NAMES if (bundle_dir / name).is_file()]
    if len(found) > 1:
        names = ", ".join(sorted(path.name for path in found))
        raise bundle_error(
            "bundle_ambiguous_config",
            f"Bundle '{bundle_dir.name}': ambiguous flow config files: {names}",
            path=str(bundle_dir),
        )
    return found[0] if found else None


def read_bundle_flow_config(config_path: Path) -> JsonObject:
    text = config_path.read_text(encoding="utf-8")
    try:
        if config_path.suffix in {".yaml", ".yml"}:
            loaded: object = yaml.safe_load(text)
        else:
            loaded = json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise bundle_error(
            "bundle_invalid_config",
            f"{config_path.name}: {exc}",
            path=str(config_path),
        ) from exc
    if loaded is None:
        raise bundle_error(
            "bundle_empty_config",
            f"{config_path.name} is empty",
            path=str(config_path),
        )
    try:
        return require_object(as_json(loaded, config_path.name), config_path.name)
    except ValueError as exc:
        raise bundle_error(
            "bundle_invalid_config",
            f"{config_path.name}: {exc}",
            path=str(config_path),
        ) from exc


def assemble_bundle(bundle_dir: Path) -> JsonObject:
    """Читает flow-конфиг и инлайнит prompt, code и output_schema."""
    config_path = find_bundle_flow_config(bundle_dir)
    if config_path is None:
        raise bundle_error(
            "bundle_config_missing",
            f"Bundle '{bundle_dir}' has no flow.yaml, flow.yml or flow.json",
            path=str(bundle_dir),
        )
    document = _document(read_bundle_flow_config(config_path), config_path.name)
    _reject_functions(document)
    if document.nodes is not None:
        document.nodes = {
            node_id: _inline_node(node, bundle_dir) for node_id, node in document.nodes.items()
        }
    if document.branches is not None:
        for branch in document.branches.values():
            if branch.nodes is None:
                continue
            branch.nodes = {
                node_id: _inline_node(node, bundle_dir) for node_id, node in branch.nodes.items()
            }
    return require_object(document.model_dump(mode="json", exclude_unset=True), "flow")


def layout_bundle(bundle_dir: Path, flow: JsonObject) -> None:
    """Раскладывает ответ сервера в flow.yaml, prompts/, code/ и schemas/."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    document = _document(flow, "flow")
    body = document.model_dump(mode="json", exclude_unset=True)
    body.pop("version", None)
    body.pop("base_version", None)
    if document.nodes is not None:
        body["nodes"] = _extract_node_map(document.nodes, bundle_dir)
    if document.branches is not None:
        extracted: JsonObject = {}
        for branch_id, branch in document.branches.items():
            branch_body = _dump_model(branch)
            if branch.nodes is not None:
                branch_body["nodes"] = _extract_node_map(
                    branch.nodes,
                    bundle_dir,
                    prefix=f"{branch_id}.",
                )
            extracted[branch_id] = branch_body
        body["branches"] = extracted
    text = yaml.safe_dump(body, sort_keys=False, allow_unicode=True)
    (bundle_dir / "flow.yaml").write_text(SCHEMA_COMMENT + text, encoding="utf-8")


def inline_prompt_from_file(node: Mapping[str, object], bundle_dir: Path) -> Mapping[str, object]:
    current = _node(node)
    if "prompt_file" in current.model_fields_set:
        raise bundle_error(
            "bundle_prompt_file_forbidden",
            "node.prompt_file is forbidden; use node.prompt",
        )
    prompt = current.prompt
    if prompt is None or prompt == "" or "\n" in prompt or not prompt.endswith(".md"):
        return _dump_node(current)
    current.prompt = _read_text(bundle_dir, prompt, "bundle_prompt_missing")
    return _dump_node(current)


def inline_output_schema_file(node: Mapping[str, object], bundle_dir: Path) -> Mapping[str, object]:
    current = _node(node)
    ref = current.output_schema_file
    if ref is None or ref == "":
        return _dump_node(current)
    dumped = _dump_node(current)
    if current.output_schema is not None:
        dumped.pop("output_schema_file", None)
        return dumped
    raw = _read_text(bundle_dir, ref, "bundle_output_schema_missing")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise bundle_error(
            "bundle_output_schema_invalid",
            f"{ref}: {exc}",
            path=ref,
        ) from exc
    try:
        dumped["output_schema"] = require_object(as_json(parsed, ref), ref)
    except ValueError as exc:
        raise bundle_error("bundle_output_schema_invalid", f"{ref}: {exc}", path=ref) from exc
    dumped.pop("output_schema_file", None)
    return dumped


def inline_code_from_file(node: Mapping[str, object], bundle_dir: Path) -> Mapping[str, object]:
    current = _node(node)
    code = current.code
    if code is None or code == "" or "\n" in code:
        return _dump_node(current)
    suffix = Path(code).suffix
    if suffix not in CODE_SUFFIX_TO_LANGUAGE:
        return _dump_node(current)
    current.code = _read_text(bundle_dir, code, "bundle_code_missing")
    if "language" not in current.model_fields_set:
        current.language = CODE_SUFFIX_TO_LANGUAGE[suffix]
    return _dump_node(current)


def _document(payload: object, label: str) -> FlowDocument:
    try:
        return FlowDocument.model_validate(payload)
    except ValidationError as exc:
        raise bundle_error("bundle_invalid_config", f"{label}: {exc}") from exc


def _node(node: Mapping[str, object]) -> BundleNode:
    try:
        return BundleNode.model_validate(dict(node))
    except ValidationError as exc:
        raise bundle_error("bundle_node_invalid", f"node must be an object: {exc}") from exc


def _dump_node(node: BundleNode) -> JsonObject:
    return _dump_model(node)


def _dump_model(model: BaseModel) -> JsonObject:
    return require_object(model.model_dump(mode="json", exclude_unset=True), type(model).__name__)


def _inline_node(node: BundleNode, bundle_dir: Path) -> BundleNode:
    current: Mapping[str, object] = _dump_node(node)
    current = inline_prompt_from_file(current, bundle_dir)
    current = inline_output_schema_file(current, bundle_dir)
    current = inline_code_from_file(current, bundle_dir)
    return _node(current)


def _reject_functions(document: FlowDocument) -> None:
    if document.nodes is not None:
        for node_id, node in document.nodes.items():
            _reject_function(node, f"nodes.{node_id}")
    if document.branches is None:
        return
    for branch_id, branch in document.branches.items():
        if branch.nodes is None:
            continue
        for node_id, node in branch.nodes.items():
            _reject_function(node, f"branches.{branch_id}.nodes.{node_id}")


def _reject_function(node: BundleNode, label: str) -> None:
    if "function" not in node.model_fields_set or node.function in (None, ""):
        return
    raise bundle_error(
        "bundle_function_not_supported",
        f"{label}.function is a server-bundle extension; put the source in code/",
        path=label,
    )


def _extract_node_map(
    nodes: dict[str, BundleNode],
    bundle_dir: Path,
    prefix: str = "",
) -> JsonObject:
    extracted: JsonObject = {}
    for node_id, node in nodes.items():
        current = _dump_node(node)
        prompt = node.prompt
        if prompt is not None and prompt != "" and "\n" in prompt:
            relative = f"prompts/{prefix}{node_id}.md"
            _write_text(bundle_dir, relative, prompt)
            current["prompt"] = relative
        code = node.code
        language_name = "python" if node.language is None or node.language == "" else node.language
        if code is not None and "\n" in code:
            suffix = LANGUAGE_TO_CODE_SUFFIX.get(language_name, ".py")
            relative = f"code/{prefix}{node_id}{suffix}"
            _write_text(bundle_dir, relative, code)
            current["code"] = relative
        if node.output_schema is not None:
            try:
                schema = require_object(node.output_schema, "output_schema")
            except ValueError:
                schema = None
            if schema is not None:
                relative = f"schemas/{prefix}{node_id}.output.json"
                _write_text(
                    bundle_dir,
                    relative,
                    json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
                )
                current["output_schema_file"] = relative
                current.pop("output_schema", None)
        extracted[node_id] = current
    return extracted


def _bundle_path(bundle_dir: Path, ref: str) -> Path:
    parts = Path(ref).parts
    if ref.startswith("/") or ".." in parts:
        raise bundle_error("bundle_path_escape", f"Path escapes the bundle: {ref}", path=ref)
    path = (bundle_dir / ref).resolve()
    root = bundle_dir.resolve()
    if not path.is_relative_to(root):
        raise bundle_error("bundle_path_escape", f"Path escapes the bundle: {ref}", path=ref)
    return path


def _read_text(bundle_dir: Path, ref: str, code: str) -> str:
    path = _bundle_path(bundle_dir, ref)
    if not path.is_file():
        raise bundle_error(code, f"File not found: {ref}", path=ref)
    return path.read_text(encoding="utf-8")


def _write_text(bundle_dir: Path, ref: str, text: str) -> None:
    path = _bundle_path(bundle_dir, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

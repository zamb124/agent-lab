"""Python language server vfs prepare."""

from __future__ import annotations

import json
from pathlib import Path

from apps.code_runner_python.services.executor import ensure_python_sandbox_site
from core.capabilities.lsp_commands import python_lsp_command, python_lsp_interpreter
from core.capabilities.models import LspWorkspace
from core.types import JsonObject, parse_json_object

__all__ = ["prepare_python_lsp_workspace", "python_lsp_command"]


def prepare_python_lsp_workspace(root: Path, workspace: LspWorkspace) -> None:
    _ = workspace
    interpreter = python_lsp_interpreter()
    sandbox_site = ensure_python_sandbox_site()
    config_path = root / "pyrightconfig.json"
    config: JsonObject = parse_json_object(
        config_path.read_text(encoding="utf-8"),
        "pyrightconfig",
    )
    config["pythonPath"] = str(interpreter)
    config["extraPaths"] = [str(sandbox_site)]
    _ = config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

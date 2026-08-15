"""Python language server vfs prepare."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from apps.code_runner_python.services.executor import ensure_python_sandbox_site
from core.capabilities.lsp_commands import python_lsp_command, python_lsp_interpreter
from core.capabilities.models import LspWorkspace
from core.types import JsonObject, require_json_object

__all__ = ["prepare_python_lsp_workspace", "python_lsp_command"]


def prepare_python_lsp_workspace(root: Path, workspace: LspWorkspace) -> None:
    _ = workspace
    interpreter = python_lsp_interpreter()
    sandbox_site = ensure_python_sandbox_site()
    config_path = root / "pyrightconfig.json"
    raw_config = cast(object, json.loads(config_path.read_text(encoding="utf-8")))
    config: JsonObject = require_json_object(raw_config, "pyrightconfig")
    config["pythonPath"] = str(interpreter)
    config["extraPaths"] = [str(sandbox_site)]
    _ = config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

"""AST-сканер: запрет тихих исключений и `or default` фолбеков в operations.py.

Проверяет файлы `apps/sync/realtime/operations.py` и `apps/sync/realtime/handlers.py`
(внутренние helpers) на:
  - `except Exception: pass` / `except: pass`
  - `except Exception: continue`
  - `bare except: ...`

Фолбеки `or default` отдельно ловит `pytest tests/sync/integration/test_ops_zero_fallback.py`
(through behaviour: ws_invalid_payload / ws_no_company / not_found).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_TARGET_FILES = [
    _REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py",
    _REPO_ROOT / "apps" / "sync" / "realtime" / "command_router.py",
]


@pytest.mark.parametrize("target_file", _TARGET_FILES, ids=lambda p: p.name)
def test_no_silent_except_in_ops(target_file: Path) -> None:
    source = target_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(target_file))

    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # Bare except: запрещён всегда.
        if node.type is None:
            violations.append(
                f"{target_file.name}:{node.lineno} bare `except:` запрещён"
            )
            continue
        # `except Exception: pass` или `: continue` — всегда нарушение.
        if (
            isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
            and len(node.body) == 1
            and isinstance(node.body[0], (ast.Pass, ast.Continue))
        ):
            violations.append(
                f"{target_file.name}:{node.lineno} `except Exception: pass/continue` запрещён"
            )
        # `except Exception:` без re-raise — позволяем только если последний
        # statement — `raise` или `raise ... from e`.
        if (
            isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
        ):
            last = node.body[-1] if node.body else None
            has_raise = isinstance(last, ast.Raise)
            has_inner_raise = any(isinstance(s, ast.Raise) for s in node.body)
            if not has_raise and not has_inner_raise:
                violations.append(
                    f"{target_file.name}:{node.lineno} `except Exception:` без `raise` запрещён"
                )

    assert not violations, "\n".join(violations)

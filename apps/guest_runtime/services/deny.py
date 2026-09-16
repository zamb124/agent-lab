"""Deny-list исходников code_agent на сборке."""

from __future__ import annotations

from core.guest_runtime.models import CodeAgentSourceFile

_DENIED_NAME_MARKERS: tuple[str, ...] = ("torch", "cuda", "nvidia")
_DEP_MANIFEST_NAMES: frozenset[str] = frozenset(
    {
        "requirements.txt",
        "requirements.in",
        "pyproject.toml",
        "package.json",
        "uv.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pipfile.lock",
        "cargo.lock",
        "composer.lock",
        "gemfile.lock",
        "go.sum",
    }
)


def assert_source_allowed(files: list[CodeAgentSourceFile], contents: dict[str, bytes]) -> None:
    for item in files:
        relative = item.relative_path.strip().lower()
        filename = relative.rsplit("/", 1)[-1]
        for marker in _DENIED_NAME_MARKERS:
            if marker in relative:
                raise ValueError(
                    f"code_agent build denies path containing {marker!r}: {item.relative_path}"
                )
        payload = contents.get(item.relative_path)
        if payload is None:
            raise ValueError(f"code_agent build missing bytes for {item.relative_path}")
        if filename in _DEP_MANIFEST_NAMES:
            text = payload.decode("utf-8")
            lowered = text.lower()
            for marker in _DENIED_NAME_MARKERS:
                if marker in lowered:
                    raise ValueError(
                        f"code_agent build denies {marker!r} in {item.relative_path}"
                    )

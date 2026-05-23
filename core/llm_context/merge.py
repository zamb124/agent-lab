"""Merge helpers for LLM context profile overlays."""

from __future__ import annotations

from typing import Any


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge JSON-like dictionaries; override wins."""
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def merge_dict_layers(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """Merge optional dict layers in order."""
    merged: dict[str, Any] = {}
    for layer in layers:
        if layer is None:
            continue
        merged = deep_merge_dict(merged, layer)
    return merged


__all__ = ["deep_merge_dict", "merge_dict_layers"]

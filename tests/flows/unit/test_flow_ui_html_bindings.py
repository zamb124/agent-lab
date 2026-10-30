"""Привязки ``data-bind`` / ``data-show`` в ``source`` html-блока.

Разбор идёт стандартным HTMLParser: комментарии, тела ``script``/``style``/``textarea``
и регистр атрибутов трактуются как в браузере. Невалидный путь — ошибка автора блока.
"""

from __future__ import annotations

import pytest

from apps.flows.src.flow_ui.html_bindings import (
    HTML_BIND_ATTRIBUTE,
    HTML_SHOW_ATTRIBUTE,
    html_bound_paths,
)


def test_attribute_names_are_the_ones_used_by_the_sandbox_bootstrap() -> None:
    assert HTML_BIND_ATTRIBUTE == "data-bind"
    assert HTML_SHOW_ATTRIBUTE == "data-show"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("<p data-bind=\"a\"></p><i data-show=\"b\"></i>", ["a", "b"]),
        ("<p data-bind=\"a\"></p><span data-bind=\"a\"></span>", ["a"]),
        ("<p data-bind = 'order.total'>x</p>", ["order.total"]),
        ("<p data-bind=order.total>x</p>", ["order.total"]),
        ("<p\n  data-show=\"ready\"\n>x</p>", ["ready"]),
        ("<img data-bind=\"image\" />", ["image"]),
        ("<P DATA-BIND=\"upper\"></P>", ["upper"]),
        ("<p data-bind=\"  spaced  \"></p>", ["spaced"]),
        ("<!-- <p data-bind=\"ignored\"></p> --><p data-bind=\"seen\"></p>", ["seen"]),
        ("<script>const x = '<p data-bind=\"ignored\">';</script><p data-bind=\"seen\"></p>", ["seen"]),
        ("<style>/* <p data-show=\"ignored\"> */</style><p data-show=\"seen\"></p>", ["seen"]),
        ("<textarea><p data-bind=\"ignored\"></p></textarea><p data-bind=\"seen\"></p>", ["seen"]),
        ("<p data-binding=\"x\" data-showcase=\"y\"></p>", []),
        ("plain text without markup", []),
        ("", []),
    ],
)
def test_bound_paths(source: str, expected: list[str]) -> None:
    assert html_bound_paths(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "<p data-bind=\"1bad\"></p>",
        "<p data-show=\"order..total\"></p>",
        "<p data-bind=\"\"></p>",
        "<p data-bind></p>",
        "<p data-bind=\"a-b\"></p>",
        "<p data-show=\"a b\"></p>",
    ],
)
def test_invalid_paths_raise(source: str) -> None:
    with pytest.raises(ValueError, match="html block: invalid state path in data-"):
        _ = html_bound_paths(source)


def test_error_lists_every_invalid_binding() -> None:
    with pytest.raises(ValueError) as exc:
        _ = html_bound_paths("<p data-bind=\"1a\"></p><i data-show=\"2b\"></i>")
    assert "data-bind='1a'" in str(exc.value)
    assert "data-show='2b'" in str(exc.value)

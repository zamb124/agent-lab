"""Статический сканер переменных шаблона промпта.

Разбирает ту же грамматику, что и ``VariableResolver.render_template``
(:mod:`core.variables.resolver`), но не резолвит значения, а извлекает список
ссылок на переменные. Используется data-flow инспектором, чтобы знать, какие
переменные требуются промпту ``llm_node`` без исполнения рантайма.

Грамматика (совпадает с render_template):
- ``{variable}`` — обязательная подстановка
- ``{variable|default}`` — обязательная с default при отсутствии значения (не строго обязательная)
- ``{?variable}`` / ``{?variable|default}`` — опциональная
- ``?variable`` / ``?variable|default`` — короткий формат опциональной
- ``{for item in list}...{endfor}`` — цикл; ``list`` читается, ``item`` — локальная
- ``{dict.key}`` — доступ к вложенному пути; корневой токен ``dict``
"""

from __future__ import annotations

from core.models import StrictBaseModel

_SYSTEM_TEMPLATE_VARIABLES: frozenset[str] = frozenset(
    {
        "current_date",
        "current_time",
        "current_datetime",
        "current_year",
        "current_month",
        "current_day",
        "user_name",
        "user_id",
        "user_email",
    }
)


class TemplateVariableRef(StrictBaseModel):
    """Одна ссылка на переменную, найденная в шаблоне."""

    name: str
    root: str
    required: bool


class TemplateScanResult(StrictBaseModel):
    """Результат статического разбора шаблона."""

    refs: list[TemplateVariableRef]

    @property
    def required_roots(self) -> list[str]:
        seen: dict[str, None] = {}
        for ref in self.refs:
            if ref.required and ref.root not in seen:
                seen[ref.root] = None
        return list(seen)

    @property
    def optional_roots(self) -> list[str]:
        required = set(self.required_roots)
        seen: dict[str, None] = {}
        for ref in self.refs:
            if ref.root in required or ref.root in seen:
                continue
            seen[ref.root] = None
        return list(seen)


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or ch == "."


def _is_system_ref(root: str) -> bool:
    return root in _SYSTEM_TEMPLATE_VARIABLES


def scan_prompt_template(template: str | None) -> TemplateScanResult:
    """Возвращает ссылки на переменные шаблона.

    Системные переменные (дата/время/пользователь) исключаются: они всегда
    доступны в рантайме и не являются входами ноды.
    """

    if not template:
        return TemplateScanResult(refs=[])
    collector: dict[tuple[str, bool], TemplateVariableRef] = {}
    _scan(template, bound=frozenset(), collector=collector)
    return TemplateScanResult(refs=list(collector.values()))


def _add_ref(
    collector: dict[tuple[str, bool], TemplateVariableRef],
    *,
    name: str,
    required: bool,
    bound: frozenset[str],
) -> None:
    name = name.strip()
    if not name:
        return
    root = name.split(".", 1)[0]
    if not root or root in bound or _is_system_ref(root):
        return
    key = (name, required)
    if key in collector:
        return
    if required:
        _ = collector.pop((name, False), None)
    elif (name, True) in collector:
        return
    collector[key] = TemplateVariableRef(name=name, root=root, required=required)


def _scan(
    text: str,
    *,
    bound: frozenset[str],
    collector: dict[tuple[str, bool], TemplateVariableRef],
) -> None:
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "\\" and i + 1 < length:
            i += 2
            continue
        if ch == "{":
            if text[i : i + 5] == "{for " or text[i : i + 4] == "{for":
                i = _scan_for_loop(text, i, bound=bound, collector=collector)
                continue
            i = _scan_block(text, i, bound=bound, collector=collector)
            continue
        if ch == "?" and (i == 0 or text[i - 1] not in "{\\"):
            i = _scan_short_form(text, i, bound=bound, collector=collector)
            continue
        i += 1


def _scan_block(
    text: str,
    start: int,
    *,
    bound: frozenset[str],
    collector: dict[tuple[str, bool], TemplateVariableRef],
) -> int:
    length = len(text)
    i = start + 1
    optional = False
    if i < length and text[i] == "?":
        optional = True
        i += 1
    expr_start = i
    while i < length and _is_ident_char(text[i]):
        i += 1
    expr = text[expr_start:i]
    if not expr:
        return start + 1
    has_default = False
    default_start = i
    if i < length and text[i] == "|":
        has_default = True
        i += 1
        default_start = i
        depth = 1
        while i < length:
            if text[i] == "\\" and i + 1 < length:
                i += 2
                continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
    if i < length and text[i] == "}":
        default_text = text[default_start:i] if has_default else ""
        i += 1
    else:
        default_text = text[default_start:i] if has_default else ""
    _add_ref(
        collector,
        name=expr,
        required=not optional and not has_default,
        bound=bound,
    )
    if has_default and default_text:
        _scan(default_text, bound=bound, collector=collector)
    return i


def _scan_short_form(
    text: str,
    start: int,
    *,
    bound: frozenset[str],
    collector: dict[tuple[str, bool], TemplateVariableRef],
) -> int:
    length = len(text)
    j = start + 1
    while j < length and _is_ident_char(text[j]):
        j += 1
    if j == start + 1:
        return start + 1
    expr = text[start + 1 : j]
    _add_ref(collector, name=expr, required=False, bound=bound)
    if j < length and text[j] == "|":
        j += 1
        while j < length and text[j] not in "\n{":
            j += 1
    return j


def _scan_for_loop(
    text: str,
    start: int,
    *,
    bound: frozenset[str],
    collector: dict[tuple[str, bool], TemplateVariableRef],
) -> int:
    length = len(text)
    i = start + 4
    while i < length and text[i] in " \n\t":
        i += 1
    var_start = i
    while i < length and text[i] not in " \n\t":
        i += 1
    loop_var = text[var_start:i]
    while i < length and text[i] in " \n\t":
        i += 1
    if text[i : i + 3] != "in ":
        return start + 1
    i += 3
    while i < length and text[i] in " \n\t":
        i += 1
    list_start = i
    while i < length and text[i] not in "}\n\t ":
        i += 1
    list_name = text[list_start:i]
    while i < length and text[i] != "}":
        i += 1
    if i >= length:
        return start + 1
    i += 1
    body_start = i
    depth = 1
    while i < length and depth > 0:
        if text[i : i + 5] == "{for ":
            depth += 1
            i += 5
        elif text[i : i + 8] == "{endfor}":
            depth -= 1
            if depth == 0:
                break
            i += 8
        else:
            i += 1
    body = text[body_start:i]
    if i < length:
        i += 8
    _add_ref(collector, name=list_name, required=False, bound=bound)
    extra: set[str] = {loop_var} if loop_var else set()
    inner_bound = bound | extra
    _scan(body, bound=inner_bound, collector=collector)
    return i


__all__ = [
    "TemplateScanResult",
    "TemplateVariableRef",
    "scan_prompt_template",
]

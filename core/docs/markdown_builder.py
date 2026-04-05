"""
Сборка документации inline-кода в один Markdown-документ.
"""

from __future__ import annotations

from core.docs.models import (
    CodeTemplate,
    DocumentationResponse,
    GlobalVariable,
    ModuleMethod,
    PlatformToolDoc,
    StateField,
)


def _fence_python(code: str) -> str:
    body = code.rstrip("\n")
    fence = "```"
    while fence in body:
        fence += "`"
    return f"{fence}python\n{body}\n{fence}\n"


def _fence_json(raw: str) -> str:
    body = raw.strip("\n")
    fence = "```"
    while fence in body:
        fence += "`"
    return f"{fence}json\n{body}\n{fence}\n"


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build_documentation_markdown(
    response: DocumentationResponse,
    *,
    title: str | None = None,
) -> str:
    """
    Формирует Markdown по ответу DocumentationService (тот же состав, что у completions).
    """
    lang = response.language
    persp = response.perspective
    h1 = title or f"Документация inline-кода ({lang}, ракурс: {persp})"

    lines: list[str] = [
        f"# {h1}",
        "",
        "## Оглавление",
        "",
        "- [Глобальные объекты](#doc-globals)",
        "- [Модули](#doc-modules)",
        "- [Поля state](#doc-state)",
        "- [Встроенные имена (builtins)](#doc-builtins)",
        "- [Platform tools (реестр и БД)](#doc-platform-tools)",
        "- [Шаблоны](#doc-templates)",
        "",
    ]

    lines.append('<h2 id="doc-globals">Глобальные объекты</h2>')
    lines.append("")
    if not response.globals:
        lines.append("_Нет доступных глобальных переменных._")
        lines.append("")
    else:
        for g in response.globals:
            lines.extend(_global_to_md(g))
        lines.append("")

    lines.append('<h2 id="doc-modules">Модули</h2>')
    lines.append("")
    if not response.modules and not response.module_methods:
        lines.append("_Нет доступных модулей._")
        lines.append("")
    else:
        lines.append("**Доступные модули:** " + ", ".join(f"`{m}`" for m in response.modules))
        lines.append("")
        for mod_name in sorted(response.module_methods.keys()):
            methods = response.module_methods[mod_name]
            lines.append(f"### `{mod_name}`")
            lines.append("")
            if not methods:
                lines.append("_Нет описанных методов._")
                lines.append("")
                continue
            for m in methods:
                lines.extend(_module_method_to_md(m))
            lines.append("")

    lines.append('<h2 id="doc-state">Поля state</h2>')
    lines.append("")
    if not response.state_fields:
        lines.append("_Нет доступных полей state._")
        lines.append("")
    else:
        lines.append("| Поле | Тип | Только чтение | Описание |")
        lines.append("| --- | --- | --- | --- |")
        for f in response.state_fields:
            ro = "да" if f.readonly else "нет"
            lines.append(
                f"| `{f.name}` | `{_escape_table_cell(f.type)}` | {ro} | {_escape_table_cell(f.description)} |"
            )
        lines.append("")

    lines.append('<h2 id="doc-builtins">Встроенные имена (builtins)</h2>')
    lines.append("")
    if not response.builtins:
        lines.append("_Нет доступных builtins._")
        lines.append("")
    else:
        chunk: list[str] = []
        for name in response.builtins:
            chunk.append(f"`{name}`")
            if len(chunk) >= 8:
                lines.append(", ".join(chunk))
                chunk = []
        if chunk:
            lines.append(", ".join(chunk))
        lines.append("")

    lines.append('<h2 id="doc-platform-tools">Platform tools (реестр и БД)</h2>')
    lines.append("")
    if not response.platform_tools:
        lines.append("_Нет зарегистрированных platform tools (пустой реестр и БД)._")
        lines.append("")
    else:
        lines.append(
            "Тулы для `llm.chat(..., tools=[...])` и конфигов нод: записи из **БД компании** "
            "и дополнение экземплярами только из **процессного ToolRegistry** (`registry_only`)."
        )
        lines.append("")
        for pt in response.platform_tools:
            lines.extend(_platform_tool_to_md(pt))
        lines.append("")

    lines.append('<h2 id="doc-templates">Шаблоны</h2>')
    lines.append("")
    if not response.templates:
        lines.append("_Нет шаблонов._")
        lines.append("")
    else:
        for t in response.templates:
            lines.extend(_template_to_md(t))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _global_to_md(g: GlobalVariable) -> list[str]:
    out = [
        f"### `{g.name}`",
        "",
        f"**Тип:** `{g.type}`",
        "",
    ]
    if g.doc.strip():
        out.append(g.doc.strip())
        out.append("")
    return out


def _module_method_to_md(m: ModuleMethod) -> list[str]:
    out = [
        f"- **`{m.name}`** (`{m.type}`)",
    ]
    if m.doc.strip():
        for line in m.doc.strip().splitlines():
            out.append(f"  {line}")
    return out


def _platform_tool_to_md(t: PlatformToolDoc) -> list[str]:
    out = [
        f"### `{t.tool_id}`",
        "",
        f"**Подпись:** {t.display_name}",
        f"**Источник:** `{t.source}`",
    ]
    if t.tags:
        out.append("**Теги:** " + ", ".join(f"`{x}`" for x in t.tags))
    if t.code_mode:
        out.append(f"**code_mode:** `{t.code_mode}`")
    if t.mcp_server_id:
        out.append(f"**mcp_server_id:** `{t.mcp_server_id}`")
    if t.mcp_tool_name:
        out.append(f"**mcp_tool_name:** `{t.mcp_tool_name}`")
    out.append("")
    if t.description.strip():
        out.append(t.description.strip())
        out.append("")
    out.append("**Схема аргументов:**")
    out.append("")
    out.append(_fence_json(t.args_schema_json))
    out.append("")
    if t.code_preview and t.code_preview.strip():
        out.append("**Фрагмент кода (из БД):**")
        out.append("")
        out.append(_fence_python(t.code_preview))
        out.append("")
    return out


def _template_to_md(t: CodeTemplate) -> list[str]:
    tags = ", ".join(f"`{x}`" for x in (t.tags or []))
    out = [
        f"### {t.name}",
        "",
        f"- **id:** `{t.id}`",
        f"- **категория:** `{t.category}`",
        f"- **node_type:** `{t.node_type}`",
    ]
    if tags:
        out.append(f"- **теги:** {tags}")
    out.append("")
    if t.description.strip():
        out.append(t.description.strip())
        out.append("")
    out.append(_fence_python(t.code))
    out.append("")
    return out

"""
Сборка документации inline-кода в один Markdown-документ.
"""

from __future__ import annotations

from core.docs.models import (
    CodeTemplate,
    DocumentationQuery,
    DocumentationResponse,
    GlobalVariable,
    ModuleMethod,
    PlatformToolDoc,
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


def _escape_html_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _entry_point_section_lines(lang: str, perspective: str) -> list[str]:
    """Секция «точка входа» для ноды code и inline tool (execute_tool), не codegen run(state)."""
    if lang != "python":
        return []
    if perspective not in ("editor", "node", "tool"):
        return []
    sample_execute = """def execute(args, state):
    return {}"""
    sample_tool_class = """class MyTool(BaseTool):
    async def run(self, args, state):
        return {}"""
    return [
        '<h2 id="doc-entry">Точка входа (нода <code>code</code> и inline tool)</h2>',
        "",
        "Один и тот же рантайм: `PythonCodeRunner.execute_tool`. Не путать с codegen-путём "
        "`async def run(state): ...` (`PythonCodeRunner.execute`, другой контракт).",
        "",
        "В порядке приоритета компилятор ищет:",
        "",
        "1. Класс, наследник `BaseTool`, с методом `run(self, args, state)`.",
        "2. Функцию `execute` (sync или async) с аргументами `args` и при необходимости `state`.",
        "3. Иначе — **последнюю** top-level функцию в файле; `args` маппятся в параметры по имени.",
        "",
        "**Пример (функция):**",
        "",
        _fence_python(sample_execute),
        "**Пример (класс):**",
        "",
        _fence_python(sample_tool_class),
        "",
    ]


def build_documentation_markdown(
    response: DocumentationResponse,
    *,
    title: str | None = None,
    query: DocumentationQuery | None = None,
) -> str:
    """
    Формирует Markdown по ответу DocumentationService (тот же состав, что у completions).
    """
    lang = response.language
    persp = response.perspective
    entry_lines = _entry_point_section_lines(lang, persp)
    h1 = title or f"Документация inline-кода ({lang}, ракурс: {persp})"

    toc: list[str] = []
    if entry_lines:
        toc.append("- [Точка входа (code / tool)](#doc-entry)")
    toc.append("- [Глобальные объекты](#doc-globals)")
    if response.runtime_namespace_extras is not None:
        toc.append("- [Доп. символы sandbox](#doc-runtime-namespace)")
    toc_tail = [
        "- [Модули](#doc-modules)",
        "- [Поля state](#doc-state)",
        "- [Встроенные имена (builtins)](#doc-builtins)",
    ]
    if query is None or query.include_platform_tools:
        toc_tail.append("- [Platform tools (реестр и БД)](#doc-platform-tools)")
    toc_tail.append("- [Шаблоны](#doc-templates)")
    toc.extend(toc_tail)

    lines: list[str] = [
        f"# {h1}",
        "",
        "## Оглавление",
        "",
        *toc,
        "",
    ]
    if entry_lines:
        lines.extend(entry_lines)

    lines.append('<h2 id="doc-globals">Глобальные объекты</h2>')
    lines.append("")
    if not response.globals:
        lines.append("_Нет доступных глобальных переменных._")
        lines.append("")
    else:
        for g in response.globals:
            lines.extend(_global_to_md(g))
        lines.append("")

    if response.runtime_namespace_extras is not None:
        lines.append('<h2 id="doc-runtime-namespace">Дополнительные символы sandbox</h2>')
        lines.append("")
        lines.append(
            "Имена из фактического `PythonNamespaceBuilder.build()`, которых нет в статическом `GLOBALS`."
        )
        lines.append("")
        if not response.runtime_namespace_extras:
            lines.append("_Список пуст._")
            lines.append("")
        else:
            for g in response.runtime_namespace_extras:
                lines.extend(_global_to_md(g))
            lines.append("")

    lines.append('<h2 id="doc-modules">Модули</h2>')
    lines.append("")
    if query is not None and not query.markdown_expand_module_methods:
        if response.modules:
            lines.append("**Доступные модули:** " + ", ".join(f"`{m}`" for m in response.modules))
            lines.append("")
            lines.append(
                "В sandbox разрешено подмножество API этих модулей. "
                "Полный перечень методов и сигнатур — в справке редактора кода платформы."
            )
            lines.append("")
        else:
            lines.append("_Нет доступных модулей._")
            lines.append("")
    elif not response.modules and not response.module_methods:
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
    if query is not None and not query.markdown_expand_builtins:
        lines.append(
            "В inline-коде доступен ограниченный whitelist встроенных имён Python "
            "(политика платформы). Полный перечень — в справке редактора кода."
        )
        lines.append("")
    elif not response.builtins:
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

    if query is None or query.include_platform_tools:
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
    title = (t.display_name or "").strip() or t.tool_id
    safe_title = _escape_html_text(title)
    out = [
        f'<h3 class="docs-platform-tool-title">{safe_title}</h3>',
        "",
        f"- **tool_id:** `{t.tool_id}`",
        f"- **Источник:** `{t.source}`",
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

#!/usr/bin/env python3
"""Codemod: JS→TS boilerplate для Lit-компонентов платформы.

После `git mv x.js x.ts` вставляет:
- type-импорты (CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult)
- `static override` для properties/styles
- `declare <prop>: <type>;` для каждого ключа static properties
- `override` + типы для lifecycle-методов и render()
- `(e)` → `(e: Event)` в обработчиках `_on*`/`_handle*`

Не трогает: event detail-типы, state-селекторы, сложные members — остаются
на ручную доработку по ошибкам tsc.
"""
import re
import sys

PROP_TYPE_MAP = {
    'String': 'string',
    'Number': 'number',
    'Boolean': 'boolean',
    'Array': 'unknown[]',
    'Object': 'Record<string, unknown>',
    'Function': 'unknown',
}

LIFECYCLE = {
    'connectedCallback': 'override connectedCallback(): void {',
    'disconnectedCallback': 'override disconnectedCallback(): void {',
    'firstUpdated': 'override firstUpdated(changed: PropertyValues<this>): void {',
    'willUpdate': 'override willUpdate(changed: PropertyValues<this>): void {',
    'updated': 'override updated(changed: PropertyValues<this>): void {',
    'render': 'override render(): TemplateResult {',
}

HANDLER_RE = re.compile(r'^(\s*)(_on[A-Z]\w*|_handle[A-Z]\w*|on[A-Z]\w*)\((\w+)\)\s*\{$', re.M)


def prop_ts_type(prop_body: str) -> str:
    m = re.search(r'type:\s*(\w+)', prop_body)
    if not m:
        return 'unknown'
    return PROP_TYPE_MAP.get(m.group(1), 'unknown')


def main(path: str) -> None:
    src = open(path).read()
    if 'lit-shim' not in src:
        # добавить type-импорт после первого import из lit/lit-shim
        m = re.search(r"^import \{[^}]*\} from '([^']+)';", src, re.M)
        if not m:
            print('no lit import found', path)
            return
        base = m.group(1)
        shim = base.replace('lit.min.js', 'lit-shim.js') if 'lit.min' in base else base
        # относительный путь до lib/
        depth = path.split('components/')[-1].count('/')
        rel = '../' * (depth + 1) + 'lit-shim.js'
        src = src.replace(m.group(0), m.group(0) + f"\nimport type {{ CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult }} from '{rel}';", 1)

    # properties block → declares
    m = re.search(r'^(\s*)static\s+(override\s+)?properties\s*=\s*\{(.*?)\n\s*\};', src, re.S | re.M)
    if m:
        body = m.group(3)
        keys = re.findall(r'^\s*(?:/\*\*[^*]*\*/\s*)?(\w+):', body, re.M)
        decls = []
        for key in keys:
            if key.startswith('_'):
                continue
            # найти type в теле свойства
            pm = re.search(rf'\b{key}:\s*\{{([^}}]*)\}}', body)
            t = prop_ts_type(pm.group(1)) if pm else 'unknown'
            decls.append(f'    declare {key}: {t};')
        inner = '_'.join(k for k in keys if k.startswith('_'))
        for key in keys:
            if key.startswith('_'):
                pm = re.search(rf'\b{key}:\s*\{{([^}}]*)\}}', body)
                t = prop_ts_type(pm.group(1)) if pm else 'unknown'
                decls.append(f'    declare {key}: {t};')
        decl_block = '\n'.join(decls) + '\n\n'
        # заменить static на static override с типом
        old_head = m.group(0).split('{')[0]
        src = src.replace(m.group(0), m.group(0).replace('static properties = {', 'static override properties: PropertyDeclarations = {').replace('static override properties = {', 'static override properties: PropertyDeclarations = {'), 1)
        # вставить declares перед `static styles` или `constructor`
        anchor = re.search(r'^\s*static\s+(override\s+)?styles\b', src, re.M)
        if anchor:
            src = src[:anchor.start()] + decl_block + '    ' + src[anchor.start():].lstrip()
        else:
            ctor = re.search(r'^\s*constructor\s*\(', src, re.M)
            if ctor:
                src = src[:ctor.start()] + decl_block + '\n' + src[ctor.start():]

    src = re.sub(r'^(\s*)static\s+styles\s*=', r'\1static override styles: CSSResultGroup =', src, flags=re.M)

    for name, sig in LIFECYCLE.items():
        src = re.sub(rf'^(\s*)(?:override\s+)?{name}\((\w*)\)\s*\{{', rf'\1{sig}', src, flags=re.M)

    src = HANDLER_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}({m.group(3)}: Event) {{', src)
    # arrow-обработчики `(e) =>` в шаблонах — руками
    open(path, 'w').write(src)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)

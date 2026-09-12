/**
 * Шаблоны текстовых свойств блоков: ``{path}``, ``{path|default}``,
 * ``{?path}``, ``{?path|default}``; ``\{`` — литеральная скобка. Пути —
 * dotted-path по проекции state (``customer.email``). Та же грамматика, что у
 * ``VariableResolver.render_template`` (подмножество без циклов и short form);
 * паритет закреплён ``tests/fixtures/flow_ui/templating.json``.
 *
 * Обязательная ссылка без значения делает шаблон неразрешённым — блок с таким
 * текстом не рендерится; это фиксирует ``rendered=false`` в результате.
 *
 * Непарные ``{}`` — ошибка автора: рендер бросает исключение (как Python), publish gate
 * показывает ``template_unbalanced``; ``templatePaths`` при этом остаётся снисходительным,
 * как Python-сканер, чтобы проблемы путей находились и в недописанном тексте.
 * Выражение с посторонним символом после пути (``{a-b}``) — литеральный текст.
 */

function isIdentChar(ch) {
    return /[A-Za-z0-9_.]/.test(ch);
}

/** Описание первой непарной скобки или ``null``; ``\{`` / ``\}`` не считаются. */
export function unmatchedBraceMessage(template) {
    let depth = 0;
    for (let i = 0; i < template.length; i += 1) {
        const ch = template[i];
        if (ch === '\\' && i + 1 < template.length) {
            i += 1;
            continue;
        }
        if (ch === '{') depth += 1;
        else if (ch === '}') {
            depth -= 1;
            if (depth < 0) return `unmatched closing brace '}' at position ${i}`;
        }
    }
    return depth > 0 ? `unmatched opening brace '{' (${depth} not closed)` : null;
}

function assertBalanced(template) {
    const problem = unmatchedBraceMessage(template);
    if (problem !== null) throw new Error(`flow-ui: ${problem} in ${JSON.stringify(template)}`);
}

export function valueAtPath(state, path) {
    if (typeof path !== 'string' || path === '') return undefined;
    let current = state;
    for (const segment of path.split('.')) {
        if (current === null || typeof current !== 'object') return undefined;
        if (Array.isArray(current)) {
            if (!/^\d+$/.test(segment)) return undefined;
            current = current[Number(segment)];
            continue;
        }
        if (!Object.prototype.hasOwnProperty.call(current, segment)) return undefined;
        current = current[segment];
    }
    return current;
}

function isPresent(value) {
    return value !== undefined && value !== null && value !== '';
}

export function stringifyTemplateValue(value) {
    if (value === undefined || value === null) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return JSON.stringify(value);
}

/** Пути шаблона в порядке появления (без дублей). */
export function templatePaths(template) {
    const paths = [];
    const visit = (text) => {
        renderTemplateInternal(text, null, paths);
    };
    visit(typeof template === 'string' ? template : '');
    return paths;
}

function renderTemplateInternal(template, state, paths, keepUnresolved = false) {
    let out = '';
    let rendered = true;
    let i = 0;
    const length = template.length;
    while (i < length) {
        const ch = template[i];
        if (ch === '\\' && i + 1 < length) {
            out += template[i + 1];
            i += 2;
            continue;
        }
        if (ch !== '{') {
            out += ch;
            i += 1;
            continue;
        }
        const exprBegin = i;
        let j = i + 1;
        const optional = template[j] === '?';
        if (optional) j += 1;
        const exprStart = j;
        while (j < length && isIdentChar(template[j])) j += 1;
        const path = template.slice(exprStart, j);
        if (path === '') {
            out += ch;
            i += 1;
            continue;
        }
        let defaultText = null;
        if (template[j] === '|') {
            j += 1;
            const defaultStart = j;
            let depth = 1;
            while (j < length) {
                if (template[j] === '\\' && j + 1 < length) {
                    j += 2;
                    continue;
                }
                if (template[j] === '{') depth += 1;
                else if (template[j] === '}') {
                    depth -= 1;
                    if (depth === 0) break;
                }
                j += 1;
            }
            defaultText = template.slice(defaultStart, j);
        }
        if (paths !== null && !paths.includes(path)) paths.push(path);
        if (template[j] !== '}') {
            // Незакрытое выражение: пути учтены, текст остаётся как есть — баланс скобок проверяет рендер
            if (state === null) {
                if (defaultText !== null) renderTemplateInternal(defaultText, null, paths);
                i = j;
                continue;
            }
            out += ch;
            i += 1;
            continue;
        }
        i = j + 1;
        if (state === null) {
            if (defaultText !== null) renderTemplateInternal(defaultText, null, paths);
            continue;
        }
        const value = valueAtPath(state, path);
        if (isPresent(value)) {
            out += stringifyTemplateValue(value);
            continue;
        }
        if (defaultText !== null) {
            const nested = renderTemplateInternal(defaultText, state, paths, keepUnresolved);
            if (!nested.rendered) rendered = false;
            out += nested.text;
            continue;
        }
        if (keepUnresolved) {
            out += template.slice(exprBegin, j + 1);
            continue;
        }
        if (!optional) rendered = false;
    }
    return { text: out, rendered };
}

/** Текст шаблона или ``null``, когда обязательный путь пуст — блок с таким свойством не рендерится. */
export function resolvedText(template, state) {
    if (typeof template !== 'string') throw new Error('flow-ui: template property must be a string');
    const result = renderTemplate(template, state);
    return result.rendered ? result.text : null;
}

/**
 * Холст редактора: известные пути подставляются, пустые остаются как ``{path}`` — автор видит структуру.
 * Недописанный текст с непарной скобкой показывается как есть: проблему сообщает панель publish gate.
 */
export function designText(template, state) {
    if (typeof template !== 'string') throw new Error('flow-ui: template property must be a string');
    if (unmatchedBraceMessage(template) !== null) return template;
    return renderTemplateInternal(template, state && typeof state === 'object' ? state : {}, null, true).text;
}

export function renderTemplate(template, state) {
    if (typeof template !== 'string') throw new Error('flow-ui: template must be a string');
    assertBalanced(template);
    return renderTemplateInternal(template, state && typeof state === 'object' ? state : {}, null);
}

/** ``visible_when``: значение по пути истинно; с ``equals`` (не null) — равно ему. */
export function isVisible(visibleWhen, state) {
    if (visibleWhen === null || visibleWhen === undefined) return true;
    if (typeof visibleWhen !== 'object' || typeof visibleWhen.path !== 'string') {
        throw new Error('flow-ui: visible_when requires path');
    }
    const value = valueAtPath(state, visibleWhen.path);
    if (visibleWhen.equals !== undefined && visibleWhen.equals !== null) {
        return JSON.stringify(value === undefined ? null : value) === JSON.stringify(visibleWhen.equals);
    }
    if (Array.isArray(value)) return value.length > 0;
    return isPresent(value) && value !== false && value !== 0;
}

/** Текст свойства блока: в рантайме — ``resolvedText``, на холсте редактора — ``designText``. */
export function blockText(ctx, template) {
    return ctx.editing ? designText(template, ctx.state) : resolvedText(template, ctx.state);
}

/**
 * URL-свойство блока (медиа, ссылка, аватар): и на холсте резолвится как в рантайме, потому что
 * неразрешённый ``{path}`` — не адрес. Пустой результат — «URL ещё нет», а не текст шаблона.
 */
export function blockUrl(ctx, template) {
    return resolvedText(template, ctx.state);
}

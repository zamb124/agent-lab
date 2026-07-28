/**
 * Сборка схемы ProseMirror из wiki-schema.json.
 *
 * Состав узлов и марок описан на сервере (apps/wiki/content/schema.py) и
 * приезжает сюда сгенерированным JSON. Здесь добавляется только отображение в
 * DOM: оно не влияет на данные, но должно существовать для каждого узла —
 * парность проверяется тестом схемы.
 */

export const PROSEMIRROR_BUNDLE_URL = '/static/core/assets/prosemirror/prosemirror-bundle.js';
export const WIKI_SCHEMA_URL = '/static/core/assets/prosemirror/wiki-schema.json';

const CALLOUT_TONE_FALLBACK = 'info';

const DOM_SPECS = Object.freeze({
    doc: null,
    text: null,
    paragraph: {
        parseDOM: [{ tag: 'p' }],
        toDOM: () => ['p', 0],
    },
    heading: {
        parseDOM: [1, 2, 3, 4, 5, 6].map((level) => ({ tag: `h${level}`, attrs: { level } })),
        toDOM: (node) => [`h${node.attrs.level}`, 0],
    },
    blockquote: {
        parseDOM: [{ tag: 'blockquote' }],
        toDOM: () => ['blockquote', 0],
    },
    code_block: {
        parseDOM: [
            {
                tag: 'pre',
                preserveWhitespace: 'full',
                getAttrs: (dom) => {
                    const dataLanguage = dom.getAttribute('data-language');
                    if (typeof dataLanguage === 'string' && dataLanguage !== '') {
                        return { language: dataLanguage };
                    }
                    const code = dom.querySelector('code');
                    const className = code instanceof Element
                        ? (code.getAttribute('class') || '')
                        : (dom.getAttribute('class') || '');
                    const match = className.match(/(?:^|\s)language-([a-zA-Z0-9_+-]+)/);
                    return { language: match ? match[1] : '' };
                },
            },
        ],
        toDOM: (node) => [
            'pre',
            { 'data-language': node.attrs.language || '' },
            ['code', node.attrs.language ? { class: `language-${node.attrs.language}` } : {}, 0],
        ],
    },
    bullet_list: {
        parseDOM: [{ tag: 'ul' }],
        toDOM: () => ['ul', 0],
    },
    ordered_list: {
        parseDOM: [
            {
                tag: 'ol',
                getAttrs: (dom) => ({ start: dom.hasAttribute('start') ? Number(dom.getAttribute('start')) : 1 }),
            },
        ],
        toDOM: (node) => (node.attrs.start === 1 ? ['ol', 0] : ['ol', { start: node.attrs.start }, 0]),
    },
    list_item: {
        parseDOM: [{ tag: 'li' }],
        toDOM: () => ['li', 0],
    },
    task_list: {
        parseDOM: [{ tag: 'ul[data-task-list]' }],
        toDOM: () => ['ul', { 'data-task-list': 'true', class: 'pm-task-list' }, 0],
    },
    task_item: {
        parseDOM: [
            {
                tag: 'li[data-task-item]',
                getAttrs: (dom) => ({ checked: dom.getAttribute('data-checked') === 'true' }),
            },
        ],
        toDOM: (node) => [
            'li',
            {
                'data-task-item': 'true',
                'data-checked': node.attrs.checked ? 'true' : 'false',
                class: 'pm-task-item',
            },
            0,
        ],
    },
    toggle: {
        parseDOM: [{ tag: 'div[data-toggle]' }],
        toDOM: () => ['div', { 'data-toggle': 'true', class: 'pm-toggle' }, 0],
    },
    toggle_summary: {
        parseDOM: [{ tag: 'div[data-toggle-summary]' }],
        toDOM: () => ['div', { 'data-toggle-summary': 'true', class: 'pm-toggle-summary' }, 0],
    },
    callout: {
        parseDOM: [
            {
                tag: 'div[data-callout]',
                getAttrs: (dom) => ({
                    tone: dom.getAttribute('data-tone') || CALLOUT_TONE_FALLBACK,
                    icon: dom.getAttribute('data-icon') || '',
                }),
            },
        ],
        toDOM: (node) => [
            'div',
            {
                'data-callout': 'true',
                'data-tone': node.attrs.tone,
                'data-icon': node.attrs.icon || '',
                class: `pm-callout pm-callout--${node.attrs.tone}`,
            },
            0,
        ],
    },
    horizontal_rule: {
        parseDOM: [{ tag: 'hr' }],
        toDOM: () => ['hr'],
    },
    footnote_definition: {
        parseDOM: [
            {
                tag: 'div[data-footnote-definition]',
                getAttrs: (dom) => ({ label: dom.getAttribute('data-label') || '' }),
            },
        ],
        toDOM: (node) => [
            'div',
            {
                'data-footnote-definition': 'true',
                'data-label': node.attrs.label,
                class: 'pm-footnote-def',
            },
            0,
        ],
    },
    footnote_reference: {
        parseDOM: [
            {
                tag: 'sup[data-footnote-reference]',
                getAttrs: (dom) => ({ label: dom.getAttribute('data-label') || '' }),
            },
        ],
        toDOM: (node) => [
            'sup',
            {
                'data-footnote-reference': 'true',
                'data-label': node.attrs.label,
                class: 'pm-footnote-ref',
            },
            node.attrs.label,
        ],
    },
    // Формула хранится и переносится точно; рендер моноширинный, без вёрстки TeX.
    math_block: {
        parseDOM: [
            {
                tag: 'div[data-math-block]',
                getAttrs: (dom) => ({ formula: dom.textContent || '' }),
            },
        ],
        toDOM: (node) => [
            'div',
            { 'data-math-block': 'true', class: 'pm-math-block' },
            node.attrs.formula,
        ],
    },
    math_inline: {
        parseDOM: [
            {
                tag: 'span[data-math-inline]',
                getAttrs: (dom) => ({ formula: dom.textContent || '' }),
            },
        ],
        toDOM: (node) => [
            'span',
            { 'data-math-inline': 'true', class: 'pm-math-inline' },
            node.attrs.formula,
        ],
    },
    image: {
        parseDOM: [
            {
                tag: 'img[src]',
                getAttrs: (dom) => ({
                    src: dom.getAttribute('src'),
                    alt: dom.getAttribute('alt') || '',
                    title: dom.getAttribute('title') || '',
                    file_id: dom.getAttribute('data-file-id') || '',
                }),
            },
        ],
        toDOM: (node) => [
            'img',
            {
                src: node.attrs.src,
                alt: node.attrs.alt,
                title: node.attrs.title || null,
                'data-file-id': node.attrs.file_id || null,
                class: 'pm-image',
            },
        ],
    },
    platform_file: {
        parseDOM: [
            {
                tag: 'div[data-platform-file]',
                getAttrs: (dom) => ({
                    file_id: dom.getAttribute('data-file-id'),
                    original_name: dom.getAttribute('data-name') || '',
                    content_type: dom.getAttribute('data-content-type') || '',
                }),
            },
        ],
        toDOM: (node) => [
            'div',
            {
                'data-platform-file': 'true',
                'data-file-id': node.attrs.file_id,
                'data-name': node.attrs.original_name || '',
                'data-content-type': node.attrs.content_type || '',
                class: 'pm-file-chip',
            },
            node.attrs.original_name || node.attrs.file_id,
        ],
    },
    platform_mention: {
        parseDOM: [
            {
                tag: 'span[data-mention]',
                getAttrs: (dom) => ({
                    mention_kind: dom.getAttribute('data-mention-kind'),
                    target_id: dom.getAttribute('data-target-id'),
                    label: dom.textContent || '',
                }),
            },
        ],
        toDOM: (node) => [
            'span',
            {
                'data-mention': 'true',
                'data-mention-kind': node.attrs.mention_kind,
                'data-target-id': node.attrs.target_id,
                class: `pm-mention pm-mention--${node.attrs.mention_kind}`,
            },
            `@${node.attrs.label || node.attrs.target_id}`,
        ],
    },
    hard_break: {
        parseDOM: [{ tag: 'br' }],
        toDOM: () => ['br'],
    },
});

const MARK_DOM_SPECS = Object.freeze({
    strong: {
        parseDOM: [{ tag: 'strong' }, { tag: 'b' }],
        toDOM: () => ['strong', 0],
    },
    em: {
        parseDOM: [{ tag: 'em' }, { tag: 'i' }],
        toDOM: () => ['em', 0],
    },
    strike: {
        parseDOM: [{ tag: 's' }, { tag: 'del' }],
        toDOM: () => ['s', 0],
    },
    code: {
        parseDOM: [{ tag: 'code' }],
        toDOM: () => ['code', 0],
    },
    highlight: {
        parseDOM: [
            { tag: 'mark', getAttrs: (dom) => ({ color: dom.getAttribute('data-color') || 'yellow' }) },
        ],
        toDOM: (mark) => ['mark', { 'data-color': mark.attrs.color }, 0],
    },
    link: {
        parseDOM: [
            {
                tag: 'a[href]',
                getAttrs: (dom) => ({
                    href: dom.getAttribute('href'),
                    title: dom.getAttribute('title') || '',
                }),
            },
        ],
        toDOM: (mark) => ['a', { href: mark.attrs.href, title: mark.attrs.title || null }, 0],
    },
});

const TABLE_NODE_NAMES = Object.freeze(['table', 'table_row', 'table_cell', 'table_header']);

function attrsFromSpec(specAttrs) {
    const attrs = {};
    for (const [name, spec] of Object.entries(specAttrs || {})) {
        attrs[name] = spec.required ? {} : { default: spec.default };
    }
    return attrs;
}

/**
 * @param {object} schemaJson — содержимое wiki-schema.json
 * @param {object} pm — модуль prosemirror-bundle
 * @returns {object} Schema
 */
export function buildWikiSchema(schemaJson, pm) {
    if (!schemaJson || typeof schemaJson !== 'object') {
        throw new Error('buildWikiSchema: schemaJson required');
    }
    if (!pm || typeof pm.Schema !== 'function') {
        throw new Error('buildWikiSchema: prosemirror bundle required');
    }

    // Таблицы описывает генератор prosemirror-tables: он задаёт colwidth и
    // поведение ячеек, повторять это вручную значило бы разойтись с плагином.
    // Выравнивание добавляется его же механизмом `cellAttributes`, иначе
    // colspan и resize пришлось бы описывать самим.
    const tableSpecs = pm.tableNodes({
        tableGroup: 'block',
        cellContent: 'block+',
        cellAttributes: {
            align: {
                default: '',
                getFromDOM: (dom) => dom.style.textAlign || dom.getAttribute('data-align') || '',
                setDOMAttr: (value, attrs) => {
                    if (value) attrs.style = `text-align: ${value}`;
                },
            },
        },
    });

    const nodes = {};
    for (const [name, spec] of Object.entries(schemaJson.nodes)) {
        if (TABLE_NODE_NAMES.includes(name)) {
            const generated = tableSpecs[name];
            if (!generated) {
                throw new Error(`buildWikiSchema: prosemirror-tables не дал узел ${name}`);
            }
            nodes[name] = generated;
            continue;
        }

        const dom = DOM_SPECS[name];
        if (dom === undefined) {
            throw new Error(`buildWikiSchema: нет DOM-описания для узла ${name}`);
        }
        const node = {
            attrs: attrsFromSpec(spec.attrs),
        };
        if (spec.group) node.group = spec.group;
        if (spec.content) node.content = spec.content;
        if (spec.marks !== null && spec.marks !== undefined) node.marks = spec.marks;
        if (spec.inline) node.inline = true;
        if (spec.atom) node.atom = true;
        if (spec.defining) node.defining = true;
        if (spec.isolating) node.isolating = true;
        if (spec.code) node.code = true;
        if (spec.draggable) node.draggable = true;
        if (spec.selectable === false) node.selectable = false;
        if (dom) {
            node.parseDOM = dom.parseDOM;
            node.toDOM = dom.toDOM;
        }
        if (name === 'code_block') node.preserveWhitespace = 'full';
        nodes[name] = node;
    }

    const marks = {};
    for (const [name, spec] of Object.entries(schemaJson.marks)) {
        const dom = MARK_DOM_SPECS[name];
        if (!dom) {
            throw new Error(`buildWikiSchema: нет DOM-описания для марки ${name}`);
        }
        const mark = {
            attrs: attrsFromSpec(spec.attrs),
            parseDOM: dom.parseDOM,
            toDOM: dom.toDOM,
        };
        if (spec.inclusive === false) mark.inclusive = false;
        if (spec.spanning === false) mark.spanning = false;
        if (spec.excludes !== null && spec.excludes !== undefined) mark.excludes = spec.excludes;
        marks[name] = mark;
    }

    return new pm.Schema({ nodes, marks });
}

let cachedRuntime = null;

/**
 * Модуль ProseMirror и схема грузятся один раз на страницу.
 *
 * Два экземпляра Schema несовместимы между собой, поэтому кеш здесь не
 * оптимизация, а условие работы: документ из одного редактора должен
 * открываться в другом.
 *
 * @returns {Promise<{pm: object, schema: object}>}
 */
export async function loadWikiEditorRuntime() {
    if (cachedRuntime) return cachedRuntime;
    const [pm, response] = await Promise.all([
        import(PROSEMIRROR_BUNDLE_URL),
        fetch(WIKI_SCHEMA_URL),
    ]);
    if (!response.ok) {
        throw new Error(`loadWikiEditorRuntime: ${response.status} ${response.statusText}`);
    }
    cachedRuntime = { pm, schema: buildWikiSchema(await response.json(), pm) };
    return cachedRuntime;
}

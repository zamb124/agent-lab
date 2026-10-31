/**
 * Сборка схемы ProseMirror из wiki-schema.json.
 *
 * Состав узлов и марок описан на сервере (apps/wiki/content/schema.py) и
 * приезжает сюда сгенерированным JSON. Здесь добавляется только отображение в
 * DOM: оно не влияет на данные, но должно существовать для каждого узла —
 * парность проверяется тестом схемы.
 */

import type { PmAttrs, PmBundleLike, PmSchemaLike } from './pm-types.js';
import { isPlainRecord } from '../events/payload.js';

export type { PmBundleLike } from './pm-types.js';

export const WIKI_SCHEMA_URL = '/static/core/assets/prosemirror/wiki-schema.json';

const CALLOUT_TONE_FALLBACK = 'info';

interface WikiNodeSpec {
    attrs?: Record<string, { required?: boolean; default?: unknown }>;
    group?: string;
    content?: string;
    marks?: string | null;
    inline?: boolean;
    atom?: boolean;
    defining?: boolean;
    isolating?: boolean;
    code?: boolean;
    draggable?: boolean;
    selectable?: boolean;
}

interface WikiMarkSpec {
    attrs?: Record<string, { required?: boolean; default?: unknown }>;
    inclusive?: boolean;
    spanning?: boolean;
    excludes?: string | null;
}

export interface WikiSchemaJson {
    nodes: Record<string, WikiNodeSpec>;
    marks: Record<string, WikiMarkSpec>;
}

export interface WikiEditorRuntime {
    pm: PmBundleLike;
    schema: PmSchemaLike;
}

interface NodeDomSpec {
    parseDOM: unknown[];
    toDOM: (node: PmAttrs) => unknown[];
}

interface MarkDomSpec {
    parseDOM: unknown[];
    toDOM: (mark: PmAttrs) => unknown[];
}

export function attrString(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

function optionalAttr(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

function cellAlign(dom: HTMLElement): string {
    if (dom.style.textAlign !== '') return dom.style.textAlign;
    return attrString(dom.getAttribute('data-align'));
}

const DOM_SPECS: Record<string, NodeDomSpec | null> = Object.freeze({
    doc: null,
    text: null,
    paragraph: {
        parseDOM: [{ tag: 'p' }],
        toDOM: () => ['p', 0],
    },
    heading: {
        parseDOM: [1, 2, 3, 4, 5, 6].map((level) => ({ tag: `h${level}`, attrs: { level } })),
        toDOM: (node: PmAttrs) => [`h${node.attrs.level}`, 0],
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
                getAttrs: (dom: HTMLElement) => {
                    const dataLanguage = dom.getAttribute('data-language');
                    if (typeof dataLanguage === 'string' && dataLanguage !== '') {
                        return { language: dataLanguage };
                    }
                    const code = dom.querySelector('code');
                    const className = code instanceof Element
                        ? attrString(code.getAttribute('class'))
                        : attrString(dom.getAttribute('class'));
                    const match = className.match(/(?:^|\s)language-([a-zA-Z0-9_+-]+)/);
                    return { language: match ? match[1] : '' };
                },
            },
        ],
        toDOM: (node: PmAttrs) => [
            'pre',
            { 'data-language': attrString(node.attrs.language) },
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
                getAttrs: (dom: HTMLElement) => ({ start: dom.hasAttribute('start') ? Number(dom.getAttribute('start')) : 1 }),
            },
        ],
        toDOM: (node: PmAttrs) => (node.attrs.start === 1 ? ['ol', 0] : ['ol', { start: node.attrs.start }, 0]),
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
                getAttrs: (dom: HTMLElement) => ({ checked: dom.getAttribute('data-checked') === 'true' }),
            },
        ],
        toDOM: (node: PmAttrs) => [
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
                getAttrs: (dom: HTMLElement) => ({
                    tone: dom.getAttribute('data-tone') || CALLOUT_TONE_FALLBACK,
                    icon: attrString(dom.getAttribute('data-icon')),
                }),
            },
        ],
        toDOM: (node: PmAttrs) => [
            'div',
            {
                'data-callout': 'true',
                'data-tone': node.attrs.tone,
                'data-icon': attrString(node.attrs.icon),
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
                getAttrs: (dom: HTMLElement) => ({ label: attrString(dom.getAttribute('data-label')) }),
            },
        ],
        toDOM: (node: PmAttrs) => [
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
                getAttrs: (dom: HTMLElement) => ({ label: attrString(dom.getAttribute('data-label')) }),
            },
        ],
        toDOM: (node: PmAttrs) => [
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
                getAttrs: (dom: HTMLElement) => ({ formula: attrString(dom.textContent) }),
            },
        ],
        toDOM: (node: PmAttrs) => [
            'div',
            { 'data-math-block': 'true', class: 'pm-math-block' },
            node.attrs.formula,
        ],
    },
    math_inline: {
        parseDOM: [
            {
                tag: 'span[data-math-inline]',
                getAttrs: (dom: HTMLElement) => ({ formula: attrString(dom.textContent) }),
            },
        ],
        toDOM: (node: PmAttrs) => [
            'span',
            { 'data-math-inline': 'true', class: 'pm-math-inline' },
            node.attrs.formula,
        ],
    },
    image: {
        parseDOM: [
            {
                tag: 'img[src]',
                getAttrs: (dom: HTMLElement) => ({
                    src: dom.getAttribute('src'),
                    alt: attrString(dom.getAttribute('alt')),
                    title: attrString(dom.getAttribute('title')),
                    file_id: attrString(dom.getAttribute('data-file-id')),
                }),
            },
        ],
        toDOM: (node: PmAttrs) => [
            'img',
            {
                src: node.attrs.src,
                alt: node.attrs.alt,
                title: optionalAttr(node.attrs.title),
                'data-file-id': optionalAttr(node.attrs.file_id),
                class: 'pm-image',
            },
        ],
    },
    platform_file: {
        parseDOM: [
            {
                tag: 'div[data-platform-file]',
                getAttrs: (dom: HTMLElement) => ({
                    file_id: dom.getAttribute('data-file-id'),
                    original_name: attrString(dom.getAttribute('data-name')),
                    content_type: attrString(dom.getAttribute('data-content-type')),
                }),
            },
        ],
        toDOM: (node: PmAttrs) => [
            'div',
            {
                'data-platform-file': 'true',
                'data-file-id': node.attrs.file_id,
                'data-name': attrString(node.attrs.original_name),
                'data-content-type': attrString(node.attrs.content_type),
                class: 'pm-file-chip',
            },
            node.attrs.original_name || node.attrs.file_id,
        ],
    },
    platform_mention: {
        parseDOM: [
            {
                tag: 'span[data-mention]',
                getAttrs: (dom: HTMLElement) => ({
                    mention_kind: dom.getAttribute('data-mention-kind'),
                    target_id: dom.getAttribute('data-target-id'),
                    label: attrString(dom.textContent),
                }),
            },
        ],
        toDOM: (node: PmAttrs) => [
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

const MARK_DOM_SPECS: Record<string, MarkDomSpec> = Object.freeze({
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
            { tag: 'mark', getAttrs: (dom: HTMLElement) => ({ color: dom.getAttribute('data-color') || 'yellow' }) },
        ],
        toDOM: (mark: PmAttrs) => ['mark', { 'data-color': mark.attrs.color }, 0],
    },
    link: {
        parseDOM: [
            {
                tag: 'a[href]',
                getAttrs: (dom: HTMLElement) => ({
                    href: dom.getAttribute('href'),
                    title: attrString(dom.getAttribute('title')),
                }),
            },
        ],
        toDOM: (mark: PmAttrs) => ['a', { href: mark.attrs.href, title: optionalAttr(mark.attrs.title) }, 0],
    },
});

const TABLE_NODE_NAMES = Object.freeze(['table', 'table_row', 'table_cell', 'table_header']);

function attrsFromSpec(specAttrs?: Record<string, { required?: boolean; default?: unknown }>): Record<string, { default?: unknown }> {
    const attrs: Record<string, { default?: unknown }> = {};
    if (specAttrs === undefined) return attrs;
    for (const [name, spec] of Object.entries(specAttrs)) {
        attrs[name] = spec.required ? {} : { default: spec.default };
    }
    return attrs;
}

/**
 * @param {object} schemaJson — содержимое wiki-schema.json
 * @param {object} pm — модуль prosemirror-lazy
 * @returns {object} Schema
 */
export function buildWikiSchema(schemaJson: WikiSchemaJson, pm: PmBundleLike): PmSchemaLike {
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
                getFromDOM: (dom: HTMLElement) => cellAlign(dom),
                setDOMAttr: (value: string, attrs: Record<string, string>) => {
                    if (value) attrs.style = `text-align: ${value}`;
                },
            },
        },
    });

    const nodes: Record<string, unknown> = {};
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
        const node: Record<string, unknown> = {
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

    const marks: Record<string, unknown> = {};
    for (const [name, spec] of Object.entries(schemaJson.marks)) {
        const dom = MARK_DOM_SPECS[name];
        if (!dom) {
            throw new Error(`buildWikiSchema: нет DOM-описания для марки ${name}`);
        }
        const mark: Record<string, unknown> = {
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

function isPmBundle(value: unknown): value is PmBundleLike {
    if (!isPlainRecord(value)) return false;
    const schema = value.Schema;
    const editorState = value.EditorState;
    const editorView = value.EditorView;
    return typeof schema === 'function'
        && typeof editorState === 'function'
        && 'create' in editorState
        && typeof editorState.create === 'function'
        && typeof editorView === 'function';
}

function isWikiSchemaJson(value: unknown): value is WikiSchemaJson {
    if (!isPlainRecord(value)) return false;
    const nodes = value.nodes;
    const marks = value.marks;
    return isPlainRecord(nodes) && isPlainRecord(marks);
}

let cachedRuntime: WikiEditorRuntime | null = null;

/**
 * Модуль ProseMirror и схема грузятся один раз на страницу.
 *
 * Два экземпляра Schema несовместимы между собой, поэтому кеш здесь не
 * оптимизация, а условие работы: документ из одного редактора должен
 * открываться в другом.
 *
 * @returns {Promise<{pm: object, schema: object}>}
 */
export async function loadWikiEditorRuntime(): Promise<WikiEditorRuntime> {
    if (cachedRuntime) return cachedRuntime;
    const [pm, response] = await Promise.all([
        import('./prosemirror-lazy.js'),
        fetch(WIKI_SCHEMA_URL),
    ]);
    if (!response.ok) {
        throw new Error(`loadWikiEditorRuntime: ${response.status} ${response.statusText}`);
    }
    if (!isPmBundle(pm)) {
        throw new Error('loadWikiEditorRuntime: prosemirror bundle is missing Schema');
    }
    const schemaJson: unknown = await response.json();
    if (!isWikiSchemaJson(schemaJson)) {
        throw new Error('loadWikiEditorRuntime: wiki schema must be an object with nodes and marks');
    }
    cachedRuntime = { pm, schema: buildWikiSchema(schemaJson, pm) };
    return cachedRuntime;
}

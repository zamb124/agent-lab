/// <reference types="node" />
/**
 * Домен редактора интерфейса: каталог из JSON Schema грамматики (фикстура ``schema.json``),
 * команды над документом, история, publish gate и каталог путей state.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { INPUT_BLOCK_TYPES } from '../../../../core/frontend/static/lib/a2a/constants.js';
import {
    CONTAINER_TYPES,
    EMPTY_DOCUMENT,
    blockCatalog,
    catalogEntry,
    commitHistory,
    createHistory,
    defaultBlock,
    documentProblems,
    duplicateBlock,
    frozenStateFields,
    hasBlockingProblems,
    insertBlock,
    insertPage,
    moveBlock,
    paletteInsertTarget,
    redoHistory,
    removeBlock,
    removePage,
    setBlockProperty,
    setPageProperty,
    statePathCatalog,
    undoHistory,
    uniqueBlockId,
    uniquePageId,
    walkPage,
    withColumns,
    wrapInSection,
} from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';
import type {
    BlockLabels,
    DocumentProblem,
    FlowUiBlock,
    FlowUiDocument,
} from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';
import { dig, prop } from '../../helpers/prop.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '../../../fixtures/flow_ui');
const schema = JSON.parse(readFileSync(join(FIXTURES, 'schema.json'), 'utf8'));
const catalog = blockCatalog(schema);
const frozen = frozenStateFields(schema);
const labels: BlockLabels = {
    tab: 'Вкладка',
    option: 'Вариант',
    text: (type: string, property: string) => `${type}.${property}`,
};

function heading(blockId: string, text = 'Заголовок'): FlowUiBlock {
    return { type: 'heading', block_id: blockId, visible_when: null, text, level: 2 };
}

function documentWith(blocks: FlowUiBlock[]): FlowUiDocument {
    return { start_page_id: 'main', pages: [{ page_id: 'main', title: '', blocks }] };
}

function blockIds(document: FlowUiDocument, pageId = 'main') {
    const page = document.pages.find((p: { page_id: string }) => p.page_id === pageId);
    if (!page) {
        throw new Error(`page ${pageId} not found`);
    }
    return walkPage(page).map((entry) => entry.block.block_id);
}

describe('interface editor catalog', () => {
    it('exposes every grammar block with group, icon and typed properties', () => {
        const types = catalog.map((entry) => entry.type);
        expect(new Set(types).size).toBe(types.length);
        for (const type of [...CONTAINER_TYPES, ...INPUT_BLOCK_TYPES, 'heading', 'text', 'button', 'html', 'slot', 'conversation']) {
            expect(types).toContain(type);
        }
        for (const entry of catalog) {
            expect(entry.group, entry.type).toBeTypeOf('string');
            expect(entry.icon, entry.type).toBeTypeOf('string');
            expect(entry.properties.some((property) => property.name === 'block_id')).toBe(true);
        }
        expect(catalogEntry(catalog, 'text_input').properties.find((property) => property.name === 'field')?.kind).toBe('state_path');
        expect(catalogEntry(catalog, 'heading').properties.find((property) => property.name === 'text')?.kind).toBe('template');
        expect(catalogEntry(catalog, 'columns').properties.find((property) => property.name === 'columns')?.kind).toBe('columns');
        expect(catalogEntry(catalog, 'html').properties.find((property) => property.name === 'height')?.kind).toBe('height');
        expect(catalogEntry(catalog, 'agent_identity').properties.find((property) => property.name === 'image_url')?.kind).toBe('image_url');
        expect(catalogEntry(catalog, 'heading').properties.find((property) => property.name === 'span')).toMatchObject({
            kind: 'integer', minimum: 1, maximum: 12, default: 12,
        });
        expect(catalogEntry(catalog, 'heading').properties.find((property) => property.name === 'align')).toMatchObject({
            kind: 'enum', enum: ['start', 'center', 'end'], default: 'start',
        });
        expect(catalogEntry(catalog, 'heading').properties.find((property) => property.name === 'valign')).toMatchObject({
            kind: 'enum', enum: ['start', 'center', 'end'], default: 'start',
        });
        expect(() => catalogEntry(catalog, 'grid')).toThrow(/unknown block type/);
    });

    it('builds valid default blocks for every type', () => {
        const page = { page_id: 'main', title: '', blocks: [] };
        for (const entry of catalog) {
            const block = defaultBlock(entry, uniqueBlockId(page, entry.type), labels);
            expect(block.type).toBe(entry.type);
            const problems = documentProblems(documentWith([block]), catalog, frozen)
                .filter((problem) => problem.code !== 'inputs_without_action');
            expect(problems, entry.type).toEqual([]);
        }
        const columns = withColumns(catalogEntry(catalog, 'columns'), 'cols', 3, labels);
        expect(prop(columns, 'columns') && (columns.columns as readonly { width: number }[]).map((column) => column.width)).toEqual([4, 4, 4]);
        expect(frozen.has('task_id')).toBe(true);
    });
});

describe('interface editor commands', () => {
    it('inserts, moves, wraps, duplicates and removes blocks by container key', () => {
        let document = insertBlock(EMPTY_DOCUMENT, 'main', 'page', 0, heading('a'));
        document = insertBlock(document, 'main', 'page', 99, heading('b'));
        const section = defaultBlock(catalogEntry(catalog, 'section'), 'box', labels);
        document = insertBlock(document, 'main', 'page', 1, section);
        expect(blockIds(document)).toEqual(['a', 'box', 'b']);

        document = moveBlock(document, 'main', 'b', 'box', 0);
        expect(blockIds(document)).toEqual(['a', 'box', 'b']);
        expect(dig(document, 'pages', '0', 'blocks', '1', 'blocks') as unknown[] && (dig(document, 'pages', '0', 'blocks', '1', 'blocks') as FlowUiBlock[]).map((block) => block.block_id)).toEqual(['b']);
        expect(() => moveBlock(document, 'main', 'box', 'box', 0)).toThrow(/into itself/);

        document = wrapInSection(document, 'main', 'a');
        expect(document.pages[0]?.blocks[0]?.type).toBe('section');
        expect(dig(document, 'pages', '0', 'blocks', '0', 'blocks', '0', 'block_id')).toBe('a');

        document = duplicateBlock(document, 'main', 'box');
        expect(blockIds(document)).toEqual(['section', 'a', 'box', 'b', 'section-2', 'heading']);

        document = removeBlock(document, 'main', 'section-2');
        expect(blockIds(document)).toEqual(['section', 'a', 'box', 'b']);
        expect(() => removeBlock(document, 'main', 'nope')).toThrow(/unknown block/);
        expect(EMPTY_DOCUMENT.pages[0]?.blocks).toEqual([]);
    });

    it('renames block ids only when unique on the page', () => {
        const document = documentWith([heading('a'), heading('b')]);
        expect(() => setBlockProperty(document, 'main', 'a', 'block_id', 'b')).toThrow(/already used/);
        const renamed = setBlockProperty(document, 'main', 'a', 'block_id', 'title');
        expect(blockIds(renamed)).toEqual(['title', 'b']);
        expect(setBlockProperty(document, 'main', 'a', 'text', 'x').pages[0]?.blocks[0]?.text).toBe('x');
        expect(document.pages[0]?.blocks[0]?.text).toBe('Заголовок');
        const button = defaultBlock(catalogEntry(catalog, 'button'), 'go', labels);
        const patched = setBlockProperty(documentWith([button]), 'main', 'go', 'click_target', {
            action: null, page_id: 'done', url: '',
        });
        expect(patched.pages[0]?.blocks[0]).toMatchObject({ action: null, page_id: 'done', url: '' });
    });

    it('manages pages and keeps start page and link targets consistent', () => {
        let document = insertPage(EMPTY_DOCUMENT, { page_id: uniquePageId(EMPTY_DOCUMENT), title: 'Вторая', blocks: [] });
        expect(document.pages.map((page) => page.page_id)).toEqual(['main', 'page-2']);
        const link = { ...defaultBlock(catalogEntry(catalog, 'link'), 'go', labels), url: '', page_id: 'page-2' };
        const button = { ...defaultBlock(catalogEntry(catalog, 'button'), 'next', labels), action: null, page_id: 'page-2', url: '' };
        document = insertBlock(document, 'main', 'page', 0, link);
        document = insertBlock(document, 'main', 'page', 1, button);
        document = setPageProperty(document, 'page-2', 'page_id', 'done');
        expect(document.pages[0]?.blocks[0]?.page_id).toBe('done');
        expect(document.pages[0]?.blocks[1]?.page_id).toBe('done');
        document = setPageProperty(document, 'main', 'page_id', 'start');
        expect(document.start_page_id).toBe('start');
        expect(() => setPageProperty(document, 'done', 'page_id', 'start')).toThrow(/already used/);
        document = removePage(document, 'start');
        expect(document.start_page_id).toBe('done');
        expect(() => removePage(document, 'done')).toThrow(/at least one page/);
    });
});

describe('paletteInsertTarget', () => {
    it('inserts into the selected container, after a leaf, or at the end of the page', () => {
        const page = {
            page_id: 'main',
            title: '',
            blocks: [
                heading('top'),
                {
                    type: 'columns',
                    block_id: 'cols',
                    columns: [
                        { width: 6, blocks: [heading('in-col')] },
                        { width: 6, blocks: [] },
                    ],
                },
                { type: 'section', block_id: 'box', title: '', blocks: [heading('in-box')] },
                {
                    type: 'tabs',
                    block_id: 'tabs',
                    tabs: [
                        { title: '1', blocks: [heading('in-tab')] },
                        { title: '2', blocks: [] },
                    ],
                },
            ],
        };
        expect(paletteInsertTarget(page, '')).toEqual({ containerKey: 'page', index: 4 });
        expect(paletteInsertTarget(page, 'top')).toEqual({ containerKey: 'page', index: 1 });
        expect(paletteInsertTarget(page, 'cols')).toEqual({ containerKey: 'cols/1', index: 0 });
        expect(paletteInsertTarget(page, 'in-col')).toEqual({ containerKey: 'cols/0', index: 1 });
        expect(paletteInsertTarget(page, 'box')).toEqual({ containerKey: 'box', index: 1 });
        expect(paletteInsertTarget(page, 'tabs')).toEqual({ containerKey: 'tabs/1', index: 0 });
        const filled = {
            page_id: 'main',
            title: '',
            blocks: [{
                type: 'columns',
                block_id: 'cols',
                columns: [
                    { width: 6, blocks: [heading('a')] },
                    { width: 6, blocks: [heading('b')] },
                ],
            }],
        };
        expect(paletteInsertTarget(filled, 'cols')).toEqual({ containerKey: 'cols/0', index: 1 });
    });
});

describe('interface editor history', () => {
    it('coalesces consecutive edits with the same key and clears redo on new commits', () => {
        let history = createHistory(documentWith([heading('a', '')]));
        history = commitHistory(history, documentWith([heading('a', 'З')]), 'a:text');
        history = commitHistory(history, documentWith([heading('a', 'За')]), 'a:text');
        expect(history.past).toHaveLength(1);
        history = commitHistory(history, documentWith([heading('a', 'За'), heading('b')]));
        expect(history.past).toHaveLength(2);
        history = undoHistory(history);
        expect(blockIds(history.present)).toEqual(['a']);
        history = redoHistory(history);
        expect(blockIds(history.present)).toEqual(['a', 'b']);
        history = undoHistory(undoHistory(history));
        expect(history.present.pages[0]?.blocks[0]?.text).toBe('');
        expect(undoHistory(history)).toBe(history);
        history = commitHistory(history, documentWith([heading('c')]));
        expect(history.future).toEqual([]);
    });
});

describe('interface editor publish gate', () => {
    it('reports blocking problems and passes a well-formed form', () => {
        const email = { ...defaultBlock(catalogEntry(catalog, 'text_input'), 'email', labels), field: 'email', required: true };
        const send = { ...defaultBlock(catalogEntry(catalog, 'button'), 'send', labels), label: 'Отправить {email}' };
        const valid = documentWith([heading('title', 'Заявка {?customer.name}'), email, send]);
        expect(documentProblems(valid, catalog, frozen)).toEqual([]);

        const broken = {
            start_page_id: 'missing',
            pages: [{
                page_id: 'Main Page',
                title: '',
                blocks: [
                    { ...email, field: 'task_id' },
                    { ...email, block_id: 'email' },
                    { ...heading('h', 'Итого {task_id}') },
                    { type: 'grid', block_id: 'g' },
                    { ...defaultBlock(catalogEntry(catalog, 'link'), 'lnk', labels), url: '', page_id: 'nowhere' },
                ],
            }],
        };
        const codes = documentProblems(broken, catalog, frozen).map((problem) => problem.code);
        expect(codes).toEqual(expect.arrayContaining([
            'start_page_missing',
            'page_id_invalid',
            'state_path_frozen',
            'block_id_duplicate',
            'template_path_frozen',
            'block_type_unknown',
            'link_page_missing',
            'inputs_without_action',
        ]));
        expect(hasBlockingProblems(documentProblems(broken, catalog, frozen))).toBe(true);
        const warnProblem: DocumentProblem = { code: 'columns_overflow', severity: 'warning', pageId: null, blockId: null, property: null, params: {} };
        expect(hasBlockingProblems([warnProblem])).toBe(false);
    });

    it('blocks unbalanced templates in every template property while typing, like the backend gate', () => {
        const select = {
            ...defaultBlock(catalogEntry(catalog, 'select'), 'plan', labels),
            field: 'plan',
            options: [{ value: 'a', label: 'Тариф {name' }],
            action: { name: 'pick', payload: {} },
        };
        const conversation = {
            ...defaultBlock(catalogEntry(catalog, 'conversation'), 'conversation', labels),
        };
        const settings = prop(conversation, 'settings');
        if (typeof settings !== 'object' || settings === null) {
            throw new Error('conversation.settings must be an object');
        }
        conversation.settings = { ...settings, greeting: 'Привет }', suggested_prompts: ['{a}', '{b'] };
        const typing = documentWith([heading('h', 'Итого {total'), heading('ok', 'Ок {total-1}'), select, conversation]);
        const problems = documentProblems(typing, catalog, frozen).filter((problem) => problem.code === 'template_unbalanced');
        expect(problems.map((problem) => [problem.blockId, problem.params.value])).toEqual([
            ['h', 'Итого {total'],
            ['plan', 'Тариф {name'],
            ['conversation', 'Привет }'],
            ['conversation', '{b'],
        ]);
        expect(problems.every((problem) => problem.severity === 'error')).toBe(true);
        expect(documentProblems(documentWith([heading('ok', 'Ок {total-1} { "json": 1 }')]), catalog, frozen)).toEqual([]);
    });
});

describe('interface editor state path catalog', () => {
    it('merges dataflow descriptors, sample state and interface fields without duplicates', () => {
        const document = documentWith([{ ...defaultBlock(catalogEntry(catalog, 'text_input'), 'email', labels), field: 'email' }]);
        const paths = statePathCatalog({
            dataflow: {
                variables: [{ path: 'plan', type: 'string', source: 'variable', protected: false }],
                nodes: { llm_1: { output_state: [{ path: 'content', type: 'string', source: 'node', protected: false }], incoming_state: [{ path: 'task_id', type: 'string', source: 'system', protected: true }] } },
            },
            sampleState: { email: 'a@b.c', total: 12 },
            document,
        });
        expect(paths.map((entry) => entry.path)).toEqual(['content', 'email', 'plan', 'task_id', 'total']);
        expect(paths.find((entry) => entry.path === 'email')).toEqual({ path: 'email', type: 'string', source: 'preview_state', protected: false });
        expect(paths.find((entry) => entry.path === 'task_id')?.protected).toBe(true);
    });
});

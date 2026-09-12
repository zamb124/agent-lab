/**
 * FlowUIStore: корнер-кейсы поверх базового спека — смена документа с открытой страницей,
 * Task snapshot против стрима, свёртка state нескольких Tasks, поля html-блоков,
 * навигация на удалённую страницу, границы входа.
 */

import { describe, expect, it } from 'vitest';

import { FlowUIStore, iterBlocks } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-store.js';

const UI_MEDIA_TYPE = 'application/vnd.platform.ui+json';
const JSON_PATCH_MEDIA_TYPE = 'application/json-patch+json';

function documentWith(blocks, extraPages = []) {
    return {
        start_page_id: 'main',
        pages: [{ page_id: 'main', title: 'Main', blocks }, ...extraPages],
    };
}

function snapshotPart(state) {
    return { data: state, mediaType: 'application/json' };
}

function patchPart(operations) {
    return { data: operations, mediaType: JSON_PATCH_MEDIA_TYPE };
}

function uiPart(event) {
    return { data: event, mediaType: UI_MEDIA_TYPE };
}

function artifactFrame(taskId, artifactId, parts, { append = true, lastChunk = false } = {}) {
    return {
        result: {
            artifactUpdate: {
                taskId,
                contextId: 'ctx-1',
                append,
                lastChunk,
                artifact: { artifactId, name: artifactId, parts },
            },
        },
    };
}

function statusFrame(taskId, state) {
    return { result: { statusUpdate: { taskId, contextId: 'ctx-1', status: { state } } } };
}

function taskSnapshotFrame(taskId, artifacts, state = 'TASK_STATE_COMPLETED') {
    return {
        result: {
            task: {
                id: taskId,
                contextId: 'ctx-1',
                status: { state },
                artifacts,
                history: [],
            },
        },
    };
}

describe('FlowUIStore documents', () => {
    it('setInterface requires a document and keeps the whole response', () => {
        const store = new FlowUIStore();
        expect(() => store.setInterface(null)).toThrow(/requires document/);
        expect(() => store.setInterface({ viewer: {} })).toThrow(/requires document/);
        const response = { document: documentWith([]), viewer: { auth_mode: 'platform' }, look: null };
        store.setInterface(response);
        expect(store.interface).toBe(response);
        expect(store.document).toBe(response.document);
        expect(store.pageId).toBe('main');
    });

    it('keeps the open page across document updates and falls back to start page when it disappears', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([], [{ page_id: 'second', title: '', blocks: [] }]));
        store.navigate('second');
        store.setDocument(documentWith([{ type: 'divider', block_id: 'd' }], [{ page_id: 'second', title: '', blocks: [] }]));
        expect(store.pageId).toBe('second');
        store.setDocument(documentWith([]));
        expect(store.pageId).toBe('main');
        // Открытая страница ещё существует: start_page_id при обновлении не проверяется
        store.setDocument({ start_page_id: 'nope', pages: [{ page_id: 'main', blocks: [] }] });
        expect(store.pageId).toBe('main');
        expect(() => new FlowUIStore().setDocument({ start_page_id: 'nope', pages: [{ page_id: 'main', blocks: [] }] })).toThrow(
            /start_page_id "nope" is not a page/,
        );
        expect(() => store.setDocument({ start_page_id: 'main' })).toThrow(/requires pages/);
        expect(() => store.setDocument([])).toThrow(/requires pages/);
    });

    it('rejects non-function listeners and unsubscribes cleanly', () => {
        const store = new FlowUIStore();
        expect(() => store.subscribe(null)).toThrow(/listener must be a function/);
        const seen = [];
        const unsubscribe = store.subscribe((source) => seen.push(source));
        store.emitChange();
        unsubscribe();
        unsubscribe();
        store.emitChange();
        expect(seen).toEqual([store]);
    });

    it('finds conversation settings anywhere in the tree and returns an empty object otherwise', () => {
        const store = new FlowUIStore();
        expect(store.conversationSettings()).toEqual({});
        store.setDocument(documentWith([{ type: 'text', block_id: 't', markdown: 'x' }]));
        expect(store.conversationSettings()).toEqual({});
        store.setDocument(
            documentWith([
                {
                    type: 'section',
                    block_id: 's',
                    blocks: [{ type: 'conversation', block_id: 'conversation', settings: { greeting: 'Привет' } }],
                },
            ]),
        );
        expect(store.conversationSettings()).toEqual({ greeting: 'Привет' });
        store.setDocument(documentWith([{ type: 'conversation', block_id: 'conversation', settings: null }]));
        expect(store.conversationSettings()).toEqual({});
    });
});

describe('FlowUIStore fields', () => {
    const blocks = [
        { type: 'text_input', block_id: 'name', field: 'name', required: true },
        { type: 'switch', block_id: 'agree', field: 'agree', required: true },
        { type: 'number_input', block_id: 'qty', field: 'qty' },
        { type: 'html', block_id: 'custom', field: 'custom.value', source: '<p></p>' },
        { type: 'html', block_id: 'view', field: null, source: '<p></p>' },
        { type: 'text', block_id: 't', markdown: 'no field' },
        { type: 'section', block_id: 's', blocks: [{ type: 'select', block_id: 'plan', field: 'plan', options: [] }] },
    ];

    it('treats html blocks with a field as inputs and walks containers', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith(blocks));
        expect(store.inputBlocks().map((block) => block.block_id)).toEqual(['name', 'agree', 'qty', 'custom', 'plan']);
    });

    it('collects zero and false as real values, keeps explicit empty edits and reports required gaps', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith(blocks));
        store.setState({ name: 'Ann', agree: false, qty: 0, custom: { value: [] }, plan: null });
        expect(store.collectFields()).toEqual({
            fields: { name: 'Ann', agree: false, qty: 0 },
            missing: new Set(),
        });
        store.setEdit('name', '');
        store.setEdit('plan', undefined);
        expect(store.collectFields()).toEqual({
            fields: { name: '', agree: false, qty: 0, plan: null },
            missing: new Set(['name']),
        });
        store.clearEdits(['name', 'plan', 'never-edited']);
        expect(store.edits).toEqual({});
        expect(() => store.setEdit('', 'x')).toThrow(/field is required/);
        expect(() => store.setEdit(5, 'x')).toThrow(/field is required/);
        expect(() => store.setState(null)).toThrow(/state must be an object/);
        expect(() => store.setState([])).toThrow(/state must be an object/);
    });

    it('fieldValue reads nested state paths and prefers edits even when the edit is null', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith(blocks));
        store.setState({ custom: { value: 'from-state' } });
        expect(store.fieldValue('custom.value')).toBe('from-state');
        store.setEdit('custom.value', null);
        expect(store.fieldValue('custom.value')).toBeNull();
        expect(store.fieldValue('unknown')).toBeUndefined();
    });
});

describe('FlowUIStore view state', () => {
    it('keeps field errors, uploading and block-local state observable and clears an error on edit', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([]));
        let changes = 0;
        store.subscribe(() => { changes += 1; });
        store.setFieldErrors(new Set(['name', 'email']));
        expect([...store.fieldErrors]).toEqual(['name', 'email']);
        expect(changes).toBe(1);
        store.setEdit('name', 'Анна');
        expect([...store.fieldErrors]).toEqual(['email']);
        store.setEdit('other', 'x');
        expect([...store.fieldErrors]).toEqual(['email']);
        store.setUploading('avatar', true);
        expect(store.uploading.has('avatar')).toBe(true);
        store.setUploading('avatar', false);
        expect(store.uploading.size).toBe(0);
        const local = store.localState('tabs');
        local.tab = 2;
        expect(store.localState('tabs')).toBe(local);
        expect(changes).toBe(5);
        store.resetContext('ctx');
        expect(store.fieldErrors.size).toBe(0);
        expect(store.uploading.size).toBe(0);
        expect(store.localState('tabs').tab).toBe(undefined);
    });
});

describe('FlowUIStore tasks and frames', () => {
    it('folds state across tasks in order and a Task snapshot rebuilds state and slots', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([{ type: 'slot', block_id: 'result' }], [{ page_id: 'done', title: '', blocks: [] }]));
        store.applyFrame(artifactFrame('task-1', 'state', [snapshotPart({ a: 1 })]));
        store.applyFrame(artifactFrame('task-1', 'state', [patchPart([{ op: 'add', path: '/b', value: 2 }])]));
        store.applyFrame(artifactFrame('task-2', 'state', [patchPart([{ op: 'remove', path: '/a' }])]));
        expect(store.state).toEqual({ b: 2 });
        expect(store.orderedTasks().map((task) => task.id)).toEqual(['task-1', 'task-2']);

        const rebuilt = new FlowUIStore();
        rebuilt.setDocument(documentWith([{ type: 'slot', block_id: 'result' }], [{ page_id: 'done', title: '', blocks: [] }]));
        const applied = rebuilt.applyFrame(
            taskSnapshotFrame('task-9', [
                { artifactId: 'state', name: 'state', parts: [snapshotPart({ x: 1 })] },
                {
                    artifactId: 'ui',
                    name: 'ui',
                    parts: [
                        uiPart({ kind: 'render', slot_id: 'result', blocks: [{ type: 'text', block_id: 'r', markdown: 'ok' }] }),
                        uiPart({ kind: 'navigate', page_id: 'done' }),
                    ],
                },
            ]),
        );
        expect(applied.frameKind).toBe('task');
        expect(applied.uiEvents).toEqual([]);
        expect(rebuilt.state).toEqual({ x: 1 });
        expect(rebuilt.slots.result.map((block) => block.block_id)).toEqual(['r']);
        expect(rebuilt.pageId).toBe('done');
        expect(rebuilt.contextId).toBe('ctx-1');
        expect(rebuilt.task('task-9').status.state).toBe('TASK_STATE_COMPLETED');
        expect(rebuilt.task('missing')).toBeNull();
        expect(rebuilt.task(null)).toBeNull();
    });

    it('ignores navigation to pages removed from the document and re-renders slots by id', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([{ type: 'slot', block_id: 'result' }]));
        store.applyFrame(artifactFrame('task-1', 'ui', [uiPart({ kind: 'navigate', page_id: 'gone' })]));
        expect(store.pageId).toBe('main');
        store.applyFrame(
            artifactFrame('task-1', 'ui', [
                uiPart({ kind: 'render', slot_id: 'result', blocks: [{ type: 'text', block_id: 'v1', markdown: '1' }] }),
            ]),
        );
        store.applyFrame(
            artifactFrame('task-1', 'ui', [
                uiPart({ kind: 'render', slot_id: 'result', blocks: [{ type: 'text', block_id: 'v2', markdown: '2' }] }),
                uiPart({ kind: 'render', slot_id: 'other', blocks: [{ type: 'text', block_id: 'o', markdown: 'o' }] }),
            ]),
        );
        expect(Object.keys(store.slots)).toEqual(['result', 'other']);
        expect(store.slots.result.map((block) => block.block_id)).toEqual(['v2']);
    });

    it('pending survives message/status/artifact frames and is released only by a Task snapshot', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([]));
        store.setPending({ text: 'hi', files: [], action: null, messageId: 'm1' });
        const messageApplied = store.applyFrame({
            result: { message: { messageId: 'm1', role: 'ROLE_USER', parts: [{ text: 'hi' }], contextId: 'ctx-1' } },
        });
        expect(messageApplied.frameKind).toBe('message');
        expect(store.pending).not.toBeNull();
        store.applyFrame(statusFrame('task-1', 'TASK_STATE_WORKING'));
        expect(store.pending).not.toBeNull();
        store.applyFrame(artifactFrame('task-1', 'response', [{ text: 'partial' }]));
        expect(store.pending).not.toBeNull();
        expect(store.turnActive).toBe(true);
        store.applyFrame({
            result: {
                task: {
                    id: 'task-1',
                    contextId: 'ctx-1',
                    status: { state: 'TASK_STATE_SUBMITTED' },
                    history: [{ messageId: 'm1', role: 'ROLE_USER', taskId: 'task-1', parts: [{ text: 'hi' }] }],
                    artifacts: [],
                },
            },
        });
        expect(store.pending).toBeNull();
        store.activeTaskId = 'task-1';
        expect(store.taskRunning).toBe(true);
        for (const settled of ['TASK_STATE_INPUT_REQUIRED', 'TASK_STATE_AUTH_REQUIRED', 'TASK_STATE_COMPLETED', 'TASK_STATE_FAILED', 'TASK_STATE_REJECTED']) {
            const single = new FlowUIStore();
            single.setDocument(documentWith([]));
            single.applyFrame(statusFrame('t', settled));
            single.activeTaskId = 't';
            expect(single.taskRunning, settled).toBe(false);
            expect(single.turnActive, settled).toBe(false);
        }
        store.activeTaskId = 'unknown';
        expect(store.taskRunning).toBe(false);
    });

    it('surfaces stream errors and malformed frames instead of swallowing them', () => {
        const store = new FlowUIStore();
        store.setDocument(documentWith([]));
        expect(() => store.applyFrame({ error: { code: -32000, message: 'boom' } })).toThrow('boom');
        expect(() => store.applyFrame({ result: { artifactUpdate: { taskId: 't', contextId: 'ctx-1', artifact: { parts: [] } } } })).toThrow(
            /artifact update has no artifactId/,
        );
        expect(() => store.applyFrame({ result: { task: { status: { state: 'TASK_STATE_WORKING' } } } })).toThrow(/Task snapshot has no id/);
        const empty = store.applyFrame({ result: {} });
        expect(empty.frameKind).toBeNull();
        expect(empty.uiEvents).toEqual([]);
    });

    it('resetContext without a document only notifies and keeps the new context id', () => {
        const store = new FlowUIStore();
        let calls = 0;
        store.subscribe(() => { calls += 1; });
        store.setError(new Error('x'));
        store.resetContext('ctx-new');
        expect(store.contextId).toBe('ctx-new');
        expect(store.error).toBeNull();
        expect(store.document).toBeNull();
        expect(store.pageId).toBeNull();
        expect(calls).toBe(2);
    });
});

describe('iterBlocks', () => {
    it('tolerates non-array input and containers without children', () => {
        expect([...iterBlocks(null)]).toEqual([]);
        expect([...iterBlocks(undefined)]).toEqual([]);
        expect([...iterBlocks([{ type: 'section', block_id: 's', blocks: [] }])].map((block) => block.block_id)).toEqual(['s']);
        expect([...iterBlocks([{ type: 'columns', block_id: 'c', columns: [] }])].map((block) => block.block_id)).toEqual(['c']);
        expect([...iterBlocks([{ type: 'tabs', block_id: 't', tabs: [] }])].map((block) => block.block_id)).toEqual(['t']);
    });
});

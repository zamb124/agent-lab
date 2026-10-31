/// <reference types="node" />
/**
 * FlowUIStore: единый источник правды рантайма — документ, страница, проекция state
 * из артефакта ``state``, слоты из артефакта ``ui``, локальные правки полей.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { INPUT_BLOCK_TYPES } from '../../../../core/frontend/static/lib/a2a/constants.js';
import { FlowUIStore, iterBlocks } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-store.js';
import type { FlowUiBlock, FlowUiRecord } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-store.js';
import { prop } from '../../helpers/prop.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '../../../fixtures/flow_ui');
const artifacts = JSON.parse(readFileSync(join(FIXTURES, 'ui_artifacts.json'), 'utf8'));

function artifactFrame(artifactId: string, parts: unknown[], { taskId = 'task-1', append = true, lastChunk = false }: { taskId?: string; append?: boolean; lastChunk?: boolean } = {}): FlowUiRecord {
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

function storeWithDocument() {
    const store = new FlowUIStore();
    store.setDocument(structuredClone(artifacts.document));
    return store;
}

describe('FlowUIStore document and pages', () => {
    it('opens on start_page_id and navigates only to known pages', () => {
        const store = storeWithDocument();
        expect(store.pageId).toBe('main');
        store.navigate('done');
        expect(store.pageId).toBe('done');
        expect(() => store.navigate('missing')).toThrow(/unknown page_id/);
    });

    it('rejects documents without pages and notifies subscribers on change', () => {
        const store = new FlowUIStore();
        expect(() => Reflect.apply(store.setDocument, store, [{ pages: [] }])).toThrow(/requires pages/);
        let calls = 0;
        const unsubscribe = store.subscribe(() => { calls += 1; });
        store.setDocument(structuredClone(artifacts.document));
        unsubscribe();
        store.navigate('done');
        expect(calls).toBe(1);
    });
});

describe('FlowUIStore state artifact', () => {
    it('folds json snapshot and json patch parts in task order', () => {
        const store = storeWithDocument();
        store.applyFrame(artifactFrame('state', [artifacts.parts[0]]));
        expect(store.state).toEqual({ email: 'a@b.c', total: 1200 });
        store.applyFrame(artifactFrame('state', [artifacts.parts[1]]));
        expect(store.state).toEqual({ email: 'a@b.c', total: 1500 });
        expect(store.contextId).toBe('ctx-1');
    });

    it('rejects state parts with foreign media types', () => {
        const store = storeWithDocument();
        expect(() => store.applyFrame(artifactFrame('state', [{ text: 'not state' }]))).toThrow(/only json snapshot or json patch/);
    });
});

describe('FlowUIStore ui artifact', () => {
    it('renders into slots and navigates from ui events', () => {
        const store = storeWithDocument();
        const applied = store.applyFrame(artifactFrame('ui', [artifacts.parts[2], artifacts.parts[3]]));
        expect(applied.uiEvents.map((event) => event.kind)).toEqual(['render', 'navigate']);
        const resultBlocks = prop(store.slots, 'result');
        if (!Array.isArray(resultBlocks)) {
            throw new Error('slots.result must be an array');
        }
        expect(resultBlocks.map((block: FlowUiBlock) => block.block_id)).toEqual(['summary']);
        expect(store.pageId).toBe('done');
    });

    it('rejects ui artifact parts that are not ui events', () => {
        const store = storeWithDocument();
        expect(() => store.applyFrame(artifactFrame('ui', [{ text: 'plain' }]))).toThrow(/must be a ui event/);
    });

    it('conversation renders are not stored as slots', () => {
        const store = storeWithDocument();
        store.applyFrame(artifactFrame('ui', [{
            data: { kind: 'render', slot_id: 'conversation', blocks: [{ block_id: 'r', type: 'text', markdown: 'hi' }] },
            mediaType: 'application/vnd.platform.ui+json',
        }]));
        expect(store.slots).toEqual({});
    });
});

describe('FlowUIStore fields', () => {
    it('collects edited and state-backed input values and reports missing required fields', () => {
        const store = storeWithDocument();
        expect(store.inputBlocks().map((block) => block.block_id)).toEqual(['email']);
        expect(store.collectFields()).toEqual({ fields: {}, missing: new Set(['email']) });
        store.setState({ email: 'from@state' });
        expect(store.fieldValue('email')).toBe('from@state');
        store.setEdit('email', 'typed@local');
        expect(store.fieldValue('email')).toBe('typed@local');
        expect(store.collectFields()).toEqual({ fields: { email: 'typed@local' }, missing: new Set() });
        store.clearEdits(['email']);
        expect(store.fieldValue('email')).toBe('from@state');
    });

    it('turnActive follows the active Task state, not the HTTP stream', () => {
        const store = storeWithDocument();
        const statusFrame = (state: string): FlowUiRecord => ({
            result: { statusUpdate: { taskId: 'task-1', contextId: 'ctx-1', status: { state } } },
        });
        expect(store.turnActive).toBe(false);
        store.setPending({ text: 'hi', files: [], action: null, messageId: 'm1' });
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
        store.applyFrame(statusFrame('TASK_STATE_WORKING'));
        store.activeTaskId = 'task-1';
        expect(store.turnActive).toBe(true);
        store.setStreaming(true);
        store.applyFrame(statusFrame('TASK_STATE_CANCELED'));
        expect(store.turnActive).toBe(false);
        expect(store.streaming).toBe(true);
        let calls = 0;
        const unsubscribe = store.subscribe(() => { calls += 1; });
        store.setStreaming(true);
        store.setStreaming(false);
        unsubscribe();
        expect(calls).toBe(1);
        expect(store.streaming).toBe(false);
    });

    it('resetContext drops state, edits, slots and returns to the start page', () => {
        const store = storeWithDocument();
        store.applyFrame(artifactFrame('state', [artifacts.parts[0]]));
        store.applyFrame(artifactFrame('ui', [artifacts.parts[2], artifacts.parts[3]]));
        store.setEdit('email', 'x');
        store.resetContext('ctx-2');
        expect(store.contextId).toBe('ctx-2');
        expect(store.state).toEqual({});
        expect(store.edits).toEqual({});
        expect(store.slots).toEqual({});
        expect(store.pageId).toBe('main');
        expect(store.orderedTasks()).toEqual([]);
    });
});

describe('flow-ui block iteration', () => {
    it('walks nested containers depth-first', () => {
        const blocks = [
            { block_id: 'a', type: 'section', blocks: [{ block_id: 'b', type: 'text', markdown: 'x' }] },
            { block_id: 'c', type: 'columns', columns: [{ blocks: [{ block_id: 'd', type: 'text_input', field: 'f' }] }] },
            { block_id: 'e', type: 'tabs', tabs: [{ tab_id: 't', title: 'T', blocks: [{ block_id: 'g', type: 'switch', field: 'h' }] }] },
        ];
        expect([...iterBlocks(blocks)].map((block) => block.block_id)).toEqual(['a', 'b', 'c', 'd', 'e', 'g']);
        expect(INPUT_BLOCK_TYPES.has('text_input')).toBe(true);
        expect(INPUT_BLOCK_TYPES.has('button')).toBe(false);
    });
});

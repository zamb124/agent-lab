/**
 * Граничные случаи протокольного слоя: дедупликация кадров по platformEventId и коллизии,
 * глубокое слияние metadata статусов, смешение camel/snake идентификаторов артефактов,
 * неполный scope кадра, валидация file Parts, UUID v4, редкие схемы свойств редактора.
 */

import { describe, expect, it } from 'vitest';

import { propertyKind, replacePageBlocks } from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';
import type { A2aFileSource } from '@platform/lib/a2a/a2a-codec.js';
import { prop } from '../../helpers/prop.js';
import { buildA2aFileParts, createProtocolId, randomUuid } from '@platform/lib/a2a/a2a-codec.js';
import {
    applyA2AFrame,
    createA2ATaskAccumulator,
    serializableTask,
    taskBoundary,
} from '@platform/lib/a2a/a2a-task-accumulator.js';

function statusUpdate(taskId: string, state: string, extra: Record<string, unknown> = {}) {
    return { result: { statusUpdate: { taskId, contextId: 'c1', status: { state }, ...extra } } };
}

describe('a2a task accumulator edge cases', () => {
    it('rejects error frames, ignores unknown frames and passes messages through as copies', () => {
        const accumulator = createA2ATaskAccumulator();
        expect(() => applyA2AFrame(accumulator, { error: { code: -32000, message: 'boom' } })).toThrow('boom');
        expect(() => applyA2AFrame(accumulator, { error: {} })).toThrow('A2A stream error');
        expect(applyA2AFrame(accumulator, { result: { unknown: {} } })).toEqual({ accumulator, changedTaskId: null, frameKind: null });
        expect(applyA2AFrame(accumulator, null)).toEqual({ accumulator, changedTaskId: null, frameKind: null });
        const message = { messageId: 'm1', role: 'ROLE_AGENT', parts: [{ text: 'hi' }] };
        const applied = applyA2AFrame(accumulator, { result: { message } });
        expect(applied).toMatchObject({ changedTaskId: null, frameKind: 'message' });
        expect(applied.message).toEqual(message);
        expect(applied.message).not.toBe(message);
        expect(accumulator.taskOrder).toEqual([]);
    });

    it('deduplicates redelivered events by platformEventId and refuses a different payload under the same id', () => {
        const accumulator = createA2ATaskAccumulator();
        const first = statusUpdate('t1', 'TASK_STATE_WORKING', { metadata: { platformEventId: 'evt-1' } });
        applyA2AFrame(accumulator, first);
        applyA2AFrame(accumulator, statusUpdate('t1', 'TASK_STATE_COMPLETED', { metadata: { platform_event_id: 'evt-2' } }));
        // Повторная доставка того же события не откатывает статус назад
        const redelivered = applyA2AFrame(accumulator, structuredClone(first));
        expect(redelivered).toEqual({ accumulator, changedTaskId: 't1', frameKind: 'statusUpdate' });
        expect(prop(prop(accumulator.tasksById['t1'], 'status'), 'state')).toBe('TASK_STATE_COMPLETED');
        const collision = statusUpdate('t1', 'TASK_STATE_FAILED', { metadata: { platformEventId: 'evt-1' } });
        expect(() => applyA2AFrame(accumulator, collision)).toThrow(/A2A event collision evt-1/);
    });

    it('deep-merges status metadata and keeps arrays and scalars as replacements', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, statusUpdate('t1', 'TASK_STATE_WORKING', { metadata: { platform_interrupt: { question: 'a', body: { kind: 'user_message', tags: [1] } }, flag: 1 } }));
        applyA2AFrame(accumulator, statusUpdate('t1', 'TASK_STATE_INPUT_REQUIRED', { metadata: { platform_interrupt: { body: { tags: [2], extra: true } }, flag: null } }));
        expect(prop(accumulator.tasksById['t1'], 'metadata')).toEqual({
            platform_interrupt: { question: 'a', body: { kind: 'user_message', tags: [2], extra: true } },
            flag: null,
        });
        applyA2AFrame(accumulator, statusUpdate('t1', 'TASK_STATE_COMPLETED', { metadata: 'ignored' }));
        expect(prop(prop(accumulator.tasksById['t1'], 'metadata'), 'flag')).toBeNull();
    });

    it('fails closed on context identity change, incomplete scope and missing ids', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, statusUpdate('t1', 'TASK_STATE_WORKING'));
        expect(() => applyA2AFrame(accumulator, { result: { statusUpdate: { taskId: 't1', contextId: 'other', status: { state: 'TASK_STATE_WORKING' } } } })).toThrow(/context identity changed/);
        expect(() => applyA2AFrame(accumulator, { result: { statusUpdate: { taskId: 't2', status: { state: 'TASK_STATE_WORKING' } } } })).toThrow(/statusUpdate scope is incomplete/);
        expect(() => applyA2AFrame(accumulator, { result: { artifactUpdate: { contextId: 'c1', artifact: { artifactId: 'a', parts: [] } } } })).toThrow(/artifactUpdate scope is incomplete/);
        expect(() => applyA2AFrame(accumulator, { result: { artifactUpdate: { taskId: 't1', contextId: 'c1', artifact: { parts: [] } } } })).toThrow(/artifact update has no artifactId/);
        expect(() => applyA2AFrame(accumulator, { result: { task: { status: { state: 'TASK_STATE_WORKING' } } } })).toThrow(/Task snapshot has no id/);
    });

    it('accepts snake_case wire ids on snapshots but refuses to append across identifier styles', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, { result: { task: {
            id: 't1', context_id: 'c1', status: { state: 'TASK_STATE_WORKING' },
            artifacts: [{ artifact_id: 'a', parts: [{ text: 'x' }] }, { parts: [{ text: 'no id, skipped' }] }],
        } } });
        const task = accumulator.tasksById['t1'];
        if (!task) throw new Error('task t1 missing');
        expect(task.contextId).toBe('c1');
        expect(task.artifacts).toHaveLength(1);
        expect(task.artifactsById['a']?.parts).toEqual([{ text: 'x' }]);
        expect(() => applyA2AFrame(accumulator, { result: { artifactUpdate: { task_id: 't1', context_id: 'c1', append: true, artifact: { artifactId: 'a', parts: [{ text: 'y' }] } } } })).toThrow(/artifact identity changed while appending/);
        // Без append артефакт заменяется целиком независимо от стиля идентификатора
        applyA2AFrame(accumulator, { result: { artifactUpdate: { task_id: 't1', context_id: 'c1', append: false, last_chunk: true, artifact: { artifactId: 'a', parts: [{ text: 'z' }] } } } });
        expect(task.artifactsById['a']).toEqual({ artifactId: 'a', parts: [{ text: 'z' }] });
        expect(task.artifacts).toEqual([task.artifactsById['a']]);
        expect(() => applyA2AFrame(accumulator, { result: { artifactUpdate: { taskId: 't1', contextId: 'c1', append: true, artifact: { artifactId: 'a', parts: [] } } } })).toThrow(/artifact a is closed/);
    });

    it('reports task boundaries and serializes closed artifact ids', () => {
        expect(taskBoundary({ status: { state: 'TASK_STATE_COMPLETED' } })).toBe('terminal');
        expect(taskBoundary({ status: { state: 'TASK_STATE_AUTH_REQUIRED' } })).toBe('interrupted');
        expect(taskBoundary({ status: { state: 'TASK_STATE_WORKING' } })).toBeNull();
        expect(taskBoundary(null)).toBeNull();
        expect(serializableTask(null)).toBeNull();
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, { result: { artifactUpdate: { taskId: 't1', contextId: 'c1', lastChunk: true, artifact: { artifactId: 'a', parts: [] } } } });
        const serialized = serializableTask(accumulator.tasksById['t1']);
        expect(prop(serialized, 'closedArtifactIds')).toEqual(['a']);
        expect(prop(accumulator.tasksById['t1'], 'closedArtifactIds')).toBeInstanceOf(Set);
    });
});

describe('a2a codec edge cases', () => {
    it('validates file part sources field by field', () => {
        expect(buildA2aFileParts(undefined)).toEqual([]);
        const sourceWithSize: A2aFileSource & { file_size?: number } = { url: 'https://f/1', content_type: 'text/plain', original_name: 'a.txt', file_size: 1 };
        expect(buildA2aFileParts([sourceWithSize])).toEqual([{ url: 'https://f/1', mediaType: 'text/plain', filename: 'a.txt' }]);
        expect(() => Reflect.apply(buildA2aFileParts, null, [['x']])).toThrow(/file part source must be an object/);
        expect(() => buildA2aFileParts([{ content_type: 'text/plain', original_name: 'a' }])).toThrow(/file part requires url/);
        expect(() => buildA2aFileParts([{ url: ' ', content_type: 'text/plain', original_name: 'a' }])).toThrow(/file part requires url/);
        expect(() => buildA2aFileParts([{ url: 'https://f/1', original_name: 'a' }])).toThrow(/file part requires content_type/);
        expect(() => buildA2aFileParts([{ url: 'https://f/1', content_type: 'text/plain', original_name: '' }])).toThrow(/file part requires original_name/);
    });

    it('generates RFC 4122 v4 ids without relying on randomUUID', () => {
        const seen = new Set<string>();
        for (let index = 0; index < 50; index += 1) {
            const uuid = randomUuid();
            expect(uuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
            seen.add(uuid);
        }
        expect(seen.size).toBe(50);
        expect(createProtocolId('context')).toMatch(/^context:[0-9a-f-]{36}$/);
        expect(createProtocolId()).toMatch(/^flow-ui:/);
    });
});

describe('interface editor domain rare schemas', () => {
    it('maps anyOf number and select-default arrays and rejects unknown property schemas', () => {
        expect(propertyKind('value', { anyOf: [{ type: 'number' }, { type: 'integer' }, { type: 'null' }] })).toBe('number');
        expect(propertyKind('default', { anyOf: [{ type: 'string' }, { type: 'array', items: { type: 'string' } }] })).toBe('select_default');
        expect(propertyKind('blocks', {})).toBe('blocks');
        expect(propertyKind('image_url', { type: 'string', 'x-flow-ui': 'image_url' })).toBe('image_url');
        expect(() => propertyKind('weird', { anyOf: [{ type: 'string' }, { type: 'boolean' }] })).toThrow(/unsupported property schema for weird/);
    });

    it('replaces page blocks on a copy of the document', () => {
        const document = { start_page_id: 'main', pages: [{ page_id: 'main', title: 'Main', blocks: [{ block_id: 'a', type: 'text', text: 'A' }] }] };
        const blocks = [{ block_id: 'b', type: 'text', text: 'B' }];
        const next = replacePageBlocks(document, 'main', blocks);
        expect(next.pages[0]?.blocks).toEqual(blocks);
        expect(next.pages[0]?.blocks).not.toBe(blocks);
        expect(document.pages[0]?.blocks.map((block) => block.block_id)).toEqual(['a']);
        expect(() => replacePageBlocks(document, 'missing', [])).toThrow();
    });
});

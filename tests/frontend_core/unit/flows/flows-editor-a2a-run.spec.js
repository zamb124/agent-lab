import { describe, it, expect } from 'vitest';
import { mapEditorA2aFrame } from '../../../../apps/flows/ui/_helpers/flows-editor-a2a-run.js';

const CONTEXT_ID = 'context:65b4c118-763f-4080-bf46-ee4dc5b01cd6';
const TASK_ID = 'c44ce807-e69c-5d1d-bbcf-b557e00f1c39';

const SESSION = Object.freeze({
    contextId: CONTEXT_ID,
    currentTaskId: null,
    taskPrimed: false,
    traceIndexBase: 0,
});

function rpcFrame(result) {
    return { jsonrpc: '2.0', id: 'rpc:test', result };
}

const NODE_START_FRAME = rpcFrame({
    artifactUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        artifact: {
            artifactId: '4e6d434d-205b-4794-a11e-3573bc72a89d',
            name: 'node_start_main',
            parts: [{ data: { event: 'node_start', node_id: 'main', node_type: 'llm_node' } }],
        },
    },
});

const NODE_ERROR_FRAME = rpcFrame({
    artifactUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        artifact: {
            artifactId: '97e82012-e333-4de3-91ca-4be46178cda4',
            name: 'node_error_main',
            parts: [{
                data: {
                    event: 'node_error',
                    node_id: 'main',
                    node_type: 'llm_node',
                    error: "LLM node 'main' returned empty final response after 1 iteration(s)",
                    duration_ms: 2058.0,
                    run_index: 0.0,
                },
            }],
        },
    },
});

const FAILED_STATUS_FRAME = rpcFrame({
    statusUpdate: {
        taskId: TASK_ID,
        contextId: CONTEXT_ID,
        status: {
            state: 'TASK_STATE_FAILED',
            message: {
                messageId: `status:${TASK_ID}:failed`,
                role: 'ROLE_AGENT',
                parts: [{ text: "LLM node 'main' returned empty final response after 1 iteration(s)" }],
            },
        },
    },
});

describe('mapEditorA2aFrame', () => {
    it('maps node_start artifactUpdate to flows/run/node_started', () => {
        const mapped = mapEditorA2aFrame(NODE_START_FRAME, SESSION);
        expect(mapped.terminal).toBe(false);
        expect(mapped.nextTaskId).toBe(TASK_ID);
        expect(mapped.runEvents).toEqual([
            { type: 'flows/run/node_started', payload: { node_id: 'main' } },
        ]);
        expect(mapped.traceEntries).toHaveLength(1);
        expect(mapped.traceEntries[0].kind).toBe('node_start');
        expect(mapped.traceEntries[0].node_id).toBe('main');
        expect(mapped.traceEntries[0].id).toContain('node_start');
    });

    it('maps node_error artifactUpdate to flows/run/node_failed', () => {
        const mapped = mapEditorA2aFrame(NODE_ERROR_FRAME, {
            ...SESSION,
            currentTaskId: TASK_ID,
            taskPrimed: true,
        });
        expect(mapped.terminal).toBe(false);
        expect(mapped.runEvents).toHaveLength(1);
        expect(mapped.runEvents[0].type).toBe('flows/run/node_failed');
        expect(mapped.runEvents[0].payload.node_id).toBe('main');
        expect(mapped.runEvents[0].payload.error).toBe(
            "LLM node 'main' returned empty final response after 1 iteration(s)",
        );
        expect(mapped.traceEntries[0].kind).toBe('node_error');
    });

    it('marks TASK_STATE_FAILED statusUpdate as terminal', () => {
        const mapped = mapEditorA2aFrame(FAILED_STATUS_FRAME, {
            ...SESSION,
            currentTaskId: TASK_ID,
            taskPrimed: true,
        });
        expect(mapped.terminal).toBe(true);
        expect(mapped.runEvents).toEqual([]);
        expect(mapped.traceEntries.some((entry) => (
            entry.kind === 'status_terminal' && entry.terminal_state === 'failed'
        ))).toBe(true);
    });

    it('throws when JSON-RPC frame has no result', () => {
        expect(() => mapEditorA2aFrame({ jsonrpc: '2.0', id: 'rpc:test' }, SESSION)).toThrow(
            'mapEditorA2aFrame: frame.result object required',
        );
    });

    it('throws when session.taskPrimed is missing', () => {
        expect(() => mapEditorA2aFrame(NODE_START_FRAME, {
            contextId: CONTEXT_ID,
            currentTaskId: null,
            traceIndexBase: 0,
        })).toThrow('mapEditorA2aFrame: session.taskPrimed must be boolean');
    });

    it('throws when session.contextId is an empty string', () => {
        expect(() => mapEditorA2aFrame(NODE_START_FRAME, {
            ...SESSION,
            contextId: '',
        })).toThrow('mapEditorA2aFrame: session.contextId must be null or non-empty string');
    });
});

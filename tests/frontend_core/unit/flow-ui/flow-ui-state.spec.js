import { describe, expect, it } from 'vitest';

import {
    createFlowUIRuntimeState,
    reduceFlowUIState,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-state.js';

describe('flow-ui-state', () => {
    it('hydrates then tracks pending mutations until ack', () => {
        let state = createFlowUIRuntimeState();
        state = reduceFlowUIState(state, {
            type: 'context.hydrated',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 2 },
        });
        expect(state.contextsById['ctx-1'].serverRevision).toBe(2);
        expect(state.contextsById['ctx-1'].saveStatus).toBe('saved');

        state = reduceFlowUIState(state, {
            type: 'document.local',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 2 },
            mutation: { id: 'm1', path: '/values/message', value: 'draft' },
        });
        expect(state.contextsById['ctx-1'].saveStatus).toBe('pending');
        expect(state.contextsById['ctx-1'].pendingMutations).toHaveLength(1);

        state = reduceFlowUIState(state, {
            type: 'document.ack',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 3 },
            mutationId: 'm1',
        });
        expect(state.contextsById['ctx-1'].serverRevision).toBe(3);
        expect(state.contextsById['ctx-1'].pendingMutations).toHaveLength(0);
        expect(state.contextsById['ctx-1'].saveStatus).toBe('saved');
    });

    it('records conflict without dropping document', () => {
        let state = createFlowUIRuntimeState();
        state = reduceFlowUIState(state, {
            type: 'context.hydrated',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 1 },
        });
        state = reduceFlowUIState(state, {
            type: 'document.conflict',
            contextId: 'ctx-1',
            conflict: { message: 'revision conflict' },
        });
        expect(state.contextsById['ctx-1'].saveStatus).toBe('conflict');
        expect(state.contextsById['ctx-1'].document.document_id).toBe('flow-ui:ctx-1');
        expect(state.contextsById['ctx-1'].conflict.message).toBe('revision conflict');
    });

    it('tracks optimistic pending turns until tasks.changed consumes them by mutation_id', () => {
        let state = createFlowUIRuntimeState();
        state = reduceFlowUIState(state, {
            type: 'context.hydrated',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 1 },
        });
        state = reduceFlowUIState(state, {
            type: 'turn.optimistic',
            contextId: 'ctx-1',
            turn: { id: 'submit-1', text: 'привет' },
        });
        expect(state.contextsById['ctx-1'].pendingTurns).toEqual([
            { id: 'submit-1', text: 'привет', files: [] },
        ]);

        // A projection without the submit mutation_id must not consume the turn.
        state = reduceFlowUIState(state, {
            type: 'tasks.changed',
            contextId: 'ctx-1',
            tasksById: {
                t0: {
                    id: 't0',
                    artifacts: [{ name: 'user_message', parts: [{ text: 'привет' }] }],
                    history: [],
                    status: { state: 'TASK_STATE_WORKING' },
                },
            },
            taskOrder: ['t0'],
            activeTaskId: 't0',
        });
        expect(state.contextsById['ctx-1'].pendingTurns).toHaveLength(1);

        state = reduceFlowUIState(state, {
            type: 'tasks.changed',
            contextId: 'ctx-1',
            tasksById: {
                t1: {
                    id: 't1',
                    artifacts: [{
                        name: 'user_message',
                        parts: [{ text: 'привет' }],
                        metadata: { mutation_id: 'submit-1' },
                    }],
                    history: [],
                    status: { state: 'TASK_STATE_WORKING' },
                },
            },
            taskOrder: ['t1'],
            activeTaskId: 't1',
        });
        expect(state.contextsById['ctx-1'].pendingTurns).toEqual([]);
        expect(state.contextsById['ctx-1'].activeTaskId).toBe('t1');
    });

    it('tracks the submit lifecycle via submitting flag', () => {
        let state = createFlowUIRuntimeState();
        state = reduceFlowUIState(state, {
            type: 'context.hydrated',
            contextId: 'ctx-1',
            document: { document_id: 'flow-ui:ctx-1', revision: 1 },
        });
        expect(state.contextsById['ctx-1'].submitting).toBe(false);
        state = reduceFlowUIState(state, { type: 'submit.started', contextId: 'ctx-1' });
        expect(state.contextsById['ctx-1'].submitting).toBe(true);
        state = reduceFlowUIState(state, { type: 'submit.finished', contextId: 'ctx-1' });
        expect(state.contextsById['ctx-1'].submitting).toBe(false);
    });
});

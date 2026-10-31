import { describe, expect, it } from 'vitest';

import { operatorHandoffFromTask } from '../../../../core/frontend/static/lib/flow-ui/runtime/operator-handoff-from-task.js';

function operatorTask({ mode = 'single_reply', workItemId = 'wi_1' } = {}) {
    return {
        id: 'task-1',
        status: {
            state: 'TASK_STATE_INPUT_REQUIRED',
            message: {
                parts: [{ text: 'wait' }],
                metadata: {
                    platform_interrupt: {
                        question: 'wait',
                        body: {
                            kind: 'operator_task',
                            handoff_mode: mode,
                            work_item_id: workItemId,
                        },
                    },
                },
            },
        },
    };
}

describe('operatorHandoffFromTask', () => {
    it('reads single_reply operator_task', () => {
        expect(operatorHandoffFromTask(operatorTask())).toEqual({
            mode: 'single_reply',
            workItemId: 'wi_1',
            taskId: 'task-1',
        });
    });

    it('reads takeover operator_task', () => {
        expect(operatorHandoffFromTask(operatorTask({ mode: 'takeover' }))).toEqual({
            mode: 'takeover',
            workItemId: 'wi_1',
            taskId: 'task-1',
        });
    });

    it('returns null when task is not interrupted', () => {
        expect(operatorHandoffFromTask({
            id: 'task-1',
            status: { state: 'TASK_STATE_COMPLETED' },
        })).toBeNull();
    });

    it('throws on unsupported operator_task handoff_mode', () => {
        expect(() => operatorHandoffFromTask(operatorTask({ mode: 'unknown' }))).toThrow(
            /unsupported handoff_mode/,
        );
    });

    it('reads operator_task from status.message.metadata', () => {
        expect(operatorHandoffFromTask({
            id: 'task-1',
            status: {
                state: 'TASK_STATE_INPUT_REQUIRED',
                message: {
                    metadata: {
                        platform_interrupt: {
                            body: {
                                kind: 'operator_task',
                                handoff_mode: 'takeover',
                                work_item_id: 'wi_msg',
                                question: 'wait',
                            },
                        },
                    },
                },
            },
        })).toEqual({
            mode: 'takeover',
            workItemId: 'wi_msg',
            taskId: 'task-1',
        });
    });
});

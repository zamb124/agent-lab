import { describe, expect, it } from 'vitest';

import {
    applyA2AFrame,
    createA2ATaskAccumulator,
    serializableTask,
    taskBoundary,
} from '../../../../core/frontend/static/lib/a2a/a2a-task-accumulator.js';

describe('a2a-task-accumulator', () => {
    it('appends artifact parts under a stable artifactId', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    contextId: 'ctx-1',
                    append: true,
                    artifact: {
                        artifactId: 'response',
                        name: 'response',
                        parts: [{ text: 'Hello' }],
                    },
                },
            },
        });
        applyA2AFrame(accumulator, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    contextId: 'ctx-1',
                    append: true,
                    lastChunk: true,
                    artifact: {
                        artifactId: 'response',
                        name: 'response',
                        parts: [{ text: ' world' }],
                    },
                },
            },
        });
        const task = accumulator.tasksById['task-1'];
        expect(task.artifacts).toHaveLength(1);
        expect(task.artifactsById.response.parts.map((part) => part.text)).toEqual([
            'Hello',
            ' world',
        ]);
        expect([...task.closedArtifactIds]).toEqual(['response']);
        expect(taskBoundary(task)).toBeNull();
    });

    it('rejects append after lastChunk closed the artifact', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    contextId: 'ctx-1',
                    lastChunk: true,
                    artifact: {
                        artifactId: 'response',
                        parts: [{ text: 'done' }],
                    },
                },
            },
        });
        expect(() => applyA2AFrame(accumulator, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    contextId: 'ctx-1',
                    append: true,
                    artifact: {
                        artifactId: 'response',
                        parts: [{ text: 'late' }],
                    },
                },
            },
        })).toThrow(/closed/);
    });

    it('hydrates Task snapshot and serializes closedArtifactIds', () => {
        const accumulator = createA2ATaskAccumulator();
        applyA2AFrame(accumulator, {
            result: {
                id: 'task-2',
                contextId: 'ctx-2',
                status: { state: 'TASK_STATE_COMPLETED' },
                artifacts: [{
                    artifactId: 'response',
                    name: 'response',
                    parts: [{ text: 'ok' }],
                }],
            },
        });
        const task = accumulator.tasksById['task-2'];
        expect(taskBoundary(task)).toBe('terminal');
        const snapshot = serializableTask(task);
        expect(snapshot.closedArtifactIds).toEqual([]);
        expect(snapshot.artifacts[0].parts[0].text).toBe('ok');
    });
});

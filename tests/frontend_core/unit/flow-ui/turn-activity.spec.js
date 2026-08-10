import { describe, expect, it } from 'vitest';
import { buildDefaultChatDocument } from '../../../../core/frontend/static/lib/flow-ui/templates/chat-template.js';
import { leadFormSurface } from '../../../../core/frontend/static/lib/flow-ui/templates/pages/lead-form.js';
import { LINNEX_CATALOG_ID } from '../../../../core/frontend/static/lib/flow-ui/protocol/constants.js';
import {
    deriveTurnActivityToasts,
    hasConversationFeed,
    projectConversationActivity,
    resolveTurnActivityPolicy,
    taskActivitySummary,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/turn-activity.js';

function leadFormDocument(policy = {}) {
    const surface = leadFormSurface('main', 'en');
    return {
        document_id: 'doc-lead',
        catalog_id: LINNEX_CATALOG_ID,
        active_page_id: 'main',
        revision: 1,
        pages: {
            main: { page_id: 'main', title: { default: 'Lead' }, route: '/', root_surface_id: 'main' },
        },
        surfaces: { main: surface },
        policy,
    };
}

function taskWithArtifacts(artifacts, state = 'TASK_STATE_WORKING') {
    return {
        id: 'task-1',
        status: { state },
        artifacts,
        history: [],
    };
}

function contextWithTask(task, { submitting = false } = {}) {
    return {
        submitting,
        activeTaskId: task?.id || null,
        tasksById: task ? { [task.id]: task } : {},
        taskOrder: task ? [task.id] : [],
    };
}

describe('turn activity toasts', () => {
    it('detects conversation feed on chat template and not on lead form', () => {
        expect(hasConversationFeed(buildDefaultChatDocument())).toBe(true);
        expect(hasConversationFeed(leadFormDocument())).toBe(false);
    });

    it('returns no toasts when conversation feed is present', () => {
        const document = {
            ...buildDefaultChatDocument(),
            policy: { show_reasoning: true, show_activity: true },
        };
        const task = taskWithArtifacts([
            { name: 'response', parts: [{ text: 'Hello' }] },
            { name: 'reasoning', parts: [{ text: 'think' }] },
        ]);
        const toasts = deriveTurnActivityToasts({
            document,
            context: contextWithTask(task, { submitting: true }),
            locale: 'en',
        });
        expect(toasts).toEqual([]);
    });

    it('shows working and response on lead form during/after turn', () => {
        const document = leadFormDocument();
        const working = deriveTurnActivityToasts({
            document,
            context: contextWithTask(
                taskWithArtifacts([{ name: 'reasoning', parts: [{ text: 'x' }] }], 'TASK_STATE_WORKING'),
                { submitting: true },
            ),
            locale: 'en',
        });
        expect(working.map((toast) => toast.kind)).toContain('working');
        expect(working.map((toast) => toast.kind)).not.toContain('reasoning');

        const done = deriveTurnActivityToasts({
            document,
            context: contextWithTask(
                taskWithArtifacts([{ name: 'response', parts: [{ text: 'Hello!' }] }], 'TASK_STATE_COMPLETED'),
            ),
            locale: 'en',
        });
        expect(done.map((toast) => toast.kind)).toEqual(['response']);
        expect(done[0].body).toBe('Hello!');
    });

    it('gates reasoning behind show_reasoning', () => {
        const hidden = deriveTurnActivityToasts({
            document: leadFormDocument({ show_reasoning: false }),
            context: contextWithTask(
                taskWithArtifacts([{ name: 'reasoning', parts: [{ text: 'secret' }] }], 'TASK_STATE_WORKING'),
            ),
            locale: 'en',
        });
        expect(hidden.map((toast) => toast.kind)).not.toContain('reasoning');

        const shown = deriveTurnActivityToasts({
            document: leadFormDocument({ show_reasoning: true }),
            context: contextWithTask(
                taskWithArtifacts([{ name: 'reasoning', parts: [{ text: 'secret' }] }], 'TASK_STATE_WORKING'),
            ),
            locale: 'en',
        });
        expect(shown.map((toast) => toast.kind)).toContain('reasoning');
        expect(shown.find((toast) => toast.kind === 'reasoning').body).toBe('secret');
    });

    it('hides activity when tool_calls_display is hidden', () => {
        const task = taskWithArtifacts([
            {
                name: 'tool_call:search',
                artifactId: 'tool_call:search',
                parts: [{ data: { name: 'search' } }],
            },
        ]);
        expect(taskActivitySummary(task, resolveTurnActivityPolicy({
            policy: { show_activity: true, tool_calls_display: 'compact' },
        }))).toBe('search');

        const toasts = deriveTurnActivityToasts({
            document: leadFormDocument({
                show_activity: true,
                tool_calls_display: 'hidden',
                show_skill_loads: false,
            }),
            context: contextWithTask(task),
            locale: 'en',
        });
        expect(toasts.map((toast) => toast.kind)).not.toContain('activity');
    });

    it('uses policy defaults when policy is missing and survives empty context', () => {
        expect(resolveTurnActivityPolicy({})).toMatchObject({
            show_reasoning: false,
            show_activity: true,
            tool_calls_display: 'compact',
            errors_display: 'generic',
        });
        expect(deriveTurnActivityToasts({
            document: leadFormDocument(),
            context: null,
            locale: 'en',
        })).toEqual([]);
    });

    it('shows generic error toast on failed tasks', () => {
        const toasts = deriveTurnActivityToasts({
            document: leadFormDocument({ errors_display: 'generic' }),
            context: contextWithTask(
                taskWithArtifacts([], 'TASK_STATE_FAILED'),
            ),
            locale: 'en',
        });
        expect(toasts.map((toast) => toast.kind)).toEqual(['error']);
        expect(toasts[0].body).toBe('The request could not be completed');
    });

    it('projects conversation tool and skill chips from A2A artifacts', () => {
        const policy = resolveTurnActivityPolicy({
            policy: {
                show_activity: true,
                tool_calls_display: 'compact',
                show_skill_loads: true,
                errors_display: 'detailed',
            },
        });
        const items = projectConversationActivity(
            taskWithArtifacts([
                {
                    name: 'tool_call:call-1',
                    artifactId: 'tool_call:call-1',
                    parts: [{
                        data: {
                            tool: 'load_agent_skill',
                            args: { agent_skill_id: 'flows-code' },
                            tool_call_id: 'call-1',
                        },
                    }],
                },
                {
                    name: 'tool_result:call-1',
                    artifactId: 'tool_result:call-1',
                    parts: [{
                        data: {
                            tool: 'load_agent_skill',
                            tool_call_id: 'call-1',
                            result: '{"success":true}',
                        },
                    }],
                },
                {
                    name: 'tool_call:call-2',
                    artifactId: 'tool_call:call-2',
                    parts: [{
                        data: {
                            tool: 'flows_get_node',
                            args: { flow_id: 'f1', node_id: 'main' },
                            tool_call_id: 'call-2',
                        },
                    }],
                },
                {
                    name: 'node_error_main',
                    artifactId: 'err-1',
                    parts: [{ data: { event: 'node_error', error: 'Ошибка выполнения инструмента' } }],
                },
            ]),
            policy,
            'en',
        );
        expect(items.map((item) => ({ kind: item.kind, label: item.label, status: item.status }))).toEqual([
            { kind: 'skill', label: 'flows-code', status: 'done' },
            { kind: 'tool', label: 'flows_get_node', status: 'running' },
            { kind: 'error', label: 'Ошибка выполнения инструмента', status: 'error' },
        ]);
    });

    it('marks open tool_call done when task is INPUT_REQUIRED', () => {
        const policy = resolveTurnActivityPolicy({
            policy: {
                show_activity: true,
                tool_calls_display: 'compact',
                show_skill_loads: false,
            },
        });
        const items = projectConversationActivity(
            taskWithArtifacts(
                [
                    {
                        name: 'tool_call:ask',
                        artifactId: 'tool_call:ask',
                        parts: [{
                            data: {
                                tool: 'ask_user',
                                tool_call_id: 'ask',
                                args: { question: 'Класс?' },
                            },
                        }],
                    },
                ],
                'TASK_STATE_INPUT_REQUIRED',
            ),
            policy,
            'ru',
        );
        expect(items).toEqual([
            expect.objectContaining({ kind: 'tool', label: 'ask_user', status: 'done' }),
        ]);
    });

    it('does not show working toast after INPUT_REQUIRED', () => {
        const toasts = deriveTurnActivityToasts({
            document: leadFormDocument(),
            context: contextWithTask(
                taskWithArtifacts(
                    [{ name: 'response', parts: [{ text: 'Вопрос?' }] }],
                    'TASK_STATE_INPUT_REQUIRED',
                ),
            ),
            locale: 'ru',
        });
        expect(toasts.map((toast) => toast.kind)).toEqual(['response']);
        expect(toasts[0].streaming).toBe(false);
    });

    it('hides conversation tool chips when tool_calls_display is hidden', () => {
        const policy = resolveTurnActivityPolicy({
            policy: {
                show_activity: true,
                tool_calls_display: 'hidden',
                show_skill_loads: false,
            },
        });
        const items = projectConversationActivity(
            taskWithArtifacts([
                {
                    name: 'tool_call:x',
                    artifactId: 'tool_call:x',
                    parts: [{ data: { tool: 'flows_get_node', tool_call_id: 'x' } }],
                },
            ]),
            policy,
            'en',
        );
        expect(items).toEqual([]);
    });
});

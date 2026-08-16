import { describe, expect, it } from 'vitest';
import {
    activeConversationTask,
    conversationTasks,
    conversationTurnText,
    conversationUserText,
    hasConversationContent,
    isSettledTaskState,
    mergeConversationTasks,
} from '../../../../core/frontend/static/lib/flow-ui/catalog/platform/conversation-turn.js';
import { resolveFlowUITheme } from '../../../../core/frontend/static/lib/flow-ui/shell/resolve-theme.js';

describe('activeConversationTask / interrupt', () => {
    it('treats INPUT_REQUIRED as settled so composer unlocks', () => {
        const tasks = [
            {
                id: 't-ask',
                status: {
                    state: 'TASK_STATE_INPUT_REQUIRED',
                    message: {
                        role: 'ROLE_AGENT',
                        parts: [{ text: 'Какой класс?' }],
                    },
                },
                artifacts: [
                    {
                        name: 'tool_call:ask',
                        artifactId: 'a1',
                        parts: [{
                            data: {
                                tool: 'ask_user',
                                tool_call_id: 'ask',
                                args: { question: 'Какой класс?' },
                            },
                        }],
                    },
                ],
            },
        ];
        expect(isSettledTaskState('TASK_STATE_INPUT_REQUIRED')).toBe(true);
        expect(isSettledTaskState('TASK_STATE_AUTH_REQUIRED')).toBe(true);
        expect(isSettledTaskState('TASK_STATE_WORKING')).toBe(false);
        expect(activeConversationTask(tasks)).toBeNull();
        expect(conversationTurnText(tasks[0])).toBe('Какой класс?');
    });

    it('keeps WORKING as the active in-flight task', () => {
        const tasks = [
            {
                id: 't-done',
                status: { state: 'TASK_STATE_COMPLETED', message: { parts: [{ text: 'ok' }] } },
                artifacts: [],
            },
            {
                id: 't-work',
                status: { state: 'TASK_STATE_WORKING' },
                artifacts: [],
            },
        ];
        expect(activeConversationTask(tasks)?.id).toBe('t-work');
    });
});

describe('conversationTurnText', () => {
    it('uses status.message when response artifact is absent', () => {
        const text = conversationTurnText({
            id: 't1',
            status: {
                state: 'TASK_STATE_COMPLETED',
                message: { parts: [{ text: 'chat-ok:hello' }] },
            },
            artifacts: [
                {
                    name: 'node_complete_main',
                    parts: [{ data: { new_value: 'chat-ok:hello' } }],
                },
            ],
        });
        expect(text).toBe('chat-ok:hello');
    });

    it('prefers streamed response artifact over status.message', () => {
        const text = conversationTurnText({
            id: 't2',
            status: {
                state: 'TASK_STATE_COMPLETED',
                message: { parts: [{ text: 'final-duplicate' }] },
            },
            artifacts: [
                { name: 'response', parts: [{ text: 'streamed-chunk' }] },
            ],
        });
        expect(text).toBe('streamed-chunk');
    });

    it('returns empty string when only observability artifacts exist', () => {
        const text = conversationTurnText({
            id: 't3',
            status: { state: 'TASK_STATE_WORKING' },
            artifacts: [
                { name: 'node_complete_main', parts: [{ data: { event: 'node_complete' } }] },
            ],
        });
        expect(text).toBe('');
    });
});

describe('conversationUserText', () => {
    it('prefers user_message artifact over older ROLE_USER history', () => {
        const text = conversationUserText({
            id: 't-current',
            history: [
                { role: 'ROLE_USER', task_id: 't-old', parts: [{ text: 'привет' }] },
                { role: 'ROLE_USER', task_id: 't-current', parts: [{ text: 'ignored-if-artifact' }] },
            ],
            status: { state: 'TASK_STATE_WORKING' },
            artifacts: [
                { name: 'user_message', parts: [{ text: 'from-artifact' }] },
            ],
        });
        expect(text).toBe('from-artifact');
    });

    it('scopes ROLE_USER history to the current task_id', () => {
        const text = conversationUserText({
            id: 't-current',
            history: [
                { role: 'ROLE_USER', task_id: 't-old', parts: [{ text: 'привет' }] },
                { role: 'ROLE_USER', task_id: 't-current', parts: [{ text: 'как дела' }] },
            ],
            status: { state: 'TASK_STATE_WORKING' },
            artifacts: [],
        });
        expect(text).toBe('как дела');
    });

    it('reads ROLE_USER history message', () => {
        const text = conversationUserText({
            id: 't-user',
            history: [
                { role: 'ROLE_USER', task_id: 't-user', parts: [{ text: 'need help' }] },
            ],
            status: { state: 'TASK_STATE_WORKING' },
            artifacts: [],
        });
        expect(text).toBe('need help');
    });

    it('reads user_message artifact when history is empty', () => {
        const text = conversationUserText({
            id: 't-user-art',
            history: [],
            status: { state: 'TASK_STATE_WORKING' },
            artifacts: [
                { name: 'user_message', parts: [{ text: 'from-artifact' }] },
            ],
        });
        expect(text).toBe('from-artifact');
    });
});

describe('conversationTasks / hasConversationContent', () => {
    it('drops bootstrap tasks without turn text', () => {
        const tasks = [
            {
                id: 'bootstrap',
                status: { state: 'TASK_STATE_COMPLETED' },
                artifacts: [
                    { name: 'ui.document', parts: [{ data: { revision: 1 } }] },
                ],
            },
            {
                id: 'reply',
                status: {
                    state: 'TASK_STATE_COMPLETED',
                    message: { parts: [{ text: 'hello' }] },
                },
                artifacts: [],
            },
        ];
        expect(conversationTasks(tasks).map((task) => task.id)).toEqual(['reply']);
        expect(hasConversationContent(tasks)).toBe(true);
        expect(hasConversationContent([tasks[0]])).toBe(false);
        expect(hasConversationContent([])).toBe(false);
    });

    it('keeps tasks that only have user text', () => {
        const tasks = [
            {
                id: 'pending',
                history: [{ role: 'ROLE_USER', parts: [{ text: 'hi' }] }],
                status: { state: 'TASK_STATE_WORKING' },
                artifacts: [],
            },
        ];
        expect(conversationTasks(tasks).map((task) => task.id)).toEqual(['pending']);
    });

    it('pairs optimistic user with an orphan assistant reply so order and typing stay correct', () => {
        const tasks = [
            {
                id: 'reply',
                status: {
                    state: 'TASK_STATE_COMPLETED',
                    message: { parts: [{ text: 'hello' }] },
                },
                artifacts: [],
            },
        ];
        const merged = mergeConversationTasks(tasks, [
            { id: 'submit-1', text: 'привет' },
        ]);
        expect(merged.map((task) => task.id)).toEqual(['reply']);
        expect(conversationUserText(merged[0])).toBe('привет');
        expect(conversationTurnText(merged[0])).toBe('hello');

        const withUser = mergeConversationTasks([
            {
                id: 't2',
                artifacts: [{
                    name: 'user_message',
                    parts: [{ text: 'привет' }],
                    metadata: { mutation_id: 'submit-1' },
                }],
                status: { state: 'TASK_STATE_WORKING' },
                history: [],
            },
        ], [{ id: 'submit-1', text: 'привет' }]);
        expect(withUser.map((task) => task.id)).toEqual(['t2']);
    });

    it('pairs optimistic user with an in-flight real task before the assistant streams', () => {
        const merged = mergeConversationTasks([
            {
                id: 't-live',
                status: { state: 'TASK_STATE_WORKING' },
                artifacts: [],
                history: [],
            },
        ], [{ id: 'submit-9', text: 'привет' }]);
        expect(merged).toHaveLength(1);
        expect(merged[0].id).toBe('t-live');
        expect(conversationUserText(merged[0])).toBe('привет');
    });

    it('does not consume a pending turn by text match without mutation_id', () => {
        const withoutId = mergeConversationTasks([
            {
                id: 't2',
                artifacts: [{ name: 'user_message', parts: [{ text: 'привет' }] }],
                status: { state: 'TASK_STATE_WORKING' },
                history: [],
            },
        ], [{ id: 'submit-1', text: 'привет' }]);
        expect(withoutId.map((task) => task.id)).toEqual(['t2', 'optimistic:submit-1']);
    });

    it('keeps a prior greeting task ahead of a new in-flight optimistic pair', () => {
        const merged = mergeConversationTasks([
            {
                id: 'greeting',
                status: {
                    state: 'TASK_STATE_COMPLETED',
                    message: { parts: [{ text: 'Hello!' }] },
                },
                artifacts: [],
            },
            {
                id: 'live',
                status: { state: 'TASK_STATE_WORKING' },
                artifacts: [],
                history: [],
            },
        ], [{ id: 'submit-2', text: 'привет' }]);
        expect(merged.map((task) => task.id)).toEqual(['greeting', 'live']);
        expect(conversationUserText(merged[0])).toBe('');
        expect(conversationUserText(merged[1])).toBe('привет');
    });

    it('carries optimistic files into the pending turn artifact', () => {
        const merged = mergeConversationTasks([], [
            { id: 'submit-2', text: '', files: [{ file_id: 'f1', original_name: 'doc.pdf' }] },
        ]);
        expect(merged).toHaveLength(1);
        expect(merged[0].artifacts[0].parts).toEqual([
            { data: { files: [{ file_id: 'f1', original_name: 'doc.pdf' }] } },
        ]);
        expect(hasConversationContent(merged)).toBe(true);
    });

    it('rejects non-array tasks', () => {
        expect(() => conversationTasks(null)).toThrow(/requires tasks array/);
    });
});

describe('resolveFlowUITheme', () => {
    it('keeps explicit light/dark', () => {
        expect(resolveFlowUITheme('light')).toBe('light');
        expect(resolveFlowUITheme('dark')).toBe('dark');
    });

    it('reads html data-theme for auto', () => {
        const doc = {
            documentElement: {
                getAttribute(name) {
                    if (name !== 'data-theme') return null;
                    return 'light';
                },
            },
        };
        expect(resolveFlowUITheme('auto', doc)).toBe('light');
        expect(resolveFlowUITheme(undefined, doc)).toBe('light');
    });

    it('defaults to dark when data-theme is missing', () => {
        const doc = {
            documentElement: {
                getAttribute() {
                    return null;
                },
            },
        };
        expect(resolveFlowUITheme('auto', doc)).toBe('dark');
    });

    it('keeps explicit dark when host html is light', () => {
        const doc = {
            documentElement: {
                getAttribute(name) {
                    if (name !== 'data-theme') return null;
                    return 'light';
                },
            },
        };
        expect(resolveFlowUITheme('dark', doc)).toBe('dark');
    });

    it('rejects unknown theme', () => {
        expect(() => resolveFlowUITheme('sepia')).toThrow(/unsupported theme/);
    });
});

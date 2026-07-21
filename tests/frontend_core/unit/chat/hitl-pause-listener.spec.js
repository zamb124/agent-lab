/**
 * Активная HITL-пауза и live resubscribe helpers.
 */

import { describe, it, expect } from 'vitest';
import {
    findActiveHitlPause,
    findActiveOauthPause,
    findActiveLiveTailPause,
} from '../../../../core/frontend/static/lib/chat/runtime/hitl-pause-listener.js';
import {
    applyChatRuntimeEvent,
    createInitialChatRuntimeState,
} from '../../../../core/frontend/static/lib/chat/runtime/chat-state.js';
import { buildA2aSubscribeToTaskBody } from '../../../../core/frontend/static/lib/chat/runtime/a2a-stream.js';

function stateWithHitlPause({ workItemId = 'wi1', taskId = 'tsk1', contextId = 'ctx1', flowId = 'flow1' } = {}) {
    let state = createInitialChatRuntimeState();
    state = applyChatRuntimeEvent(state, 'session_loaded', {
        sessionId: `${flowId}:${contextId}`,
        flowId,
        contextId,
        taskId,
        messages: [
            {
                id: 'u1',
                role: 'user',
                content: 'оператор',
                timestamp: new Date().toISOString(),
                taskId,
            },
        ],
    });
    state = applyChatRuntimeEvent(state, 'input_required', {
        task_id: taskId,
        context_id: contextId,
        message: { parts: [{ text: 'ожидайте' }] },
        result_metadata: {
            platform_interrupt: {
                question: 'ожидайте',
                body: {
                    kind: 'operator_task',
                    question: 'ожидайте',
                    task_title: 't',
                    assignee_queue: 'example_hitl',
                    handoff_mode: 'takeover',
                    work_item_id: workItemId,
                },
            },
        },
    });
    return state;
}

function stateWithOauthPause({
    taskId = 'tsk-oauth',
    contextId = 'ctx-oauth',
    flowId = 'flow-oauth',
    authUrl = 'https://accounts.google.com/o/oauth2/v2/auth?x=1',
} = {}) {
    let state = createInitialChatRuntimeState();
    state = applyChatRuntimeEvent(state, 'session_loaded', {
        sessionId: `${flowId}:${contextId}`,
        flowId,
        contextId,
        taskId,
        messages: [
            {
                id: 'u1',
                role: 'user',
                content: 'sheets',
                timestamp: new Date().toISOString(),
                taskId,
            },
        ],
    });
    state = applyChatRuntimeEvent(state, 'input_required', {
        task_id: taskId,
        context_id: contextId,
        message: { parts: [{ text: 'oauth' }] },
        result_metadata: {
            platform_interrupt: {
                question: 'oauth_required.google.workspace',
                body: {
                    kind: 'oauth_required',
                    question: 'oauth_required.google.workspace',
                    auth_url: authUrl,
                    provider: 'google',
                    service: 'workspace',
                },
            },
        },
    });
    return state;
}

describe('findActiveHitlPause', () => {
    it('returns pause when operator_task inputRequired is present', () => {
        const pause = findActiveHitlPause(stateWithHitlPause());
        expect(pause).toEqual({
            workItemId: 'wi1',
            taskId: 'tsk1',
            contextId: 'ctx1',
            flowId: 'flow1',
            sessionId: 'flow1:ctx1',
        });
    });

    it('returns null without operator_task', () => {
        expect(findActiveHitlPause(createInitialChatRuntimeState())).toBeNull();
    });
});

describe('findActiveOauthPause', () => {
    it('returns pause when oauth_required with authUrl is present', () => {
        const pause = findActiveOauthPause(stateWithOauthPause());
        expect(pause).toEqual({
            taskId: 'tsk-oauth',
            contextId: 'ctx-oauth',
            flowId: 'flow-oauth',
            sessionId: 'flow-oauth:ctx-oauth',
            authUrl: 'https://accounts.google.com/o/oauth2/v2/auth?x=1',
        });
    });

    it('returns null without oauth pause', () => {
        expect(findActiveOauthPause(createInitialChatRuntimeState())).toBeNull();
    });
});

describe('findActiveLiveTailPause', () => {
    it('prefers HITL over oauth', () => {
        const pause = findActiveLiveTailPause(stateWithHitlPause());
        expect(pause?.kind).toBe('operator_task');
    });

    it('returns oauth when no HITL', () => {
        const pause = findActiveLiveTailPause(stateWithOauthPause());
        expect(pause?.kind).toBe('oauth_required');
        expect(pause?.taskId).toBe('tsk-oauth');
    });
});

describe('buildA2aSubscribeToTaskBody', () => {
    it('builds SubscribeToTask JSON-RPC', () => {
        const body = buildA2aSubscribeToTaskBody('task-abc');
        expect(body.method).toBe('SubscribeToTask');
        expect(body.params).toEqual({ id: 'task-abc' });
    });

    it('rejects empty taskId', () => {
        expect(() => buildA2aSubscribeToTaskBody('')).toThrow(/taskId/);
    });
});

describe('operator_reply consecutive dedupe', () => {
    it('skips duplicate consecutive operator bubble', () => {
        let state = createInitialChatRuntimeState();
        state = applyChatRuntimeEvent(state, 'session_loaded', {
            sessionId: 'f:c',
            flowId: 'f',
            contextId: 'c',
            taskId: 't1',
            messages: [],
        });
        state = applyChatRuntimeEvent(state, 'operator_reply', { task_id: 't1', text: 'привет' });
        state = applyChatRuntimeEvent(state, 'operator_reply', { task_id: 't1', text: 'привет' });
        const bucket = state.messagesByContextId.c;
        const ops = bucket.messages.filter((m) => m.role === 'operator');
        expect(ops).toHaveLength(1);
    });
});

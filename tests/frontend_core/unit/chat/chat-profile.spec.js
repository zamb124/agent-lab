import { describe, it, expect } from 'vitest';
import {
    CHAT_PROFILE_KINDS,
    createChatProfile,
    resolveChatViewConfig,
} from '../../../../core/frontend/static/lib/chat/runtime/chat-profile.js';

describe('operator_handoff profile', () => {
    it('входит в CHAT_PROFILE_KINDS и даёт минимальный диалоговый вид', () => {
        expect(CHAT_PROFILE_KINDS).toContain('operator_handoff');
        const profile = createChatProfile({ kind: 'operator_handoff' });
        expect(profile.capabilities.runTrace).toBe(false);
        expect(profile.capabilities.filesPanel).toBe(false);
        expect(profile.capabilities.cancel).toBe(false);
    });

    it('viewConfig фиксирован независимо от policy (single_reply/takeover)', () => {
        const profile = createChatProfile({ kind: 'operator_handoff' });
        for (const policy of [
            null,
            { mode: 'single_reply', can_send: false, can_complete: true },
            { mode: 'takeover', can_send: true, can_complete: true },
        ]) {
            const vc = resolveChatViewConfig(profile, policy);
            expect(vc.profileKind).toBe('operator_handoff');
            expect(vc.showRunTrace).toBe(false);
            expect(vc.showFilesPanel).toBe(false);
            expect(vc.allowCancel).toBe(false);
            expect(vc.toolCallsDisplay).toBe('hidden');
            expect(vc.suggestedPrompts).toEqual([]);
        }
    });
});

describe('createChatProfile', () => {
    it('создаёт профиль для каждого известного kind', () => {
        for (const kind of CHAT_PROFILE_KINDS) {
            const profile = createChatProfile({ kind });
            expect(profile.kind).toBe(kind);
            expect(typeof profile.capabilities.runTrace).toBe('boolean');
        }
    });

    it('бросает на неизвестный kind и невалидный вход', () => {
        expect(() => createChatProfile({ kind: 'widget' })).toThrow(/unknown profile kind/);
        expect(() => createChatProfile(null)).toThrow(/input object required/);
    });

    it('override capabilities: только известные boolean-ключи', () => {
        const profile = createChatProfile({ kind: 'embed_public', capabilities: { cancel: false } });
        expect(profile.capabilities.cancel).toBe(false);
        expect(() => createChatProfile({ kind: 'spa', capabilities: { unknown: true } })).toThrow(
            /unknown capability/,
        );
        expect(() => createChatProfile({ kind: 'spa', capabilities: { cancel: 'yes' } })).toThrow(
            /must be boolean/,
        );
    });
});

describe('resolveChatViewConfig: policy ∩ capabilities', () => {
    it('пустая policy даёт Pydantic-дефолты для spa', () => {
        const view = resolveChatViewConfig(createChatProfile({ kind: 'spa' }), null);
        expect(view).toMatchObject({
            profileKind: 'spa',
            showReasoning: false,
            toolCallsDisplay: 'compact',
            showActivity: true,
            errorsDisplay: 'generic',
            showRunTrace: false,
            showTraceActions: true,
            showBrowserPreviews: true,
            showFilesPanel: true,
            allowCancel: true,
            greetingMessage: null,
        });
        expect(view.suggestedPrompts).toEqual([]);
    });

    it('policy разрешает элементы в пределах capabilities поверхности', () => {
        const policy = {
            show_reasoning: true,
            tool_calls_display: 'detailed',
            show_run_trace: true,
            show_trace_actions: true,
            errors_display: 'detailed',
        };
        const spa = resolveChatViewConfig(createChatProfile({ kind: 'spa' }), policy);
        expect(spa.showRunTrace).toBe(true);
        expect(spa.showTraceActions).toBe(true);
        expect(spa.showReasoning).toBe(true);
        expect(spa.toolCallsDisplay).toBe('detailed');
        expect(spa.errorsDisplay).toBe('detailed');

        const embed = resolveChatViewConfig(createChatProfile({ kind: 'embed_public' }), policy);
        expect(embed.showRunTrace).toBe(false);
        expect(embed.showTraceActions).toBe(false);
        expect(embed.showReasoning).toBe(true);
    });

    it('spa всегда показывает trace actions независимо от flow policy', () => {
        const restrictive = {
            show_trace_actions: false,
            show_run_trace: false,
        };
        const spa = resolveChatViewConfig(createChatProfile({ kind: 'spa' }), restrictive);
        expect(spa.showTraceActions).toBe(true);
        expect(spa.showRunTrace).toBe(false);
    });

    it('editor_test игнорирует policy и показывает всё', () => {
        const restrictive = {
            show_reasoning: false,
            tool_calls_display: 'hidden',
            show_activity: false,
            errors_display: 'generic',
            show_run_trace: false,
            show_trace_actions: false,
            show_browser_previews: false,
            show_files_panel: false,
            allow_cancel: false,
        };
        const view = resolveChatViewConfig(createChatProfile({ kind: 'editor_test' }), restrictive);
        expect(view).toMatchObject({
            showReasoning: true,
            toolCallsDisplay: 'detailed',
            showActivity: true,
            errorsDisplay: 'detailed',
            showRunTrace: true,
            showTraceActions: true,
            showBrowserPreviews: true,
            showFilesPanel: true,
            allowCancel: true,
        });
    });

    it('greeting и suggested_prompts проходят и в editor_test', () => {
        const view = resolveChatViewConfig(createChatProfile({ kind: 'editor_test' }), {
            greeting_message: 'Привет!',
            suggested_prompts: ['Что ты умеешь?', '  ', 'Помоги с задачей'],
        });
        expect(view.greetingMessage).toBe('Привет!');
        expect(view.suggestedPrompts).toEqual(['Что ты умеешь?', 'Помоги с задачей']);
    });

    it('пустой/пробельный greeting нормализуется в null', () => {
        const profile = createChatProfile({ kind: 'spa' });
        expect(resolveChatViewConfig(profile, { greeting_message: '   ' }).greetingMessage).toBeNull();
        expect(resolveChatViewConfig(profile, { greeting_message: null }).greetingMessage).toBeNull();
    });

    it('бросает на невалидную policy (Zero-Guess)', () => {
        const profile = createChatProfile({ kind: 'spa' });
        expect(() => resolveChatViewConfig(profile, { show_reasoning: 'yes' })).toThrow(/must be boolean/);
        expect(() => resolveChatViewConfig(profile, { tool_calls_display: 'verbose' })).toThrow(
            /invalid value/,
        );
        expect(() => resolveChatViewConfig(profile, { suggested_prompts: [1] })).toThrow(/string\[\]/);
        expect(() => resolveChatViewConfig(profile, 'policy')).toThrow(/must be object or null/);
        expect(() => resolveChatViewConfig({ kind: 'bad' }, null)).toThrow(/profile from createChatProfile/);
    });
});

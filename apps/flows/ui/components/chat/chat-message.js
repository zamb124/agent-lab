/**
 * Компонент одного сообщения в чате
 */
import { html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-assistant-message-actions.js';
import { asArray, asString, isPlainObject, toolCallIconName } from '../../_helpers/flows-resolvers.js';
import { resolveFlowVoiceHttpOrigin } from '../../_helpers/flow-voice-session.js';
import {
    readTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '@platform/lib/voice/tts-output-pref.js';
import './flows-chat-run-trace.js';

export class ChatMessage extends PlatformElement {
    static i18nNamespace = 'flows';
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .message {
                display: flex;
                gap: var(--space-4);
                animation: message-enter var(--duration-normal) var(--easing-default);
            }
            
            .message.user {
                flex-direction: row-reverse;
            }
            
            .avatar {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
            }
            
            .message.user .avatar {
                background: var(--accent-gradient);
                border: none;
                color: white;
                box-shadow: 0 4px 12px rgba(153, 166, 249, 0.25);
            }
            
            .message.assistant .avatar {
                background: var(--glass-solid-medium);
                color: var(--accent);
            }
            
            .message.operator .avatar {
                background: var(--glass-solid-medium);
                color: var(--warning, #f59e0b);
            }
            
            .message.system .avatar {
                background: var(--info-bg);
                color: var(--info);
            }
            
            .bubble {
                flex: 1;
                max-width: 70%;
                min-width: 0;
            }
            
            .message.user .bubble {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
            }
            
            .content {
                padding: var(--space-4) var(--space-5);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle), var(--glass-inner-glow-subtle);
            }
            
            .message.user .content {
                background: var(--accent);
                border: none;
                color: white;
                border-bottom-right-radius: var(--radius-sm);
                box-shadow: 0 4px 16px rgba(153, 166, 249, 0.2);
            }
            
            .message.assistant .content {
                background: var(--glass-solid-medium);
                border-bottom-left-radius: var(--radius-sm);
            }
            
            .message.system .content {
                background: var(--info-bg);
                border-color: var(--info-border);
            }
            
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            
            .message.user .header {
                justify-content: flex-end;
            }
            .message.user .header.has-inline-tools {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
            }
            .user-header-meta {
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                min-width: 0;
            }
            .user-run-trace-embed {
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
                max-height: min(220px, 38vh);
                overflow: auto;
                border-radius: var(--radius-lg);
            }
            .user-run-trace-embed flows-chat-run-trace {
                display: block;
            }
            .message.user .tracing-btn.user-bubble-tool {
                background: rgba(255, 255, 255, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.4);
                color: white;
            }
            .message.user .tracing-btn.user-bubble-tool:hover {
                background: rgba(255, 255, 255, 0.35);
                border-color: white;
                color: white;
            }
            .message.user .tracing-btn.user-bubble-tool[aria-pressed='true'] {
                background: rgba(255, 255, 255, 0.35);
                border-color: white;
            }
            
            .header-actions {
                display: flex;
                gap: var(--space-1);
                margin-left: auto;
            }
            
            .tracing-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                padding: 0;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tracing-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--accent);
                border-color: var(--accent);
            }
            
            .role {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            
            .message.user .role {
                color: rgba(255, 255, 255, 0.8);
            }
            
            .timestamp {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .message.user .timestamp {
                color: rgba(255, 255, 255, 0.6);
            }
            
            .text {
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-primary);
                word-wrap: break-word;
            }
            
            .message.user .text {
                color: white;
            }
            
            .text p {
                margin: 0 0 var(--space-3);
            }
            
            .text p:last-child {
                margin-bottom: 0;
            }
            
            .text code {
                font-family: var(--font-mono);
                font-size: 0.875em;
                padding: 3px 8px;
                background: rgba(0, 0, 0, 0.15);
                border-radius: var(--radius-sm);
            }
            
            .message.user .text code {
                background: rgba(255, 255, 255, 0.2);
            }
            
            .text pre {
                margin: var(--space-4) 0;
                padding: var(--space-4);
                background: var(--bg-primary);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                overflow-x: auto;
            }
            
            .text pre code {
                padding: 0;
                background: none;
            }
            
            .streaming .text::after {
                content: '▊';
                color: var(--accent);
                animation: blink 1s infinite;
            }
            
            .stream-pending {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 1.5em;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .chat-line-error {
                margin-top: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                line-height: var(--leading-relaxed);
                color: var(--error, #ef4444);
                background: var(--error-bg, rgba(239, 68, 68, 0.1));
                border: 1px solid var(--error-border, rgba(239, 68, 68, 0.35));
            }
            
            .stream-placeholder-shimmer {
                position: relative;
                flex: 1;
                min-width: 120px;
                max-width: 220px;
                height: 10px;
                border-radius: var(--radius-pill, 999px);
                background: linear-gradient(
                    90deg,
                    var(--glass-tint-subtle) 0%,
                    var(--glass-solid-strong) 50%,
                    var(--glass-tint-subtle) 100%
                );
                background-size: 200% 100%;
                animation: stream-shimmer 1.4s ease-in-out infinite;
            }
            
            @keyframes stream-shimmer {
                0% {
                    background-position: 100% 0;
                }
                100% {
                    background-position: -100% 0;
                }
            }
            
            .assistant-actions {
                margin-top: var(--space-3);
            }

            .activity-line {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            
            .activity-line platform-icon {
                flex-shrink: 0;
                margin-top: 2px;
                color: var(--accent);
            }

            .thinking-row-compact {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .thinking-row-compact.thinking-live {
                color: var(--accent);
            }

            .thinking-row-compact .tool-orb-inner {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                cursor: help;
            }

            .tool-stack {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                margin-top: var(--space-3);
            }

            .tool-orb {
                position: relative;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 30px;
                height: 30px;
                margin-left: -10px;
                border-radius: 50%;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
            }

            .tool-orb:first-child {
                margin-left: 0;
            }

            .tool-orb platform-help-hint {
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .tool-orb-inner {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
            }
            
            @keyframes message-enter {
                from {
                    opacity: 0;
                    transform: translateY(12px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes blink {
                50% { opacity: 0; }
            }
            
            .input-required {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--info-bg);
                border: 1px solid var(--info-border);
                border-radius: var(--radius-lg);
            }

            .input-required-banner {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .input-required-text {
                font-size: var(--text-base);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }

            .oauth-auth-link {
                display: inline-block;
                padding: var(--space-2) var(--space-4);
                background: var(--primary);
                color: var(--on-primary);
                border-radius: var(--radius-md);
                text-decoration: none;
                font-size: var(--text-sm);
                font-weight: 500;
                transition: opacity 0.15s;
            }
            .oauth-auth-link:hover {
                opacity: 0.85;
            }

            .operator-reply {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }

            .operator-reply-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .operator-reply-text {
                font-size: var(--text-base);
                color: var(--text-primary);
            }
            
            .breakpoint {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
                border-radius: var(--radius-lg);
            }
            
            .breakpoint-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .breakpoint-icon {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--warning);
                flex-shrink: 0;
            }
            
            .breakpoint-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--warning);
            }
            
            .breakpoint-message {
                font-size: var(--text-sm);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }
            
            .breakpoint-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .files-container {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            
            .file-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) 0;
                font-size: var(--text-sm);
                text-decoration: none;
                color: inherit;
            }
            
            .file-image {
                width: 48px;
                height: 48px;
                object-fit: cover;
                border-radius: var(--radius-sm);
            }
            
            .file-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }
            
            .file-size {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            
            @media (max-width: 767px) {
                .message {
                    display: block;
                    position: relative;
                }
                
                .message .avatar {
                    position: absolute;
                    top: var(--space-2);
                    width: 28px;
                    height: 28px;
                    z-index: 2;
                }
                
                .message.user .avatar {
                    right: var(--space-2);
                }
                
                .message.assistant .avatar,
                .message.operator .avatar,
                .message.system .avatar {
                    left: var(--space-2);
                }
                
                .bubble {
                    max-width: 100%;
                    width: 100%;
                }
                
                .message.user .content {
                    padding-right: 40px;
                }
                
                .message.assistant .content,
                .message.operator .content,
                .message.system .content {
                    padding-left: 40px;
                }
            }
        `
    ];

    static properties = {
        role: { type: String },
        content: { type: String },
        timestamp: { type: String },
        streaming: { type: Boolean },
        reasoning: { type: String },
        activity: { type: String },
        toolCalls: { type: Array },
        toolResults: { type: Array },
        error: { type: String },
        errorI18nKey: { type: String },
        inputRequired: { type: Object },
        operatorReply: { type: String },
        breakpoint: { type: Object },
        files: { type: Array },
        fileIds: { type: Array },
        taskId: { type: String },
        isLastUserMessage: { type: Boolean, attribute: 'is-last-user-message' },
        runTraceEntries: { type: Array },
        traceTaskId: { type: String },
        _runTracePanelOpen: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.role = 'user';
        this.content = '';
        this.timestamp = '';
        this.streaming = false;
        this.reasoning = '';
        this.activity = '';
        this.toolCalls = [];
        this.toolResults = [];
        this.error = '';
        this.errorI18nKey = null;
        this.inputRequired = null;
        this.operatorReply = '';
        this.breakpoint = null;
        this.files = [];
        this.fileIds = [];
        this.taskId = '';
        this.isLastUserMessage = false;
        this.runTraceEntries = [];
        this.traceTaskId = '';
        this._runTracePanelOpen = false;
        this._i18nLocale = this.select((s) => s.i18n.locale);
        /** @type {(() => void) | null} */
        this._onTtsPrefBound = null;
        /** @type {((e: StorageEvent) => void) | null} */
        this._onTtsStorageBound = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._onTtsPrefBound = () => {
            this.requestUpdate();
        };
        this._onTtsStorageBound = (e) => {
            if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                this.requestUpdate();
            }
        };
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefBound);
            window.addEventListener('storage', this._onTtsStorageBound);
        }
    }

    disconnectedCallback() {
        if (typeof window !== 'undefined') {
            if (this._onTtsPrefBound) {
                window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefBound);
                this._onTtsPrefBound = null;
            }
            if (this._onTtsStorageBound) {
                window.removeEventListener('storage', this._onTtsStorageBound);
                this._onTtsStorageBound = null;
            }
        }
        super.disconnectedCallback();
    }

    _formatMessageTimestamp(iso) {
        if (typeof iso !== 'string' || iso.length === 0) {
            return '';
        }
        const ms = Date.parse(iso);
        if (Number.isNaN(ms)) {
            return iso;
        }
        const locale =
            this._i18nLocale &&
            typeof this._i18nLocale.value === 'string' &&
            this._i18nLocale.value.length > 0
                ? this._i18nLocale.value
                : 'ru';
        return new Intl.DateTimeFormat(locale, {
            dateStyle: 'short',
            timeStyle: 'short',
        }).format(new Date(ms));
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('isLastUserMessage') && !this.isLastUserMessage) {
            this._runTracePanelOpen = false;
        }
    }

    _getRoleName() {
        switch (this.role) {
            case 'user': return this.t('chat_message.role_user');
            case 'assistant': return this.t('chat_message.role_assistant');
            case 'operator': return this.t('chat_message.role_operator');
            case 'system': return this.t('chat_message.role_system');
            default: return this.role;
        }
    }

    _getAvatarIcon() {
        switch (this.role) {
            case 'user': return 'user';
            case 'assistant': return 'bot';
            case 'operator': return 'agent';
            case 'system': return 'info';
            default: return 'chat';
        }
    }

    _renderContent() {
        if (window.marked && this.content) {
            return unsafeHTML(window.marked.parse(this.content));
        }
        return this.content;
    }

    _streamPendingSuppressed() {
        if (this.role !== 'assistant') {
            return false;
        }
        if (asString(this.activity).length > 0) {
            return true;
        }
        if (asString(this.reasoning).length > 0) {
            return true;
        }
        if (asArray(this.toolCalls).length > 0) {
            return true;
        }
        if (asArray(this.toolResults).length > 0) {
            return true;
        }
        return false;
    }

    _pairToolCallsAndResults() {
        const calls = asArray(this.toolCalls);
        const results = asArray(this.toolResults);
        const used = new Set();
        const paired = [];
        for (let i = 0; i < calls.length; i++) {
            const call = calls[i];
            let res = null;
            if (isPlainObject(call) && typeof call.id === 'string' && call.id.length > 0) {
                const callId = call.id;
                for (let j = 0; j < results.length; j++) {
                    if (used.has(j)) {
                        continue;
                    }
                    const item = results[j];
                    if (
                        isPlainObject(item) &&
                        (item.tool_call_id === callId || item.id === callId)
                    ) {
                        res = item;
                        used.add(j);
                        break;
                    }
                }
            }
            if (res === null && !used.has(i) && i < results.length) {
                res = results[i];
                used.add(i);
            }
            paired.push({ call, result: res });
        }
        for (let j = 0; j < results.length; j++) {
            if (used.has(j)) {
                continue;
            }
            paired.push({ call: null, result: results[j] });
        }
        return paired;
    }

    _toolArgsObject(call) {
        if (!isPlainObject(call)) {
            return {};
        }
        if (isPlainObject(call.arguments)) {
            return call.arguments;
        }
        if (isPlainObject(call.args)) {
            return call.args;
        }
        return {};
    }

    _toolResultBody(result) {
        if (!isPlainObject(result) || !Object.prototype.hasOwnProperty.call(result, 'result')) {
            return '';
        }
        const r = result.result;
        if (typeof r === 'string') {
            return r;
        }
        if (r === null || r === undefined) {
            return '';
        }
        return JSON.stringify(r, null, 2);
    }

    _toolRowDisplayName(call, result) {
        if (isPlainObject(call) && typeof call.name === 'string' && call.name.length > 0) {
            return call.name;
        }
        if (isPlainObject(result) && typeof result.name === 'string' && result.name.length > 0) {
            return result.name;
        }
        return this.t('chat_message.tool_default_name');
    }

    _formatToolPairHintText(call, result) {
        const displayName = this._toolRowDisplayName(call, result);
        const parts = [this.t('chat_message.tool_hint_tool_name', { name: displayName })];
        if (isPlainObject(call)) {
            const argsLine = JSON.stringify(this._toolArgsObject(call), null, 2);
            parts.push('');
            parts.push(this.t('chat_message.tool_hint_args_label'));
            parts.push(argsLine);
        }
        if (isPlainObject(result)) {
            const body = this._toolResultBody(result);
            if (body.length > 0) {
                parts.push('');
                parts.push(this.t('chat_message.tool_hint_result_label'));
                parts.push(body);
            }
        }
        return parts.join('\n');
    }

    _renderToolOrbs() {
        const rows = this._pairToolCallsAndResults();
        if (rows.length === 0) {
            return nothing;
        }
        const nameList = rows.map((row) => this._toolRowDisplayName(row.call, row.result)).join(', ');
        return html`
            <div
                class="tool-stack"
                role="group"
                aria-label=${this.t('chat_message.tool_stack_aria', { names: nameList })}
            >
                ${rows.map((row, index) => {
                    const name = this._toolRowDisplayName(row.call, row.result);
                    const icon = toolCallIconName(name);
                    const hint = this._formatToolPairHintText(row.call, row.result);
                    const z = index + 1;
                    return html`
                        <span class="tool-orb" style="z-index: ${z};">
                            <platform-help-hint
                                .text=${hint}
                                .label=${name}
                                ?wide=${true}
                            >
                                <span class="tool-orb-inner" tabindex="0" role="img" aria-label=${name}>
                                    <platform-icon name=${icon} size="16"></platform-icon>
                                </span>
                            </platform-help-hint>
                        </span>
                    `;
                })}
            </div>
        `;
    }

    _renderReasoning() {
        const plain = asString(this.reasoning);
        if (plain.length === 0) {
            return nothing;
        }
        const isLive = this.role === 'assistant' && this.streaming;
        return html`
            <div
                class=${classMap({
                    'thinking-row-compact': true,
                    'thinking-live': isLive,
                })}
            >
                <platform-help-hint
                    .text=${plain}
                    .label=${this.t('chat_message.thinking_aria')}
                    ?wide=${true}
                >
                    <span class="tool-orb-inner" tabindex="0">
                        <platform-icon name="message-circle" size="16"></platform-icon>
                        <span>${this.t('chat_message.thinking_status')}</span>
                    </span>
                </platform-help-hint>
            </div>
        `;
    }

    _renderActivity() {
        if (this.role !== 'assistant') {
            return nothing;
        }
        const a = asString(this.activity);
        if (a.length === 0) {
            return nothing;
        }
        return html`
            <div class="activity-line">
                <platform-icon name="search" size="16"></platform-icon>
                <span>${a}</span>
            </div>
        `;
    }

    _renderAssistantError() {
        if (this.role !== 'assistant') {
            return nothing;
        }
        const k = this.errorI18nKey;
        if (typeof k === 'string' && k.length > 0) {
            return html`
                <div class="chat-line-error" role="alert">
                    ${this.t(`chat_message.${k}`)}
                </div>
            `;
        }
        const e = asString(this.error);
        if (e.length === 0) {
            return nothing;
        }
        return html`
            <div class="chat-line-error" role="alert">
                ${e}
            </div>
        `;
    }

    _renderStreamPending() {
        if (this.role !== 'assistant' || !this.streaming) {
            return nothing;
        }
        if (this._streamPendingSuppressed()) {
            return nothing;
        }
        const c = asString(this.content);
        if (c.length > 0) {
            return nothing;
        }
        return html`
            <div class="text stream-pending" aria-live="polite">
                <span>${this.t('chat_message.streaming_placeholder')}</span>
                <span class="stream-placeholder-shimmer" aria-hidden="true"></span>
            </div>
        `;
    }

    _renderInputRequired() {
        if (!this.inputRequired) return '';

        const kind = this.inputRequired.interruptKind;

        if (kind === 'oauth_required' && this.inputRequired.authUrl) {
            return html`
                <div class="input-required">
                    <div class="input-required-banner">${this.t('chat_message.interrupt_oauth_banner')}</div>
                    <div class="input-required-text">
                        ${window.marked ? unsafeHTML(window.marked.parse(this.inputRequired.question)) : this.inputRequired.question}
                    </div>
                    <a
                        class="oauth-auth-link"
                        href="${this.inputRequired.authUrl}"
                        target="_blank"
                        rel="noopener noreferrer"
                    >${this.t('chat_message.interrupt_oauth_button')}</a>
                </div>
            `;
        }

        const banner =
            kind === 'operator_task'
                ? html`<div class="input-required-banner">${this.t('chat_message.interrupt_operator_banner')}</div>`
                : nothing;

        return html`
            <div class="input-required">
                ${banner}
                <div class="input-required-text">
                    ${window.marked ? unsafeHTML(window.marked.parse(this.inputRequired.question)) : this.inputRequired.question}
                </div>
            </div>
        `;
    }

    _renderOperatorReply() {
        const reply = this.operatorReply ? String(this.operatorReply).trim() : '';
        const t = reply;
        if (!t) {
            return '';
        }
        return html`
            <div class="operator-reply">
                <div class="operator-reply-label">${this.t('chat_message.operator_reply_heading')}</div>
                <div class="operator-reply-text">
                    ${window.marked ? unsafeHTML(window.marked.parse(t)) : t}
                </div>
            </div>
        `;
    }

    _renderBreakpoint() {
        if (!this.breakpoint) return '';
        
        return html`
            <div class="breakpoint">
                <div class="breakpoint-header">
                    <span class="breakpoint-icon" aria-hidden="true"></span>
                    <span class="breakpoint-title">Breakpoint: ${this.breakpoint.nodeId}</span>
                </div>
                <div class="breakpoint-message">
                    ${window.marked ? unsafeHTML(window.marked.parse(this.breakpoint.message)) : this.breakpoint.message}
                </div>
                <div class="breakpoint-actions">
                    <button class="btn" @click=${this._continueBreakpoint}>${this.t('chat_message.breakpoint_continue')}</button>
                    <button class="btn" @click=${this._viewBreakpointState}>${this.t('chat_message.breakpoint_view_state')}</button>
                </div>
            </div>
        `;
    }

    _voiceBaseUrlForAssistantPlay() {
        if (!readTtsOutputEnabled()) {
            return '';
        }
        return resolveFlowVoiceHttpOrigin();
    }

    _renderAssistantActions() {
        if (this.role !== 'assistant') {
            return nothing;
        }
        if (this.streaming) {
            return nothing;
        }
        const text = asString(this.content).trim();
        if (text.length === 0) {
            return nothing;
        }
        const base = this._voiceBaseUrlForAssistantPlay();
        return html`
            <div class="assistant-actions">
                <platform-assistant-message-actions
                    .text=${text}
                    voice-base-url=${base}
                    credentials="include"
                ></platform-assistant-message-actions>
            </div>
        `;
    }

    _continueBreakpoint() {
        this.emit('continue-breakpoint', { breakpoint: this.breakpoint });
    }

    _viewBreakpointState() {
        this.emit('view-breakpoint-state', { breakpoint: this.breakpoint });
    }

    _showTracing() {
        const fromTask = asString(this.taskId);
        if (fromTask.length > 0) {
            this.emit('show-tracing', { taskId: fromTask });
            return;
        }
        const fromArg = asString(this.traceTaskId);
        this.emit('show-tracing', { taskId: fromArg.length > 0 ? fromArg : '' });
    }

    _toggleUserRunTrace() {
        this._runTracePanelOpen = !this._runTracePanelOpen;
    }

    _renderOperatorFiles() {
        if (!this.fileIds || this.fileIds.length === 0) return '';
        return html`
            <div class="files-container">
                ${this.fileIds.map(
                    (fid) => html`
                        <a
                            class="file-item"
                            href="/flows/api/v1/files/download/${fid}"
                            target="_blank"
                            rel="noopener"
                            style="text-decoration:none;color:inherit;cursor:pointer;"
                        >
                            <platform-icon name="file" size="20"></platform-icon>
                            <div>
                                <div class="file-name">${this.t('chat_message.operator_files')}</div>
                            </div>
                        </a>
                    `,
                )}
            </div>
        `;
    }

    _renderFiles() {
        if (!this.files || this.files.length === 0) return '';
        
        return html`
            <div class="files-container">
                ${this.files.map(file => this._renderFile(file))}
            </div>
        `;
    }

    _renderFile(file) {
        const isImage = file.type && file.type.startsWith('image/');
        const iconKey = isImage ? 'image' : resolveFileIconKey(asString(file.name), asString(file.type));

        return html`
            <div class="file-item">
                <platform-icon file-icon name=${iconKey} size="20"></platform-icon>
                <div>
                    <div class="file-name">${file.name}</div>
                    ${file.size ? html`<div class="file-size">${this._formatFileSize(file.size)}</div>` : ''}
                </div>
            </div>
        `;
    }

    _formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    _renderUserInlineRunTrace() {
        if (this.role !== 'user' || !this.isLastUserMessage) {
            return nothing;
        }
        if (!this._runTracePanelOpen) {
            return nothing;
        }
        return html`
            <div class="user-run-trace-embed">
                <flows-chat-run-trace
                    .entries=${asArray(this.runTraceEntries)}
                    ?compact=${true}
                    ?showSectionHeader=${true}
                ></flows-chat-run-trace>
            </div>
        `;
    }

    _renderUserHeader() {
        const hasTools = this.isLastUserMessage;
        if (!hasTools) {
            return html`
                <div class="header">
                    <span class="role">${this._getRoleName()}</span>
                    ${this.timestamp
                        ? html`<span class="timestamp">${this._formatMessageTimestamp(this.timestamp)}</span>`
                        : ''}
                </div>
            `;
        }
        return html`
            <div class="header has-inline-tools">
                <div class="user-header-meta">
                    <span class="role">${this._getRoleName()}</span>
                    ${this.timestamp
                        ? html`<span class="timestamp">${this._formatMessageTimestamp(this.timestamp)}</span>`
                        : ''}
                </div>
                <div class="header-actions">
                    <button
                        type="button"
                        class="tracing-btn user-bubble-tool"
                        @click=${this._toggleUserRunTrace}
                        title=${this.t('run_trace.section_title')}
                        aria-pressed=${this._runTracePanelOpen ? 'true' : 'false'}
                    >
                        <platform-icon name="chart" size="14"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="tracing-btn user-bubble-tool"
                        @click=${this._showTracing}
                        title=${this.t('chat_message.show_tracing_title')}
                    >
                        <platform-icon name="terminal" size="14"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _renderDefaultHeader() {
        return html`
            <div class="header">
                <span class="role">${this._getRoleName()}</span>
                ${this.timestamp
                    ? html`<span class="timestamp">${this._formatMessageTimestamp(this.timestamp)}</span>`
                    : ''}
                ${this.role === 'assistant' && this.taskId && !this.streaming
                    ? html`
                          <div class="header-actions">
                              <button
                                  type="button"
                                  class="tracing-btn"
                                  @click=${this._showTracing}
                                  title=${this.t('chat_message.show_tracing_title')}
                              >
                                  <platform-icon name="terminal" size="14"></platform-icon>
                              </button>
                          </div>
                      `
                    : nothing}
            </div>
        `;
    }

    render() {
        const classes = {
            'message': true,
            [this.role]: true,
            'streaming': this.streaming,
        };

        return html`
            <div class=${classMap(classes)}>
                <div class="avatar">
                    <platform-icon name=${this._getAvatarIcon()} size="18"></platform-icon>
                </div>
                <div class="bubble">
                    <div class="content">
                        ${this.role === 'user' ? this._renderUserHeader() : this._renderDefaultHeader()}
                        ${this._renderUserInlineRunTrace()}
                        ${this._renderFiles()}
                        ${this._renderOperatorFiles()}
                        ${this._renderActivity()}
                        ${this._renderToolOrbs()}
                        ${this._renderReasoning()}
                        ${this.content ? html`<div class="text">${this._renderContent()}</div>` : ''}
                        ${this._renderStreamPending()}
                        ${this._renderAssistantError()}
                        ${this._renderInputRequired()}
                        ${this._renderOperatorReply()}
                        ${this._renderBreakpoint()}
                        ${this._renderAssistantActions()}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('chat-message', ChatMessage);

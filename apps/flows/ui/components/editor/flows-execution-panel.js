/**
 * flows-execution-panel — плавающая панель «Запуск агента» в редакторе.
 *
 * Видна, пока `state.flowsEditor.executionPanelOpen === true`. Источники state:
 *   - useOp('flows/editor') — режим, currentSkillId, previewExecutionState.breakpoints;
 *   - useResource('flows/chat') — currentContextId/currentTaskId/streaming, сообщения;
 *   - useOp('flows/chat_send') / useOp('flows/chat_cancel') — SSE A2A
 *     (`POST /flows/api/v1/{flow_id}` с `message/stream` / `tasks/cancel`);
 *   - useSlice('flows/execution_ui') — локальный ввод, прикреплённые файлы,
 *     persistContext и mock-ответы для LLM.
 *
 * Вкладка Chat: лента `chat-message` из `flows/chat` (тот же bucket, что и SSE).
 * Разворот — кнопка в шапке: `position: fixed` + `nextModalLayerZIndex()`, иначе z-index
 * не выходит из `canvas-host` и панель свойств (`flows-floating-panel`, до 25100) перекрывает.
 * Снизу — `--flows-exec-fab-gutter`, чтобы поле ввода не заезжало на FAB embed-ассистента.
 * Кнопки State / Tracing / Mocks открывают модалки `flows.state`, `flows.tracing`,
 * `flows.mocks`. «Сбросить чат» вызывает `flows/chat` `resetSession` (и `tasks/cancel` при
 * активном стриме). Mocks редактируются модалкой через slice — их payload идёт
 * в `params.metadata.mock` команды `flows/chat_send`.
 */

import { html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/glass-button.js';
import '../chat/flows-chat-run-trace.js';
import '../chat/chat-message.js';
import {
    asArray,
    asObject,
    asString,
    deriveRunPanelStatus,
} from '../../_helpers/flows-resolvers.js';

const ACCEPT_FILE_TYPES = '*/*';
const EMPTY_TRACE = Object.freeze([]);

function _readAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result;
            if (typeof result !== 'string') {
                reject(new Error('execution-panel: file read result is not a string'));
                return;
            }
            const comma = result.indexOf(',');
            const bytes = comma >= 0 ? result.slice(comma + 1) : '';
            resolve(bytes);
        };
        reader.onerror = () => reject(reader.error ? reader.error : new Error('file read failed'));
        reader.readAsDataURL(file);
    });
}

export class FlowsExecutionPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String },
        skillId: { type: String },
        _panelTab: { type: String, state: true },
        _layoutExpanded: { type: Boolean, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                /* Зазор под FAB embed-чата (56px + bottom 16px + запас), см. platform-embed-chat-drawer .fab */
                --flows-exec-fab-gutter: calc(56px + max(16px, env(safe-area-inset-bottom, 0px)) + 12px);
                position: absolute;
                top: 12px;
                right: 12px;
                bottom: calc(12px + var(--flows-exec-fab-gutter));
                left: auto;
                z-index: 5;
                display: flex;
                flex-direction: column;
                width: min(460px, calc(100% - 24px));
                max-width: none;
                min-height: 0;
                pointer-events: none;
            }
            :host([data-layout-expanded]) {
                position: fixed;
                top: 12px;
                right: 12px;
                bottom: calc(12px + var(--flows-exec-fab-gutter));
                left: 12px;
                width: auto;
            }
            .panel {
                pointer-events: auto;
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                overflow: hidden;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                box-shadow: var(--glass-shadow-medium);
                backdrop-filter: blur(20px);
            }
            .panel-header {
                flex-shrink: 0;
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                flex-wrap: wrap;
            }
            .panel-header-main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .panel-header-aside {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }
            .panel-title-row {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }
            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .status-badge {
                display: inline-flex;
                align-items: center;
                width: fit-content;
                padding: 2px 10px;
                border-radius: var(--radius-full);
                font-size: 11px;
                font-weight: var(--font-semibold);
                letter-spacing: 0.02em;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            .status-badge[data-status='running'] {
                border-color: var(--warning-border, rgba(234, 179, 8, 0.45));
                background: var(--warning-bg, rgba(234, 179, 8, 0.12));
                color: var(--warning, #ca8a04);
                animation: execPanelPulse 1.4s ease-in-out infinite;
            }
            .status-badge[data-status='passed'] {
                border-color: var(--success-border);
                background: var(--success-bg);
                color: var(--success, #16a34a);
            }
            .status-badge[data-status='failed'] {
                border-color: var(--error-border);
                background: var(--error-bg);
                color: var(--error);
            }
            @keyframes execPanelPulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.72; }
            }
            .tabs {
                flex-shrink: 0;
                display: flex;
                gap: 2px;
                padding: 4px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-inner-glow-subtle);
            }
            .tab {
                flex: 1;
                min-height: 36px;
                padding: 8px 12px;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast), box-shadow var(--duration-fast);
            }
            .tab:hover {
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
            }
            .tab[data-active] {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-inner-glow-medium), var(--glass-shadow-subtle);
            }
            .tab-toolbar {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: flex-end;
            }
            .icon-btn-close {
                box-sizing: border-box;
                width: 36px;
                height: 36px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .icon-btn-close:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .panel-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: hidden;
            }
            .tab-panel {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: hidden;
            }
            .tab-panel[data-tab='chat'] .compose {
                flex-shrink: 0;
                margin-top: auto;
            }
            .trace-panel-inner {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .trace-panel-inner flows-chat-run-trace {
                flex: 1;
                min-height: 0;
            }
            .state-tab {
                padding: var(--space-4);
                border-radius: var(--radius-xl);
                border: 1px dashed var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                align-items: stretch;
            }
            .state-tab-hint {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.5;
                margin: 0;
            }
            .message-feed {
                flex: 1;
                min-height: 0;
                overflow-x: hidden;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-2) 2px var(--space-2) 0;
            }
            .compose {
                position: relative;
                display: block;
                width: 100%;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                transition: border-color var(--duration-fast);
            }
            .compose:focus-within {
                border-color: var(--accent);
            }
            .compose textarea {
                display: block;
                width: 100%;
                min-height: 84px;
                max-height: 180px;
                resize: none;
                margin: 0;
                padding: var(--space-3) var(--space-4);
                padding-right: calc(36px + var(--space-2) + 36px + var(--space-3));
                padding-bottom: calc(36px + var(--space-3));
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                line-height: 1.45;
                box-sizing: border-box;
            }
            .compose textarea:focus {
                outline: none;
            }
            .compose-actions {
                position: absolute;
                right: var(--space-2);
                bottom: var(--space-2);
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-2);
                pointer-events: none;
            }
            .compose-actions glass-button {
                pointer-events: auto;
            }
            .file-input-hidden {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                white-space: nowrap;
                border: 0;
            }
            .files-row {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .file-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 6px 2px 8px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                max-width: 200px;
            }
            .file-chip span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .file-chip button {
                width: 18px;
                height: 18px;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 14px;
                line-height: 1;
                padding: 0;
            }
            .file-chip button:hover { color: var(--text-primary); }
            .persist-wrap {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._panelTab = 'chat';
        this._editor = this.useOp('flows/editor');
        this._chat = this.useResource('flows/chat');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
        this._ui = this.useSlice('flows/execution_ui');
        this._lastChatCtx = '';
        this._lastChatLen = 0;
        this._layoutExpanded = false;
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (this._panelTab !== 'chat') {
            return;
        }
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : '';
        if (ctx !== this._lastChatCtx) {
            this._lastChatCtx = ctx;
            this._lastChatLen = this._panelChatMessages().length;
            this._scrollChatFeedBottom();
            return;
        }
        const n = this._panelChatMessages().length;
        const grew = n > this._lastChatLen;
        this._lastChatLen = n;
        if (grew || Boolean(chatState.streaming)) {
            this._scrollChatFeedBottom();
        }
    }

    _scrollChatFeedBottom() {
        requestAnimationFrame(() => {
            const root = this.renderRoot;
            if (!root || typeof root.querySelector !== 'function') {
                return;
            }
            const el = root.querySelector('.message-feed');
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    _panelChatMessages() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : null;
        if (!ctx) {
            return [];
        }
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) {
            return [];
        }
        return bucket.messages;
    }

    _ensureContextId() {
        const chatState = this._chat.state;
        const ctx = chatState && typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (ctx && ctx.length > 0) return ctx;
        this._chat.initSession({ flowId: this.flowId, contextId: `editor_${Date.now()}` });
        const after = this._chat.state;
        if (!after || typeof after.currentContextId !== 'string' || after.currentContextId.length === 0) {
            throw new Error('flows-execution-panel: failed to init chat context');
        }
        return after.currentContextId;
    }

    _lastAssistantMessage() {
        const chatState = this._chat.state;
        const ctx = chatState && typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) return null;
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) return null;
        for (let i = bucket.messages.length - 1; i >= 0; i--) {
            const m = bucket.messages[i];
            if (m && m.role === 'assistant') return m;
        }
        return null;
    }

    /** Ассистент текущего task_id (чтобы не показывать ответ прошлого запуска до первого чанка). */
    _activeAssistantMessage() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) {
            return null;
        }
        const tid = typeof chatState.currentTaskId === 'string'
            ? chatState.currentTaskId
            : null;
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) {
            return null;
        }
        if (tid) {
            for (let i = bucket.messages.length - 1; i >= 0; i -= 1) {
                const m = bucket.messages[i];
                if (m && m.role === 'assistant' && m.taskId === tid) {
                    return m;
                }
            }
        }
        return this._lastAssistantMessage();
    }

    _currentRunTrace() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) {
            return EMPTY_TRACE;
        }
        const byCtx = chatState.runTraceByContextId;
        if (!byCtx || typeof byCtx !== 'object') {
            return EMPTY_TRACE;
        }
        const list = byCtx[ctx];
        if (!Array.isArray(list)) {
            return EMPTY_TRACE;
        }
        return list;
    }

    _onPersistChange(e) {
        const value = Boolean(e.detail && e.detail.value);
        this._ui.togglePersistContext({ value });
    }

    _onInputChange(e) {
        this._ui.setInputText({ text: asString(e.target.value) });
    }

    /**
     * @param {KeyboardEvent} e
     */
    _onComposeKeydown(e) {
        if (e.isComposing) {
            return;
        }
        if (e.key !== 'Enter' || e.shiftKey) {
            return;
        }
        e.preventDefault();
        void this._onRun();
    }

    _toggleLayoutExpanded() {
        this._layoutExpanded = !this._layoutExpanded;
        if (this._layoutExpanded) {
            this.style.zIndex = String(nextModalLayerZIndex());
            this.setAttribute('data-layout-expanded', '');
        } else {
            this.style.zIndex = '';
            this.removeAttribute('data-layout-expanded');
        }
    }

    async _handleFileSelect(e) {
        const list = e.target.files;
        if (!list || list.length === 0) return;
        const files = Array.from(list);
        const prepared = await Promise.all(files.map(async (file) => ({
            name: file.name,
            size: file.size,
            type: typeof file.type === 'string' && file.type.length > 0 ? file.type : 'application/octet-stream',
            bytes: await _readAsBase64(file),
        })));
        this._ui.addFiles({ files: prepared });
        e.target.value = '';
    }

    _pickAttachedFiles() {
        const root = this.renderRoot;
        if (!root || typeof root.getElementById !== 'function') {
            throw new Error('flows-execution-panel: renderRoot unavailable');
        }
        const input = root.getElementById('flows-exec-file-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('flows-execution-panel: file input missing');
        }
        input.click();
    }

    _removeFile(index) {
        this._ui.removeFile({ index });
    }

    async _onRun() {
        if (!this.flowId) return;
        const editorState = asObject(this._editor.state);
        const chatStateBefore = asObject(this._chat.state);
        if (this._send.busy || editorState.agentExecutionRunning || chatStateBefore.streaming) {
            return;
        }

        const ui = this._ui.value;
        const text = asString(ui.inputText).trim();
        const files = asArray(ui.attachedFiles);
        if (text.length === 0 && files.length === 0) return;

        const hasContext = Boolean(chatStateBefore.currentContextId);
        if (!ui.persistContext || !hasContext) {
            this._chat.resetSession({});
        }
        const contextId = this._ensureContextId();

        const userMessage = {
            id: `user_${Date.now()}`,
            role: 'user',
            content: text,
            timestamp: new Date().toISOString(),
            files: files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
        };
        this._chat.addUserMessage({ contextId, message: userMessage });

        const parts = [{ kind: 'text', text }];
        for (const f of files) {
            parts.push({
                kind: 'file',
                file: { name: f.name, mimeType: f.type, bytes: f.bytes },
            });
        }

        this._ui.clear({});
        const a2aMessage = {
            messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
            role: 'user',
            parts,
            contextId,
        };

        const metadata = {};
        if (this.skillId && this.skillId !== 'base') {
            metadata.skill = this.skillId;
        }
        const preview = editorState.previewExecutionState;
        const bps = preview && preview.breakpoints;
        if (Array.isArray(bps) && bps.length > 0) {
            metadata.breakpoints = bps;
        }
        if (Array.isArray(ui.mockResponses) && ui.mockResponses.length > 0) {
            metadata.mock = {
                enabled: true,
                llm: ui.mockResponses.map((m) => ({
                    type: 'text',
                    content: m.response,
                    match: m.match,
                })),
            };
        }

        const params = { message: a2aMessage };
        if (Object.keys(metadata).length > 0) {
            params.metadata = metadata;
        }

        this._editor.setAgentExecutionRunning({ running: true });
        try {
            await this._send.run({ flow_id: this.flowId, params });
        } finally {
            this._editor.setAgentExecutionRunning({ running: false });
        }
    }

    _onStop() {
        const chatState = this._chat.state;
        const taskId = chatState && chatState.currentTaskId;
        if (typeof taskId !== 'string' || taskId.length === 0) return;
        void this._cancel.run({ flow_id: this.flowId, task_id: taskId });
    }

    _onClose() {
        this._layoutExpanded = false;
        this.style.zIndex = '';
        this.removeAttribute('data-layout-expanded');
        this._editor.setExecutionPanelOpen({ open: false });
        this._editor.setMode({ mode: 'edit' });
    }

    _buildSessionId() {
        const chatState = this._chat.state;
        const ctx = chatState && chatState.currentContextId;
        if (!this.flowId || typeof ctx !== 'string' || ctx.length === 0) return '';
        return `${this.flowId}:${ctx}`;
    }

    _openState() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        this.openModal('flows.state', { sessionId });
    }

    _openTracing() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        this.openModal('flows.tracing', { sessionId });
    }

    _openMocks() {
        this.openModal('flows.mocks', {});
    }

    /**
     * Новая сессия чата: остановка текущей задачи при необходимости, сброс контекста и поля ввода.
     */
    async _onResetChat() {
        if (!this.flowId) {
            return;
        }
        const chatState = asObject(this._chat.state);
        const taskId = typeof chatState.currentTaskId === 'string' ? chatState.currentTaskId : '';
        if (Boolean(chatState.streaming) && taskId.length > 0) {
            await this._cancel.run({ flow_id: this.flowId, task_id: taskId });
        }
        this._editor.setAgentExecutionRunning({ running: false });
        this._chat.resetSession({});
        this._ui.clear({});
    }

    _setPanelTab(tab) {
        if (tab !== 'chat' && tab !== 'trace' && tab !== 'state') {
            throw new Error('flows-execution-panel: invalid tab');
        }
        this._panelTab = tab;
    }

    render() {
        const editorState = asObject(this._editor.state);
        if (!editorState.executionPanelOpen) return nothing;

        const ui = this._ui.value;
        const chatState = asObject(this._chat.state);
        const streaming = Boolean(chatState.streaming);
        const sendBusy = this._send.busy;
        const agentRun = Boolean(editorState.agentExecutionRunning);
        const runInFlight = streaming || sendBusy || agentRun;
        const hasContext = typeof chatState.currentContextId === 'string'
            && chatState.currentContextId.length > 0;
        const lastAssistant = this._activeAssistantMessage();
        const inputRequired = Boolean(lastAssistant && lastAssistant.inputRequired);
        const placeholderKey = inputRequired
            ? 'execution_panel.placeholder_answer'
            : 'execution_panel.placeholder_message';
        const runDisabled = runInFlight
            ? false
            : (ui.inputText.trim().length === 0 && ui.attachedFiles.length === 0);

        const runTrace = this._currentRunTrace();
        const panelMessages = this._panelChatMessages();
        const taskId = typeof chatState.currentTaskId === 'string'
            ? chatState.currentTaskId
            : null;
        const panelStatus = deriveRunPanelStatus({
            runInFlight,
            taskId,
            activeAssistant: lastAssistant,
            runTrace,
        });
        const statusLabelKey = `execution_panel.status_${panelStatus}`;
        const tab = this._panelTab;

        return html`
            <div class="panel" role="region" aria-label=${this.t('execution_panel.title')}>
                <div class="panel-header">
                    <div class="panel-header-main">
                        <div class="panel-title-row">
                            <div class="panel-title">
                                <platform-icon name="play" size="14"></platform-icon>
                                ${this.t('execution_panel.title')}
                            </div>
                            <span class="status-badge" data-status=${panelStatus}>${this.t(statusLabelKey)}</span>
                        </div>
                    </div>
                    <div class="panel-header-aside">
                        <div class="persist-wrap">
                            <platform-switch
                                size="sm"
                                ?checked=${ui.persistContext}
                                @change=${this._onPersistChange}
                                aria-label=${this.t('execution_panel.persist_aria')}
                            ></platform-switch>
                            <platform-help-hint
                                label=${this.t('execution_panel.help_hint_label')}
                                text=${this.t('execution_panel.persist_context_help')}
                            ></platform-help-hint>
                        </div>
                        <button
                            class="icon-btn-close"
                            type="button"
                            title=${this._layoutExpanded
                                ? this.t('execution_panel.collapse_panel')
                                : this.t('execution_panel.expand_panel')}
                            aria-expanded=${this._layoutExpanded ? 'true' : 'false'}
                            @click=${this._toggleLayoutExpanded}
                        >
                            <platform-icon
                                name=${this._layoutExpanded ? 'minimize' : 'fullscreen'}
                                size="14"
                            ></platform-icon>
                        </button>
                        <button
                            class="icon-btn-close"
                            type="button"
                            title=${this.t('execution_panel.close_panel')}
                            @click=${this._onClose}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                        </button>
                    </div>
                </div>

                <div class="tabs" role="tablist">
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'chat'}
                        aria-selected=${tab === 'chat' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('chat'); }}
                    >${this.t('execution_panel.tab_chat')}</button>
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'trace'}
                        aria-selected=${tab === 'trace' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('trace'); }}
                    >${this.t('execution_panel.tab_trace')}</button>
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'state'}
                        aria-selected=${tab === 'state' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('state'); }}
                    >${this.t('execution_panel.tab_state')}</button>
                </div>

                ${tab === 'chat' || tab === 'trace'
                    ? html`
                        <div class="tab-toolbar">
                            ${tab === 'trace' ? html`
                                <glass-button
                                    variant="primary"
                                    size="sm"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.full_trace_title')}
                                    @click=${this._openTracing}
                                >${this.t('execution_panel.full_trace')}</glass-button>
                            ` : nothing}
                            ${tab === 'chat' ? html`
                                <glass-button
                                    variant="secondary"
                                    size="sm"
                                    title=${this.t('execution_panel.reset_chat_title')}
                                    @click=${() => { void this._onResetChat(); }}
                                >${this.t('execution_panel.reset_chat')}</glass-button>
                            ` : nothing}
                            <glass-button
                                variant="secondary"
                                size="sm"
                                title=${this.t('execution_panel.mocks_title')}
                                @click=${this._openMocks}
                            >${this.t('execution_panel.mocks_title')}</glass-button>
                        </div>
                    `
                    : nothing}

                <div class="panel-body">
                    <div class="tab-panel" data-tab=${tab}>
                        ${tab === 'chat' ? html`
                            ${ui.attachedFiles.length > 0 ? html`
                                <div class="files-row">
                                    ${ui.attachedFiles.map((f, i) => html`
                                        <div class="file-chip" title=${f.name}>
                                            <platform-icon name="paperclip" size="12"></platform-icon>
                                            <span>${f.name}</span>
                                            <button type="button" @click=${() => this._removeFile(i)}>×</button>
                                        </div>
                                    `)}
                                </div>
                            ` : nothing}
                            ${panelMessages.length > 0 ? html`
                                <div class="message-feed">
                                    ${repeat(
                                        panelMessages,
                                        (m, i) => {
                                            if (m && typeof m.id === 'string' && m.id.length > 0) {
                                                return m.id;
                                            }
                                            const role = m && typeof m.role === 'string' ? m.role : 'msg';
                                            const tid = m && typeof m.taskId === 'string' ? m.taskId : '';
                                            return `${role}_${tid}_${i}`;
                                        },
                                        (message) => html`
                                            <chat-message
                                                .role=${asString(message.role)}
                                                .content=${typeof message.content === 'string' ? message.content : ''}
                                                .timestamp=${asString(message.timestamp)}
                                                ?streaming=${Boolean(message.streaming)}
                                                .reasoning=${asString(message.reasoning)}
                                                .activity=${asString(message.activity)}
                                                .toolCalls=${asArray(message.toolCalls)}
                                                .toolResults=${asArray(message.toolResults)}
                                                .inputRequired=${message.inputRequired != null ? message.inputRequired : null}
                                                .operatorReply=${asString(message.operatorReply)}
                                                .breakpoint=${message.breakpoint != null ? message.breakpoint : null}
                                                .files=${asArray(message.files)}
                                                .fileIds=${asArray(message.fileIds)}
                                                .taskId=${asString(message.taskId)}
                                            ></chat-message>
                                        `,
                                    )}
                                </div>
                            ` : nothing}
                            <div class="compose">
                                <input
                                    id="flows-exec-file-input"
                                    class="file-input-hidden"
                                    type="file"
                                    multiple
                                    accept=${ACCEPT_FILE_TYPES}
                                    @change=${this._handleFileSelect}
                                />
                                <textarea
                                    .value=${ui.inputText}
                                    placeholder=${this.t(placeholderKey)}
                                    @input=${this._onInputChange}
                                    @keydown=${this._onComposeKeydown}
                                ></textarea>
                                <div class="compose-actions">
                                    <glass-button
                                        variant="secondary"
                                        size="sm"
                                        iconOnly
                                        title=${this.t('execution_panel.attach_files')}
                                        type="button"
                                        @click=${this._pickAttachedFiles}
                                    >
                                        <platform-icon name="paperclip" size="16"></platform-icon>
                                    </glass-button>
                                    ${runInFlight ? html`
                                        <glass-button
                                            variant="danger"
                                            size="sm"
                                            iconOnly
                                            type="button"
                                            title=${this.t('execution_panel.stop')}
                                            @click=${this._onStop}
                                        >
                                            <platform-icon name="stop" size="16"></platform-icon>
                                        </glass-button>
                                    ` : html`
                                        <glass-button
                                            variant="primary"
                                            size="sm"
                                            iconOnly
                                            type="button"
                                            ?disabled=${runDisabled || sendBusy}
                                            title=${this.t('execution_panel.run_start')}
                                            @click=${this._onRun}
                                        >
                                            <platform-icon name="play" size="16"></platform-icon>
                                        </glass-button>
                                    `}
                                </div>
                            </div>
                        ` : nothing}

                        ${tab === 'trace' ? html`
                            <div class="trace-panel-inner">
                                <flows-chat-run-trace
                                    .entries=${runTrace}
                                    compact
                                    .showSectionHeader=${false}
                                    .fillAvailable=${true}
                                ></flows-chat-run-trace>
                            </div>
                        ` : nothing}

                        ${tab === 'state' ? html`
                            <div class="state-tab">
                                <p class="state-tab-hint">${this.t('execution_panel.state_tab_hint')}</p>
                                <glass-button
                                    variant="secondary"
                                    size="sm"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.state_title')}
                                    @click=${this._openState}
                                >${this.t('execution_panel.open_state')}</glass-button>
                            </div>
                        ` : nothing}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);

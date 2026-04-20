/**
 * flows-execution-panel — плавающая панель «Запуск агента» в редакторе.
 *
 * Видна, пока `state.flowsEditor.executionPanelOpen === true`. Источники state:
 *   - useOp('flows/editor') — режим, currentSkillId, previewExecutionState.breakpoints;
 *   - useResource('flows/chat') — currentContextId/currentTaskId/streaming + сообщения;
 *   - useOp('flows/chat_send') / useOp('flows/chat_cancel') — SSE A2A
 *     (`POST /flows/api/v1/{flow_id}` с `message/stream` / `tasks/cancel`);
 *   - useSlice('flows/execution_ui') — локальный ввод, прикреплённые файлы,
 *     persistContext и mock-ответы для LLM.
 *
 * Кнопки State / Tracing / Mocks открывают модалки `flows.state`, `flows.tracing`,
 * `flows.mocks`. Mocks редактируются модалкой через slice — их payload идёт
 * в `params.metadata.mock` команды `flows/chat_send`.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import { asArray, asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';

const ACCEPT_FILE_TYPES = '*/*';

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
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                top: 12px;
                right: 12px;
                z-index: 5;
                display: block;
                width: min(420px, calc(100% - 24px));
                pointer-events: none;
            }
            .panel {
                pointer-events: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong);
                backdrop-filter: blur(20px);
            }
            .panel-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-right: auto;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .header-actions { display: inline-flex; gap: 4px; align-items: center; }
            .header-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 4px;
                padding: 4px 8px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .header-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .header-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }
            .icon-btn {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .body {
                display: flex;
                gap: var(--space-2);
                align-items: flex-end;
            }
            .body textarea {
                flex: 1;
                min-height: 56px;
                max-height: 180px;
                resize: vertical;
                padding: var(--space-2);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                box-sizing: border-box;
            }
            .body textarea:focus {
                outline: none;
                border-color: var(--accent);
            }
            .body-actions {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .file-attach-btn {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .file-attach-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .file-attach-btn input { display: none; }
            .run-btn {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--accent);
                color: var(--text-inverse);
                border: 1px solid var(--accent);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .run-btn:hover {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
            }
            .run-btn[data-stop] {
                background: var(--danger);
                border-color: var(--danger);
            }
            .run-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .files-row {
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
            .answer {
                padding: var(--space-2);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
                max-height: 220px;
                overflow-y: auto;
            }
            .answer.error {
                color: var(--danger);
                border-color: var(--danger-border);
                background: var(--danger-bg);
            }
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
        this._editor = this.useOp('flows/editor');
        this._chat = this.useResource('flows/chat');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
        this._ui = this.useSlice('flows/execution_ui');
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

    _onPersistChange(e) {
        const value = Boolean(e.detail && e.detail.value);
        this._ui.togglePersistContext({ value });
    }

    _onInputChange(e) {
        this._ui.setInputText({ text: asString(e.target.value) });
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

    _removeFile(index) {
        this._ui.removeFile({ index });
    }

    async _onRun() {
        if (!this.flowId) return;
        const ui = this._ui.value;
        const text = asString(ui.inputText).trim();
        const files = asArray(ui.attachedFiles);
        if (text.length === 0 && files.length === 0) return;

        const chatState = this._chat.state;
        const hasContext = Boolean(chatState && chatState.currentContextId);
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
        const editorState = this._editor.state;
        const preview = editorState && editorState.previewExecutionState;
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
        this._ui.clear({});
    }

    _onStop() {
        const chatState = this._chat.state;
        const taskId = chatState && chatState.currentTaskId;
        if (typeof taskId !== 'string' || taskId.length === 0) return;
        void this._cancel.run({ flow_id: this.flowId, task_id: taskId });
    }

    _onClose() {
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

    render() {
        const editorState = asObject(this._editor.state);
        if (!editorState.executionPanelOpen) return nothing;

        const ui = this._ui.value;
        const chatState = asObject(this._chat.state);
        const streaming = Boolean(chatState.streaming);
        const hasContext = typeof chatState.currentContextId === 'string'
            && chatState.currentContextId.length > 0;
        const lastAssistant = this._lastAssistantMessage();
        const inputRequired = Boolean(lastAssistant && lastAssistant.inputRequired);
        const placeholderKey = inputRequired
            ? 'execution_panel.placeholder_answer'
            : 'execution_panel.placeholder_message';
        const runDisabled = streaming
            ? false
            : (ui.inputText.trim().length === 0 && ui.attachedFiles.length === 0);
        const sendBusy = this._send.busy;

        return html`
            <div class="panel" role="region" aria-label=${this.t('execution_panel.title')}>
                <div class="panel-header">
                    <div class="panel-title">
                        <platform-icon name="play" size="14"></platform-icon>
                        ${this.t('execution_panel.title')}
                    </div>
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
                    <div class="header-actions">
                        <button
                            class="header-btn"
                            type="button"
                            ?disabled=${!hasContext}
                            title=${this.t('execution_panel.state_title')}
                            @click=${this._openState}
                        >${this.t('execution_panel.state_title')}</button>
                        <button
                            class="header-btn"
                            type="button"
                            ?disabled=${!hasContext}
                            title=${this.t('execution_panel.tracing_title')}
                            @click=${this._openTracing}
                        >${this.t('execution_panel.tracing_title')}</button>
                        <button
                            class="header-btn"
                            type="button"
                            title=${this.t('execution_panel.mocks_title')}
                            @click=${this._openMocks}
                        >${this.t('execution_panel.mocks_title')}</button>
                        <button
                            class="icon-btn"
                            type="button"
                            title=${this.t('execution_panel.close_panel')}
                            @click=${this._onClose}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                        </button>
                    </div>
                </div>

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

                <div class="body">
                    <div class="body-actions">
                        <label class="file-attach-btn" title=${this.t('execution_panel.attach_files')}>
                            <platform-icon name="paperclip" size="16"></platform-icon>
                            <input
                                type="file"
                                multiple
                                accept=${ACCEPT_FILE_TYPES}
                                @change=${this._handleFileSelect}
                            />
                        </label>
                        ${streaming ? html`
                            <button
                                class="run-btn"
                                data-stop
                                type="button"
                                title=${this.t('execution_panel.stop')}
                                @click=${this._onStop}
                            >
                                <platform-icon name="stop" size="16"></platform-icon>
                            </button>
                        ` : html`
                            <button
                                class="run-btn"
                                type="button"
                                ?disabled=${runDisabled || sendBusy}
                                title=${this.t('execution_panel.run_start')}
                                @click=${this._onRun}
                            >
                                <platform-icon name="play" size="16"></platform-icon>
                            </button>
                        `}
                    </div>
                    <textarea
                        .value=${ui.inputText}
                        placeholder=${this.t(placeholderKey)}
                        @input=${this._onInputChange}
                    ></textarea>
                </div>

                ${lastAssistant && !streaming && (lastAssistant.content || lastAssistant.error)
                    ? html`
                        <div class="answer ${lastAssistant.error ? 'error' : ''}">
                            ${lastAssistant.error
                                ? lastAssistant.error
                                : lastAssistant.content}
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);

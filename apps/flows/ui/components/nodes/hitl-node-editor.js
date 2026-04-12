/**
 * Редактор ноды hitl_node — очередь оператора и тексты handoff.
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-textarea.js';

export class HitlNodeEditor extends BaseNodeEditor {
    static styles = [
        BaseNodeEditor.styles,
        css`
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .queue-picker-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .queue-picker-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }

            .queue-picker-refresh {
                font-size: var(--text-xs);
                color: var(--accent-text);
                background: none;
                border: none;
                cursor: pointer;
                text-decoration: underline;
                padding: 0;
            }

            .queue-picker-refresh:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .queue-picker-list {
                max-height: 220px;
                overflow-y: auto;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                margin-bottom: var(--space-3);
            }

            .queue-picker-row {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 2px;
                width: 100%;
                padding: var(--space-2) var(--space-3);
                text-align: left;
                border: none;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                cursor: pointer;
                color: var(--text-primary);
            }

            .queue-picker-row:last-child {
                border-bottom: none;
            }

            .queue-picker-row:hover {
                background: var(--glass-tint-medium);
            }

            .queue-picker-row.selected {
                background: var(--accent-bg);
                box-shadow: inset 3px 0 0 var(--accent);
            }

            .queue-picker-row-name {
                font-weight: var(--font-medium);
                font-size: var(--text-sm);
            }

            .queue-picker-row-slug {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .queue-picker-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .queue-picker-err {
                font-size: var(--text-xs);
                color: var(--error);
                margin-bottom: var(--space-2);
            }

            .hitl-handoff-card {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                margin-bottom: var(--space-4);
            }

            .hitl-handoff-card-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: var(--space-2);
            }

            .hitl-handoff-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
                grid-template-rows: auto minmax(0, 1fr);
                gap: var(--space-3);
                align-items: start;
                margin-top: var(--space-2);
            }

            .hitl-handoff-mode {
                grid-column: 1;
                grid-row: 1;
            }

            .hitl-handoff-title {
                grid-column: 1;
                grid-row: 2;
                align-self: stretch;
            }

            .hitl-handoff-message {
                grid-column: 2;
                grid-row: 1 / span 2;
                align-self: stretch;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-height: 0;
            }

            @media (max-width: 720px) {
                .hitl-handoff-grid {
                    grid-template-columns: 1fr;
                    grid-template-rows: auto auto auto;
                }

                .hitl-handoff-mode {
                    grid-column: 1;
                    grid-row: 1;
                }

                .hitl-handoff-title {
                    grid-column: 1;
                    grid-row: 2;
                }

                .hitl-handoff-message {
                    grid-column: 1;
                    grid-row: 3;
                }
            }
        `,
    ];

    static properties = {
        ...BaseNodeEditor.properties,
        _operatorQueues: { state: true },
        _queuesLoading: { state: true },
        _queuesErrorKey: { state: true },
        _queuesErrorDetail: { state: true },
        _queueFilter: { state: true },
    };

    constructor() {
        super();
        this._nodeType = 'hitl_node';
        this._operatorQueues = [];
        this._queuesLoading = false;
        this._queuesErrorKey = null;
        this._queuesErrorDetail = '';
        this._queueFilter = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadOperatorQueues();
    }

    _queuesForbiddenMessage(err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (/\b403\b/.test(msg)) {
            return true;
        }
        const lower = msg.toLowerCase();
        return lower.includes('admin') || lower.includes('администратор');
    }

    async _loadOperatorQueues() {
        const svc = this.a2a;
        if (!svc) {
            this._operatorQueues = [];
            return;
        }
        this._queuesLoading = true;
        this._queuesErrorKey = null;
        this._queuesErrorDetail = '';
        this.requestUpdate();
        try {
            const page = await svc.listOperatorQueues();
            this._operatorQueues = page?.items ?? [];
        } catch (err) {
            this._operatorQueues = [];
            if (this._queuesForbiddenMessage(err)) {
                this._queuesErrorKey = 'forbidden';
                this._queuesErrorDetail = '';
            } else {
                this._queuesErrorKey = 'load_failed';
                this._queuesErrorDetail =
                    err instanceof Error ? err.message : String(err);
            }
        } finally {
            this._queuesLoading = false;
            this.requestUpdate();
        }
    }

    _filteredQueues() {
        const needle = (this._queueFilter || '').trim().toLowerCase();
        const list = this._operatorQueues || [];
        if (!needle) {
            return list;
        }
        return list.filter((row) => {
            const slug = String(row.slug || '').toLowerCase();
            const name = String(row.name || '').toLowerCase();
            return slug.includes(needle) || name.includes(needle);
        });
    }

    _pickQueue(slug) {
        const s = String(slug || '').trim();
        this._onInputChange('operator_queue_slug', s);
        this._onInputChange('operator_queue_id', '');
    }

    _onQueueFilterInput(e) {
        this._queueFilter = e.detail?.value ?? e.target.value ?? '';
        this.requestUpdate();
    }

    _renderQueuePicker(config) {
        const filtered = this._filteredQueues();
        const currentSlug = String(config.operator_queue_slug || '').trim();

        return html`
            <div class="form-group">
                <div class="queue-picker-toolbar">
                    <span class="queue-picker-title"
                        >${this.i18n.t('hitl_node_editor.queue_picker_title')}</span
                    >
                    <button
                        type="button"
                        class="queue-picker-refresh"
                        ?disabled=${this._queuesLoading}
                        @click=${() => this._loadOperatorQueues()}
                    >
                        ${this.i18n.t('hitl_node_editor.queue_picker_refresh')}
                    </button>
                </div>
                ${this._queuesLoading
                    ? html`<div class="queue-picker-meta">
                          ${this.i18n.t('hitl_node_editor.queue_picker_loading')}
                      </div>`
                    : ''}
                ${this._queuesErrorKey === 'forbidden'
                    ? html`<div class="queue-picker-err">
                          ${this.i18n.t('hitl_node_editor.queue_picker_forbidden')}
                      </div>`
                    : ''}
                ${this._queuesErrorKey === 'load_failed'
                    ? html`<div class="queue-picker-err">
                          ${this.i18n.t('hitl_node_editor.queue_picker_load_failed', {
                              message: this._queuesErrorDetail || '—',
                          })}
                      </div>`
                    : ''}
                ${!this._queuesLoading &&
                !this._queuesErrorKey &&
                this._operatorQueues.length === 0
                    ? html`<div class="queue-picker-meta">
                          ${this.i18n.t('hitl_node_editor.queue_picker_empty')}
                      </div>`
                    : ''}
                ${!this._queuesLoading && this._operatorQueues.length > 0
                    ? html`
                          <glass-input
                              .value=${this._queueFilter}
                              placeholder=${this.i18n.t(
                                  'hitl_node_editor.queue_picker_search_placeholder',
                              )}
                              @input=${this._onQueueFilterInput}
                          ></glass-input>
                          ${filtered.length === 0
                              ? html`<div class="queue-picker-meta">
                                    ${this.i18n.t('hitl_node_editor.queue_picker_no_match')}
                                </div>`
                              : html`
                                    <div class="queue-picker-list" role="listbox">
                                        ${filtered.map(
                                            (row) => html`
                                                <button
                                                    type="button"
                                                    class="queue-picker-row${currentSlug ===
                                                    String(row.slug || '').trim()
                                                        ? ' selected'
                                                        : ''}"
                                                    role="option"
                                                    @click=${() =>
                                                        this._pickQueue(row.slug)}
                                                >
                                                    <span class="queue-picker-row-name"
                                                        >${row.name || row.slug}</span
                                                    >
                                                    <span class="queue-picker-row-slug"
                                                        >${row.slug}</span
                                                    >
                                                </button>
                                            `,
                                        )}
                                    </div>
                                `}
                      `
                    : ''}
            </div>
        `;
    }

    _renderHandoffCard(config) {
        return html`
            <div class="hitl-handoff-card">
                <div class="hitl-handoff-card-title">
                    ${this.i18n.t('hitl_node_editor.handoff_block_title')}
                </div>
                <div class="hint">${this.i18n.t('hitl_node_editor.handoff_input_mapping_hint')}</div>
                <div class="hitl-handoff-grid">
                    <div class="hitl-handoff-mode">
                        <div class="form-label">${this.i18n.t('hitl_node_editor.handoff_mode_label')}</div>
                        <select
                            class="form-input form-select"
                            .value=${config.operator_handoff_mode || 'single_reply'}
                            @change=${(e) =>
                                this._onInputChange('operator_handoff_mode', e.target.value)}
                        >
                            <option value="single_reply">
                                ${this.i18n.t('hitl_node_editor.handoff_mode_single_reply')}
                            </option>
                            <option value="takeover">
                                ${this.i18n.t('hitl_node_editor.handoff_mode_takeover')}
                            </option>
                        </select>
                    </div>
                    <div class="hitl-handoff-title">
                        <div class="form-label">${this.i18n.t('hitl_node_editor.task_title_label')}</div>
                        <glass-input
                            .value=${config.operator_task_title || ''}
                            @input=${(e) =>
                                this._onInputChange(
                                    'operator_task_title',
                                    e.detail?.value ?? e.target.value,
                                )}
                        ></glass-input>
                        <div class="hint">${this.i18n.t('hitl_node_editor.task_title_mapping_hint')}</div>
                    </div>
                    <div class="hitl-handoff-message">
                        <div class="form-label">${this.i18n.t('hitl_node_editor.user_message_label')}</div>
                        <glass-textarea
                            .value=${config.operator_user_message || ''}
                            rows=${5}
                            @input=${(e) =>
                                this._onInputChange(
                                    'operator_user_message',
                                    e.detail?.value ?? e.target.value,
                                )}
                        ></glass-textarea>
                        <div class="hint">${this.i18n.t('hitl_node_editor.user_message_mapping_hint')}</div>
                    </div>
                </div>
            </div>
        `;
    }

    renderFields() {
        const config = this.nodeConfig || {};
        const compactHeader = !this.expanded;
        return html`
            ${compactHeader
                ? html`
                      ${this.renderNodeIdField()}
                      <div class="form-group">
                          <div class="form-label">${this.i18n.t('node_modal.common.field_name')}</div>
                          <glass-input
                              .value=${config.name || ''}
                              @input=${(e) =>
                                  this._onInputChange('name', e.detail?.value ?? e.target.value)}
                          ></glass-input>
                      </div>
                  `
                : ''}
            ${this._renderQueuePicker(config)}
            <div class="form-group">
                <div class="form-label">${this.i18n.t('hitl_node_editor.queue_slug_label')}</div>
                <glass-input
                    .value=${config.operator_queue_slug || ''}
                    placeholder="support_l1"
                    @input=${(e) =>
                        this._onInputChange(
                            'operator_queue_slug',
                            e.detail?.value ?? e.target.value,
                        )}
                ></glass-input>
                <div class="hint">${this.i18n.t('hitl_node_editor.queue_slug_hint')}</div>
                <div class="hint">${this.i18n.t('hitl_node_editor.queue_slug_manual_hint')}</div>
                <div class="hint">${this.i18n.t('hitl_node_editor.queue_slug_mapping_hint')}</div>
            </div>
            ${this._renderHandoffCard(config)}
            ${this.renderMappingSection()}
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('hitl-node-editor', HitlNodeEditor);

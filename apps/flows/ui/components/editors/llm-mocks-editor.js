/**
 * LLMMocksEditor — мок-ответы для нод flow (metadata.mock).
 * Контролируемый компонент: источник правды — props.mocks, изменения через @change.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const LLM_NODE = 'llm_node';
const TOOL_NONE = '';

/**
 * Стабильный уникальный id строки. randomUUID есть только в secure context (HTTPS / localhost).
 */
function createRowId() {
    const c = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
    if (c && typeof c.randomUUID === 'function') {
        return c.randomUUID();
    }
    const bytes = new Uint8Array(16);
    if (c && typeof c.getRandomValues === 'function') {
        c.getRandomValues(bytes);
    } else {
        for (let i = 0; i < 16; i++) {
            bytes[i] = Math.floor(Math.random() * 256);
        }
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class LLMMocksEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .mocks-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .mock-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                min-width: 0;
            }

            .mock-toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                gap: var(--space-2);
                min-width: 0;
            }

            .mock-toolbar-main {
                display: flex;
                flex-wrap: wrap;
                flex: 1;
                gap: var(--space-2);
                min-width: 0;
            }

            .mock-number {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                flex-shrink: 0;
                line-height: 32px;
            }

            .node-select,
            .tool-select,
            .mock-type-select {
                padding: 6px 8px;
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                min-width: 0;
                max-width: 100%;
            }

            .node-select {
                flex: 1 1 140px;
            }

            .tool-select {
                flex: 1 1 120px;
            }

            .mock-type-select {
                flex: 0 1 110px;
            }

            .remove-icon-btn {
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
            }

            .remove-icon-btn:hover {
                color: var(--error);
                border-color: var(--error);
                background: rgba(239, 68, 68, 0.08);
            }

            .mock-textarea {
                width: 100%;
                box-sizing: border-box;
                min-height: 80px;
                padding: var(--space-2);
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                resize: vertical;
                outline: none;
                min-width: 0;
            }

            .mock-textarea:focus {
                border-color: var(--accent);
            }

            .mock-textarea::placeholder {
                color: var(--text-tertiary);
            }

            .tool-fields {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }

            .tool-input {
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                width: 100%;
                box-sizing: border-box;
            }

            .tool-input:focus {
                border-color: var(--accent);
            }

            .add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--accent);
                background: transparent;
                border: 1px dashed var(--accent);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .add-btn:hover {
                background: var(--accent-bg);
            }

            .empty-state {
                padding: var(--space-6) var(--space-4);
                text-align: center;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
            }

            .mock-label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
            }
        `,
    ];

    static properties = {
        mocks: { type: Array },
        flowNodes: { type: Object },
    };

    constructor() {
        super();
        this.mocks = [];
        this.flowNodes = {};
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('mocks')) {
            this._ensureRowIds();
        }
    }

    /**
     * Старые сохранённые моки без row_id — добавляем id, чтобы удаление и ключи работали стабильно.
     */
    _ensureRowIds() {
        const rows = this._rows();
        if (rows.length === 0 || !rows.some((r) => !r.row_id)) {
            return;
        }
        const next = rows.map((r) => ({
            ...r,
            row_id: r.row_id || createRowId(),
        }));
        this._emitRows(next);
    }

    _rows() {
        return Array.isArray(this.mocks) ? this.mocks : [];
    }

    _emitRows(next) {
        this.emit('change', { value: next });
    }

    _nodeIds() {
        const g = this.flowNodes && typeof this.flowNodes === 'object' ? this.flowNodes : {};
        return Object.keys(g).sort();
    }

    _nodeType(nodeId) {
        const n = this.flowNodes?.[nodeId];
        return n && typeof n.type === 'string' ? n.type : '';
    }

    _toolOptions(nodeId) {
        const n = this.flowNodes?.[nodeId];
        const list = n && Array.isArray(n.tools) ? n.tools : [];
        return list
            .map((t) => (t && typeof t.tool_id === 'string' ? t.tool_id : ''))
            .filter(Boolean);
    }

    _patchRow(rowId, patch) {
        const next = this._rows().map((r) =>
            r.row_id === rowId ? { ...r, ...patch } : r
        );
        this._emitRows(next);
    }

    _addMock() {
        const row = {
            row_id: createRowId(),
            node_id: '',
            tool_id: TOOL_NONE,
            type: 'text',
            content: '',
            tool: '',
            args: '{}',
            response: '{}',
        };
        this._emitRows([...this._rows(), row]);
    }

    _removeMock(rowId) {
        this._emitRows(this._rows().filter((r) => r.row_id !== rowId));
    }

    _onNodeChange(rowId, nodeId) {
        const nextNode = nodeId || '';
        const t = this._nodeType(nextNode);
        const patch = { node_id: nextNode };
        if (t !== LLM_NODE) {
            patch.tool_id = TOOL_NONE;
        }
        this._patchRow(rowId, patch);
    }

    _onToolChange(rowId, toolId) {
        this._patchRow(rowId, { tool_id: toolId || TOOL_NONE });
    }

    _onTypeChange(rowId, type) {
        const row = this._rows().find((r) => r.row_id === rowId);
        if (!row) {
            return;
        }
        if (type === 'text') {
            this._patchRow(rowId, { type, content: row.content ?? '' });
        } else if (type === 'tool_call') {
            this._patchRow(rowId, {
                type,
                tool: row.tool ?? '',
                args: row.args ?? '{}',
            });
        } else {
            this._patchRow(rowId, { type, response: row.response ?? '{}' });
        }
    }

    render() {
        const rows = this._rows();
        const nodeIds = this._nodeIds();

        if (rows.length === 0) {
            return html`
                <div class="mocks-container">
                    <div class="empty-state">
                        ${this.i18n.t('llm_mocks_editor.empty_state')}
                    </div>
                    <button type="button" class="add-btn" @click=${this._addMock}>
                        ${this.i18n.t('llm_mocks_editor.add_mock')}
                    </button>
                    <div class="hint">
                        ${this.i18n.t('llm_mocks_editor.hint')}
                    </div>
                </div>
            `;
        }

        return html`
            <div class="mocks-container">
                ${rows.map((mock, index) => {
                    const nid = mock.node_id || '';
                    const nType = this._nodeType(nid);
                    const showTools = nType === LLM_NODE && this._toolOptions(nid).length > 0;
                    return html`
                        <div class="mock-item">
                            <div class="mock-toolbar">
                                <span class="mock-number">${this.i18n.t('llm_mocks_editor.answer_n', { n: index + 1 })}</span>
                                <div class="mock-toolbar-main">
                                    <select
                                        class="node-select"
                                        .value=${nid}
                                        @change=${(e) => this._onNodeChange(mock.row_id, e.target.value)}
                                    >
                                        ${nodeIds.length === 0
                                            ? html`<option value="" disabled>${this.i18n.t('llm_mocks_editor.no_nodes')}</option>`
                                            : html`
                                                  <option value="" disabled>${this.i18n.t('llm_mocks_editor.select_node')}</option>
                                                  ${nodeIds.map(
                                                      (id) => html`<option value=${id}>${id}</option>`
                                                  )}
                                              `}
                                    </select>
                                    ${showTools
                                        ? html`
                                              <select
                                                  class="tool-select"
                                                  .value=${mock.tool_id || TOOL_NONE}
                                                  @change=${(e) =>
                                                      this._onToolChange(mock.row_id, e.target.value)}
                                              >
                                                  <option value=${TOOL_NONE}>${this.i18n.t('llm_mocks_editor.llm_only_queue')}</option>
                                                  ${this._toolOptions(nid).map(
                                                      (tid) => html`<option value=${tid}>${tid}</option>`
                                                  )}
                                              </select>
                                          `
                                        : ''}
                                    <select
                                        class="mock-type-select"
                                        .value=${mock.type}
                                        @change=${(e) => this._onTypeChange(mock.row_id, e.target.value)}
                                    >
                                        <option value="text">${this.i18n.t('llm_mocks_editor.type_text')}</option>
                                        <option value="tool_call">${this.i18n.t('llm_mocks_editor.type_tool_call')}</option>
                                        <option value="json">${this.i18n.t('llm_mocks_editor.type_json')}</option>
                                    </select>
                                </div>
                                <button
                                    type="button"
                                    class="remove-icon-btn"
                                    title=${this.i18n.t('llm_mocks_editor.remove_row')}
                                    @click=${() => this._removeMock(mock.row_id)}
                                >
                                    <platform-icon name="trash" size="18"></platform-icon>
                                </button>
                            </div>
                            ${mock.type === 'text'
                                ? html`
                                      <div>
                                          <div class="mock-label">${this.i18n.t('llm_mocks_editor.text_reply_label')}</div>
                                          <textarea
                                              class="mock-textarea"
                                              placeholder=${this.i18n.t('llm_mocks_editor.placeholder_text')}
                                              .value=${mock.content || ''}
                                              @input=${(e) =>
                                                  this._patchRow(mock.row_id, {
                                                      content: e.target.value,
                                                  })}
                                          ></textarea>
                                      </div>
                                  `
                                : mock.type === 'tool_call'
                                  ? html`
                                        <div class="tool-fields">
                                            <div>
                                                <div class="mock-label">${this.i18n.t('llm_mocks_editor.tool_name_label')}</div>
                                                <input
                                                    class="tool-input"
                                                    type="text"
                                                    placeholder=${this.i18n.t('llm_mocks_editor.placeholder_tool_id')}
                                                    .value=${mock.tool || ''}
                                                    @input=${(e) =>
                                                        this._patchRow(mock.row_id, {
                                                            tool: e.target.value,
                                                        })}
                                                />
                                            </div>
                                            <div>
                                                <div class="mock-label">${this.i18n.t('llm_mocks_editor.args_json_label')}</div>
                                                <textarea
                                                    class="mock-textarea"
                                                    placeholder='{"x": 1, "y": 2}'
                                                    .value=${mock.args || '{}'}
                                                    @input=${(e) =>
                                                        this._patchRow(mock.row_id, {
                                                            args: e.target.value,
                                                        })}
                                                ></textarea>
                                            </div>
                                        </div>
                                    `
                                  : html`
                                        <div>
                                            <div class="mock-label">${this.i18n.t('llm_mocks_editor.json_reply_label')}</div>
                                            <textarea
                                                class="mock-textarea"
                                                placeholder='{"result": "mock_value", "status": "success"}'
                                                .value=${mock.response || '{}'}
                                                @input=${(e) =>
                                                    this._patchRow(mock.row_id, {
                                                        response: e.target.value,
                                                    })}
                                            ></textarea>
                                        </div>
                                    `}
                        </div>
                    `;
                })}
                <button type="button" class="add-btn" @click=${this._addMock}>${this.i18n.t('llm_mocks_editor.add_another')}</button>
            </div>
        `;
    }
}

customElements.define('llm-mocks-editor', LLMMocksEditor);

/**
 * flows-state-mapping-editor — маппинг для нод.
 *
 * Бэкенд (apps/flows/src/mapping.py):
 * - input / input_mapping: { target_param: "@state:path" | "@var:path" | "constant" }
 * - output / output_mapping и state_mapping (MCP, external_api): { result_key: state_field }
 *
 * kind: "input" — три поля: источник (путь), тип (@state / @var / const), параметр ноды.
 * kind: "output" — два поля + стрелка: ключ результата, поле в state.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';

function _parseInputSource(raw) {
    const s = String(raw);
    if (s.startsWith('@state:')) {
        return { sourceType: 'state', sourcePath: s.slice(7) };
    }
    if (s.startsWith('@var:')) {
        return { sourceType: 'var', sourcePath: s.slice(5) };
    }
    return { sourceType: 'const', sourcePath: s };
}

function _buildInputSource(sourceType, sourcePath) {
    const p = typeof sourcePath === 'string' ? sourcePath : '';
    if (sourceType === 'state') {
        return `@state:${p}`;
    }
    if (sourceType === 'var') {
        return `@var:${p}`;
    }
    return p;
}

export class FlowsStateMappingEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        /** Сброс локальных строк при смене ноды или вкладки Input/Output (не при каждом emit). */
        syncKey: { type: String },
        mapping: { type: Object },
        /** "input" — input_mapping; "output" — output_mapping / state_mapping. */
        kind: { type: String },
        title: { type: String },
        stateSuggestions: { type: Array },
        varSuggestions: { type: Array },
        resultSuggestions: { type: Array },
        _rows: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .add-btn {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--accent-subtle);
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
            }
            .add-btn:hover {
                filter: brightness(1.05);
            }
            .map-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .map-row {
                display: grid;
                align-items: center;
                gap: var(--space-2);
                padding: 0;
                box-sizing: border-box;
            }
            .map-row.input-grid {
                grid-template-columns: 1fr minmax(0, 10px) minmax(100px, 130px) minmax(0, 28px) 1fr minmax(0, 36px);
            }
            .map-row.output-grid {
                grid-template-columns: 1fr minmax(0, 28px) 1fr minmax(0, 36px);
            }
            .sep {
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                user-select: none;
            }
            .arrow {
                text-align: center;
                color: var(--text-secondary);
                font-size: var(--text-lg);
                user-select: none;
            }
            .map-row platform-field {
                min-width: 0;
                --field-pill-padding-y: var(--space-1);
                --field-pill-padding-x: var(--space-2);
            }
            .remove-btn {
                width: 32px;
                height: 32px;
                padding: 0;
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                font-size: var(--text-xl);
                line-height: 1;
                cursor: pointer;
            }
            .remove-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            .head-row {
                display: grid;
                gap: var(--space-2);
                padding: 0 var(--space-3) var(--space-1);
            }
            .head-row.input-grid {
                grid-template-columns: 1fr minmax(0, 10px) minmax(100px, 130px) minmax(0, 28px) 1fr minmax(0, 36px);
            }
            .head-row.output-grid {
                grid-template-columns: 1fr minmax(0, 28px) 1fr minmax(0, 36px);
            }
            .head-row label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                padding: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this.syncKey = '';
        this.mapping = null;
        this.kind = 'input';
        this.title = '';
        this.stateSuggestions = [];
        this.varSuggestions = [];
        this.resultSuggestions = [];
        this._rows = [];
        /** Не тянуть `mapping` с родителя после первого init (иначе пропадут незаполненные новые строки). */
        this._parentMappingSettled = false;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('syncKey') || changed.has('kind')) {
            this._parentMappingSettled = true;
            this._syncRowsFromMapping();
            return;
        }
        if (changed.has('mapping') && this._parentMappingSettled === false) {
            this._parentMappingSettled = true;
            this._syncRowsFromMapping();
        }
    }

    firstUpdated() {
        if (this._parentMappingSettled === false) {
            this._parentMappingSettled = true;
            this._syncRowsFromMapping();
        }
    }

    get _isOutput() {
        return this.kind === 'output';
    }

    _syncRowsFromMapping() {
        const m = this.mapping;
        this._rows = [];
        if (!m || typeof m !== 'object') {
            return;
        }
        if (this._isOutput) {
            for (const [k, v] of Object.entries(m)) {
                this._rows.push({
                    resultKey: k,
                    stateField: String(v),
                });
            }
        } else {
            for (const [param, source] of Object.entries(m)) {
                const parsed = _parseInputSource(source);
                this._rows.push({
                    param,
                    sourceType: parsed.sourceType,
                    sourcePath: parsed.sourcePath,
                });
            }
        }
    }

    _emitChange() {
        if (this._isOutput) {
            const mapping = {};
            for (const r of this._rows) {
                const a = typeof r.resultKey === 'string' ? r.resultKey.trim() : '';
                const b = typeof r.stateField === 'string' ? r.stateField.trim() : '';
                if (a.length === 0 || b.length === 0) {
                    continue;
                }
                mapping[a] = b;
            }
            this.emit('change', { mapping });
            return;
        }
        const mapping = {};
        for (const r of this._rows) {
            const param = typeof r.param === 'string' ? r.param.trim() : '';
            if (param.length === 0) {
                continue;
            }
            mapping[param] = _buildInputSource(r.sourceType, r.sourcePath);
        }
        this.emit('change', { mapping });
    }

    _addRow() {
        if (this._isOutput) {
            this._rows = [...this._rows, { resultKey: '', stateField: '' }];
        } else {
            this._rows = [
                ...this._rows,
                { param: '', sourceType: 'state', sourcePath: '' },
            ];
        }
    }

    _removeRow(idx) {
        this._rows = this._rows.filter((_, i) => i !== idx);
        this._emitChange();
    }

    _updateInputRow(idx, patch) {
        this._rows = this._rows.map((r, i) => (i === idx ? { ...r, ...patch } : r));
        this._emitChange();
    }

    _updateOutputRow(idx, patch) {
        this._rows = this._rows.map((r, i) => (i === idx ? { ...r, ...patch } : r));
        this._emitChange();
    }

    _inputSourceTypeEnumConfig() {
        return {
            values: [
                { value: 'state', label: '@state' },
                { value: 'var', label: '@var' },
                { value: 'const', label: this.t('state_mapping_editor.type_const') },
            ],
        };
    }

    _suggestionsForInputSource(sourceType) {
        if (sourceType === 'var') {
            return Array.isArray(this.varSuggestions) ? this.varSuggestions : [];
        }
        if (sourceType === 'state') {
            return Array.isArray(this.stateSuggestions) ? this.stateSuggestions : [];
        }
        return [];
    }

    _normalizedSuggestions(suggestions) {
        return Array.isArray(suggestions)
            ? suggestions.filter((item) => typeof item === 'string' && item.length > 0).slice(0, 120)
            : [];
    }

    _renderInputText(value, suggestions, onInput, placeholder = '') {
        const values = this._normalizedSuggestions(suggestions);
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=""
                .value=${typeof value === 'string' ? value : ''}
                .placeholder=${placeholder}
                .suggestions=${values}
                @change=${(e) => onInput(typeof e.detail.value === 'string' ? e.detail.value : '')}
            ></platform-field>
        `;
    }

    render() {
        const isOut = this._isOutput;
        const empty = this._rows.length === 0;
        return html`
            ${this.title
                ? html`<div class="title" style="margin-bottom: var(--space-2); font-weight: var(--font-medium)">${this.title}</div>`
                : ''}
            <div class="toolbar">
                <span class="hint">${isOut
                    ? this.t('state_mapping_editor.hint_legend_output')
                    : this.t('state_mapping_editor.hint_legend_input')}</span>
                <button type="button" class="add-btn" @click=${this._addRow}>
                    + ${this.t('state_mapping_editor.add')}
                </button>
            </div>
            ${empty
                ? html`<div class="empty">${this.t('state_mapping_editor.empty')}</div>`
                : ''}
            ${!empty && !isOut
                ? html`
                    <div class="head-row input-grid" aria-hidden="true">
                        <label>${this.t('state_mapping_editor.col_source')}</label>
                        <span></span>
                        <label>${this.t('state_mapping_editor.col_type')}</label>
                        <span></span>
                        <label>${this.t('state_mapping_editor.col_parameter')}</label>
                        <span></span>
                    </div>
                `
                : ''}
            ${!empty && isOut
                ? html`
                    <div class="head-row output-grid" aria-hidden="true">
                        <label>${this.t('state_mapping_editor.col_result_key')}</label>
                        <span></span>
                        <label>${this.t('state_mapping_editor.col_state_field')}</label>
                        <span></span>
                    </div>
                `
                : ''}
            <div class="map-wrap">
                ${isOut
                    ? this._rows.map((r, i) => html`
                        <div class="map-row output-grid">
                            ${this._renderInputText(
                                r.resultKey,
                                this.resultSuggestions,
                                (value) => this._updateOutputRow(i, { resultKey: value }),
                                this.t('state_mapping_editor.placeholder_result_key'),
                            )}
                            <span class="arrow" title="">→</span>
                            ${this._renderInputText(
                                r.stateField,
                                this.stateSuggestions,
                                (value) => this._updateOutputRow(i, { stateField: value }),
                                this.t('state_mapping_editor.placeholder_state_field'),
                            )}
                            <button
                                type="button"
                                class="remove-btn"
                                @click=${() => this._removeRow(i)}
                            >×</button>
                        </div>
                    `)
                    : this._rows.map((r, i) => html`
                        <div class="map-row input-grid">
                            ${this._renderInputText(
                                r.sourcePath,
                                this._suggestionsForInputSource(r.sourceType),
                                (value) => this._updateInputRow(i, { sourcePath: value }),
                                this.t('state_mapping_editor.placeholder_source_path'),
                            )}
                            <span class="sep" aria-hidden="true">|</span>
                            <platform-field
                                type="enum"
                                mode="edit"
                                label=""
                                .value=${r.sourceType}
                                .config=${this._inputSourceTypeEnumConfig()}
                                @change=${(e) => this._updateInputRow(i, { sourceType: typeof e.detail.value === 'string' ? e.detail.value : 'state' })}
                            ></platform-field>
                            <span class="arrow" aria-hidden="true">→</span>
                            <platform-field
                                type="string"
                                mode="edit"
                                label=""
                                .value=${r.param}
                                @change=${(e) => this._updateInputRow(i, { param: typeof e.detail.value === 'string' ? e.detail.value : '' })}
                            ></platform-field>
                            <button
                                type="button"
                                class="remove-btn"
                                @click=${() => this._removeRow(i)}
                            >×</button>
                        </div>
                    `)}
            </div>
        `;
    }
}

customElements.define('flows-state-mapping-editor', FlowsStateMappingEditor);

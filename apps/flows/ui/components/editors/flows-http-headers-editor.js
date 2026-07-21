/**
 * flows-http-headers-editor — единый key/value редактор HTTP-заголовков.
 *
 * Контракт: Record<string, string>. Значения поддерживают @var: / @state:
 * (autocomplete @var: через platform-variable-input).
 *
 * Events: change { value: Record<string, string> }
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-variable-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

/**
 * @param {unknown} headers
 * @returns {Record<string, string>}
 */
function _normalizeHeadersObject(headers) {
    if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
        return {};
    }
    /** @type {Record<string, string>} */
    const out = {};
    for (const key of Object.keys(headers)) {
        const v = headers[key];
        out[key] = typeof v === 'string' ? v : '';
    }
    return out;
}

/**
 * @param {{ name: string, value: string }[]} rows
 * @returns {Record<string, string>}
 */
function _headersObjectFromRows(rows) {
    /** @type {Record<string, string>} */
    const out = {};
    if (!Array.isArray(rows)) {
        return out;
    }
    for (const row of rows) {
        if (!row || typeof row !== 'object') {
            continue;
        }
        const name = typeof row.name === 'string' ? row.name.trim() : '';
        if (!name) {
            continue;
        }
        out[name] = typeof row.value === 'string' ? row.value : '';
    }
    return out;
}

/**
 * @param {Record<string, string>} a
 * @param {Record<string, string>} b
 * @returns {boolean}
 */
function _headerDictEqual(a, b) {
    const ka = Object.keys(a).sort();
    const kb = Object.keys(b).sort();
    if (ka.length !== kb.length) {
        return false;
    }
    for (let i = 0; i < ka.length; i += 1) {
        if (ka[i] !== kb[i]) {
            return false;
        }
        if (a[ka[i]] !== b[kb[i]]) {
            return false;
        }
    }
    return true;
}

/**
 * @param {Record<string, string>} headers
 * @returns {{ name: string, value: string }[]}
 */
function _pairsFromHeaders(headers) {
    return Object.keys(headers).map((name) => ({
        name,
        value: headers[name],
    }));
}

export class FlowsHttpHeadersEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        value: { type: Object },
        readOnly: { type: Boolean, attribute: 'read-only', reflect: true },
        /** @type {{ name: string, value: string }[]} */
        _rows: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                width: 100%;
                box-sizing: border-box;
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: 0 0 var(--space-2);
                line-height: 1.35;
            }
            .header-pair-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
                gap: var(--space-2);
                align-items: center;
                padding: var(--space-1) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .header-pair-row > platform-variable-input,
            .header-pair-row > platform-field {
                min-width: 0;
                width: 100%;
            }
            .header-pair-row > platform-button {
                align-self: center;
            }
            .header-pairs-add {
                margin-top: var(--space-2);
            }
            .empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-2) 0;
            }
        `,
    ];

    constructor() {
        super();
        this.value = {};
        this.readOnly = false;
        this._rows = [];
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('value')) {
            const cfgNorm = _normalizeHeadersObject(this.value);
            const rowsNorm = _headersObjectFromRows(this._rows);
            if (!_headerDictEqual(cfgNorm, rowsNorm)) {
                this._rows = _pairsFromHeaders(cfgNorm);
            }
        }
    }

    _emitFromRows() {
        this.emit('change', { value: _headersObjectFromRows(this._rows) });
    }

    /**
     * @param {number} idx
     * @param {CustomEvent} e
     */
    _onName(idx, e) {
        e.stopPropagation();
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-http-headers-editor: name change detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-http-headers-editor: name must be string');
        }
        this._rows = this._rows.map((row, i) => (i === idx ? { ...row, name: v } : row));
        this._emitFromRows();
    }

    /**
     * @param {number} idx
     * @param {CustomEvent} e
     */
    _onValue(idx, e) {
        e.stopPropagation();
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-http-headers-editor: value change detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-http-headers-editor: value must be string');
        }
        this._rows = this._rows.map((row, i) => (i === idx ? { ...row, value: v } : row));
        this._emitFromRows();
    }

    _addRow() {
        this._rows = [...this._rows, { name: '', value: '' }];
    }

    /**
     * @param {number} idx
     */
    _removeRow(idx) {
        this._rows = this._rows.filter((_, i) => i !== idx);
        this._emitFromRows();
    }

    render() {
        const rows = Array.isArray(this._rows) ? this._rows : [];
        return html`
            <p class="hint">${this.t('http_headers_editor.hint')}</p>
            ${rows.length === 0 && this.readOnly
                ? html`<div class="empty">${this.t('http_headers_editor.empty')}</div>`
                : nothing}
            ${rows.map(
                (row, idx) => html`
                    <div class="header-pair-row">
                        ${this.readOnly
                            ? html`
                                <platform-field
                                    mode="view"
                                    type="string"
                                    .label=${this.t('http_headers_editor.name')}
                                    .value=${typeof row.name === 'string' ? row.name : ''}
                                ></platform-field>
                                <platform-field
                                    mode="view"
                                    type="string"
                                    .label=${this.t('http_headers_editor.value')}
                                    .value=${typeof row.value === 'string' ? row.value : ''}
                                ></platform-field>
                            `
                            : html`
                                <platform-variable-input
                                    .label=${this.t('http_headers_editor.name')}
                                    .placeholder=${this.t('http_headers_editor.name_placeholder')}
                                    .value=${typeof row.name === 'string' ? row.name : ''}
                                    @change=${(e) => this._onName(idx, e)}
                                ></platform-variable-input>
                                <platform-variable-input
                                    .label=${this.t('http_headers_editor.value')}
                                    .placeholder=${this.t('http_headers_editor.value_placeholder')}
                                    .value=${typeof row.value === 'string' ? row.value : ''}
                                    @change=${(e) => this._onValue(idx, e)}
                                ></platform-variable-input>
                            `}
                        ${this.readOnly
                            ? nothing
                            : html`
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    danger
                                    title=${this.t('http_headers_editor.remove')}
                                    aria-label=${this.t('http_headers_editor.remove')}
                                    @click=${() => this._removeRow(idx)}
                                >
                                    <platform-icon name="trash" .size=${16}></platform-icon>
                                </platform-button>
                            `}
                    </div>
                `,
            )}
            ${this.readOnly
                ? nothing
                : html`
                    <platform-button
                        class="header-pairs-add"
                        variant="ghost"
                        density="compact"
                        @click=${() => this._addRow()}
                    >
                        <platform-icon name="plus"></platform-icon>
                        ${this.t('http_headers_editor.add')}
                    </platform-button>
                `}
        `;
    }
}

customElements.define('flows-http-headers-editor', FlowsHttpHeadersEditor);

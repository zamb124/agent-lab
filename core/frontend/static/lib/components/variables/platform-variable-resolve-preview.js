/**
 * Resolve preview — effective variable values for executor context.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../platform-button.js';
import '../glass-spinner.js';

function _stringifyResolvedItem(item) {
    if (!item.resolvable || !item.payload || !item.payload.base) {
        return '';
    }
    const base = item.payload.base;
    if (base.value_kind === 'expression') {
        return base.expression ?? '';
    }
    const value = base.value;
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value === 'string') {
        return value;
    }
    return JSON.stringify(value);
}

export class PlatformVariableResolvePreview extends PlatformElement {
    static i18nNamespace = 'company_variables';

    static properties = {
        variableKey: { type: String, attribute: 'variable-key' },
        _userId: { state: true },
        _namespace: { state: true },
        _channel: { state: true },
        _items: { state: true },
        _loading: { state: true },
    };

    static styles = css`
        :host { display: block; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: var(--space-2);
            margin-bottom: var(--space-3);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: var(--space-2);
            border-bottom: 1px solid var(--glass-border-subtle);
            text-align: left;
            font-size: var(--text-sm);
        }
        th {
            color: var(--text-tertiary);
            text-transform: uppercase;
            font-size: var(--text-xs);
        }
        .empty {
            color: var(--text-tertiary);
            font-size: var(--text-sm);
            padding: var(--space-3);
        }
    `;

    constructor() {
        super();
        this.variableKey = '';
        this._userId = '';
        this._namespace = '';
        this._channel = '';
        this._items = [];
        this._loading = false;
        this._resolve = this.useOp('secrets/variables_resolve');
    }

    async _runPreview() {
        this._loading = true;
        try {
            const response = await this._resolve.run({
                user_id: this._userId.trim() === '' ? null : this._userId.trim(),
                namespace: this._namespace.trim() === '' ? null : this._namespace.trim(),
                channel: this._channel.trim() === '' ? null : this._channel.trim(),
            });
            const items = response && Array.isArray(response.items) ? response.items : [];
            if (this.variableKey) {
                this._items = items.filter((item) => item.variable_key === this.variableKey);
            } else {
                this._items = items;
            }
        } finally {
            this._loading = false;
        }
    }

    render() {
        return html`
            <div class="grid">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_user_id')}
                    .value=${this._userId}
                    @change=${(e) => { this._userId = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_namespace')}
                    .value=${this._namespace}
                    @change=${(e) => { this._namespace = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_channel')}
                    .value=${this._channel}
                    @change=${(e) => { this._channel = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
            </div>
            <platform-button @click=${() => this._runPreview()}>${this.t('editor.preview_run')}</platform-button>
            ${this._loading ? html`<glass-spinner></glass-spinner>` : ''}
            ${!this._loading && this._items.length === 0
                ? html`<div class="empty">${this.t('editor.preview_empty')}</div>`
                : html`
                    <table>
                        <thead>
                            <tr>
                                <th>${this.t('editor.preview_col_key')}</th>
                                <th>${this.t('editor.preview_col_value')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${this._items.map((item) => html`
                                <tr>
                                    <td><code>${item.variable_key}</code></td>
                                    <td>${!item.resolvable || item.secret ? this.t('value_masked') : _stringifyResolvedItem(item)}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                `}
        `;
    }
}

customElements.define('platform-variable-resolve-preview', PlatformVariableResolvePreview);

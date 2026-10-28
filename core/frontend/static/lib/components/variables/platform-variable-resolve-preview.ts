/**
 * Resolve preview — effective variable values for executor context.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../platform-button.js';
import '../glass-spinner.js';
import { isPlainRecord } from '../../events/payload.js';
import type { OpController } from '../../base/use-resource.js';

interface ResolvedVariableBase {
    value_kind?: string;
    value?: unknown;
    expression?: string;
}

interface ResolvedVariableItem {
    variable_key?: string;
    resolvable?: boolean;
    secret?: boolean;
    payload?: { base?: ResolvedVariableBase } | null;
}

function isResolvedVariableItem(value: unknown): value is ResolvedVariableItem {
    if (!isPlainRecord(value)) return false;
    if (value.variable_key !== undefined && typeof value.variable_key !== 'string') return false;
    if (value.resolvable !== undefined && typeof value.resolvable !== 'boolean') return false;
    if (value.secret !== undefined && typeof value.secret !== 'boolean') return false;
    if (value.payload === undefined || value.payload === null) return true;
    if (!isPlainRecord(value.payload)) return false;
    return value.payload.base === undefined || isPlainRecord(value.payload.base);
}

function resolvedItems(response: unknown): ResolvedVariableItem[] {
    if (!isPlainRecord(response) || !Array.isArray(response.items)) {
        throw new Error('platform-variable-resolve-preview: items array required');
    }
    const items: ResolvedVariableItem[] = [];
    for (const item of response.items) {
        if (!isResolvedVariableItem(item)) {
            throw new Error('platform-variable-resolve-preview: item must be an object');
        }
        items.push(item);
    }
    return items;
}

function _stringifyResolvedItem(item: ResolvedVariableItem): string {
    if (!item.resolvable || !item.payload || !item.payload.base) {
        return '';
    }
    const base = item.payload.base;
    if (base.value_kind === 'expression') {
        return base.expression === undefined || base.expression === null ? '' : base.expression;
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

    static override properties: PropertyDeclarations = {
        variableKey: { type: String, attribute: 'variable-key' },
        _userId: { state: true },
        _namespace: { state: true },
        _channel: { state: true },
        _items: { state: true },
        _loading: { state: true },
    };

    declare variableKey: string;
    declare _userId: string;
    declare _namespace: string;
    declare _channel: string;
    declare _items: ResolvedVariableItem[];
    declare _loading: boolean;

    private _resolve: OpController;

    static override styles: CSSResultGroup = css`
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

    async _runPreview(): Promise<void> {
        this._loading = true;
        try {
            const response = await this._resolve.run({
                user_id: this._userId.trim() === '' ? null : this._userId.trim(),
                namespace: this._namespace.trim() === '' ? null : this._namespace.trim(),
                channel: this._channel.trim() === '' ? null : this._channel.trim(),
            });
            const items = response === null ? [] : resolvedItems(response);
            if (this.variableKey) {
                this._items = items.filter((item: ResolvedVariableItem) => item.variable_key === this.variableKey);
            } else {
                this._items = items;
            }
        } finally {
            this._loading = false;
        }
    }

    override render(): TemplateResult {
        return html`
            <div class="grid">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_user_id')}
                    .value=${this._userId}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._userId = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_namespace')}
                    .value=${this._namespace}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._namespace = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('editor.preview_channel')}
                    .value=${this._channel}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._channel = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
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
                            ${this._items.map((item: ResolvedVariableItem) => html`
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

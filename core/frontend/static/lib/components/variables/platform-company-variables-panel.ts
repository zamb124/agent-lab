/**
 * Company variables list panel — shared between Console and Flows embed.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../../lit-shim.js';
import { isPlainRecord } from '../../events/payload.js';
import { PlatformElement } from '../../platform-element/index.js';
import type { OpController, ResourceController } from '../../base/use-resource.js';
import { platformConfirm } from '../platform-confirm-modal.js';
import '../platform-button.js';
import '../platform-icon.js';
import '../glass-spinner.js';
import './platform-company-variable-editor-modal.js';
import './platform-system-variables-catalog.js';

interface CompanyVariableItem {
    variable_key: string;
    title?: string;
    version?: number | string;
    public?: boolean;
    secret?: boolean;
    shared_for_execution?: boolean;
    payload?: {
        base?: { value_kind?: string; value?: unknown };
        scopes?: unknown[];
    };
}

interface VariableHistoryItem {
    version?: number | string;
    updated_at?: string;
    created_at?: string;
}

function isVariableHistoryItem(value: unknown): value is VariableHistoryItem {
    if (!isPlainRecord(value)) return false;
    if (value.version !== undefined && typeof value.version !== 'number' && typeof value.version !== 'string') {
        return false;
    }
    if (value.updated_at !== undefined && typeof value.updated_at !== 'string') return false;
    if (value.created_at !== undefined && typeof value.created_at !== 'string') return false;
    return true;
}

function historyItems(page: unknown): VariableHistoryItem[] {
    if (!isPlainRecord(page) || !Array.isArray(page.items)) {
        throw new Error('platform-company-variables-panel: versions page items required');
    }
    const items: VariableHistoryItem[] = [];
    for (const item of page.items) {
        if (!isVariableHistoryItem(item)) {
            throw new Error('platform-company-variables-panel: version row must be an object');
        }
        items.push(item);
    }
    return items;
}

type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

function companyVariableItems(items: readonly unknown[]): CompanyVariableItem[] {
    return items.map((value) => {
        if (value === null || typeof value !== 'object' || Array.isArray(value)) {
            throw new Error('company variable: row must be an object');
        }
        if (!('variable_key' in value) || typeof value.variable_key !== 'string' || value.variable_key.length === 0) {
            throw new Error('company variable: variable_key required');
        }
        const item: CompanyVariableItem = { variable_key: value.variable_key };
        if ('title' in value && value.title !== undefined) {
            if (typeof value.title !== 'string') throw new Error('company variable: title must be a string');
            item.title = value.title;
        }
        if ('version' in value && value.version !== undefined) {
            if (typeof value.version !== 'number' && typeof value.version !== 'string') {
                throw new Error('company variable: version must be a number or string');
            }
            item.version = value.version;
        }
        if ('public' in value && value.public !== undefined) {
            if (typeof value.public !== 'boolean') throw new Error('company variable: public must be boolean');
            item.public = value.public;
        }
        if ('secret' in value && value.secret !== undefined) {
            if (typeof value.secret !== 'boolean') throw new Error('company variable: secret must be boolean');
            item.secret = value.secret;
        }
        if ('shared_for_execution' in value && value.shared_for_execution !== undefined) {
            if (typeof value.shared_for_execution !== 'boolean') {
                throw new Error('company variable: shared_for_execution must be boolean');
            }
            item.shared_for_execution = value.shared_for_execution;
        }
        if ('payload' in value && value.payload !== undefined) {
            item.payload = variablePayload(value.payload);
        }
        return item;
    });
}

function variablePayload(value: unknown): NonNullable<CompanyVariableItem['payload']> {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error('company variable: payload must be an object');
    }
    const payload: NonNullable<CompanyVariableItem['payload']> = {};
    if ('base' in value && value.base !== undefined) {
        const base = value.base;
        if (base === null || typeof base !== 'object' || Array.isArray(base)) {
            throw new Error('company variable: payload.base must be an object');
        }
        const copied: { value_kind?: string; value?: unknown } = {};
        if ('value_kind' in base && base.value_kind !== undefined) {
            if (typeof base.value_kind !== 'string') {
                throw new Error('company variable: value_kind must be a string');
            }
            copied.value_kind = base.value_kind;
        }
        if ('value' in base) copied.value = base.value;
        payload.base = copied;
    }
    if ('scopes' in value && value.scopes !== undefined) {
        if (!Array.isArray(value.scopes)) throw new Error('company variable: scopes must be an array');
        payload.scopes = value.scopes;
    }
    return payload;
}

function versionLabel(value: number | string | null | undefined): string | number {
    return value === undefined || value === null ? '' : value;
}

function historyTime(item: VariableHistoryItem): string {
    if (typeof item.updated_at === 'string') return item.updated_at;
    if (typeof item.created_at === 'string') return item.created_at;
    return '';
}

function titleText(value: string | null | undefined): string {
    return value === undefined || value === null ? '' : value;
}

function _accessLabelKey(item: CompanyVariableItem): string {
    if (item.public) {
        return 'access_public_a2a';
    }
    if (item.secret && item.shared_for_execution) {
        return 'access_secret_shared';
    }
    if (item.secret) {
        return 'access_secret_private';
    }
    return 'access_plain';
}

function _valueSummary(item: CompanyVariableItem, t: TranslateFn): string {
    if (item.secret) {
        return t('value_masked');
    }
    const base = item.payload?.base;
    if (!base) {
        return '';
    }
    if (base.value_kind === 'expression') {
        return t('value_expression');
    }
    if (item.payload && Array.isArray(item.payload.scopes) && item.payload.scopes.length > 0) {
        return t('value_scoped');
    }
    if (base.value === null || base.value === undefined) {
        return '';
    }
    if (typeof base.value === 'string') {
        return base.value;
    }
    return JSON.stringify(base.value);
}

export class PlatformCompanyVariablesPanel extends PlatformElement {
    static i18nNamespace = 'company_variables';

    static override properties: PropertyDeclarations = {
        compact: { type: Boolean, reflect: true },
        showHelp: { type: Boolean, attribute: 'show-help' },
        _historyKey: { state: true },
        _historyItems: { state: true },
    };
    declare compact: boolean;
    declare showHelp: boolean;
    declare _historyKey: string;
    declare _historyItems: VariableHistoryItem[];

    private _variables: ResourceController;
    private _versionsLoad: OpController;

    static override styles: CSSResultGroup = css`
        :host { display: block; }
        .layout {
            display: grid;
            grid-template-columns: 1fr;
            gap: var(--space-4);
        }
        :host(:not([compact])) .layout {
            grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);
        }
        .help-panel {
            padding: var(--space-3);
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-md);
            background: var(--glass-solid-medium);
            font-size: var(--text-sm);
            color: var(--text-secondary);
            line-height: 1.5;
        }
        .help-panel h4 {
            margin: 0 0 var(--space-2) 0;
            color: var(--text-primary);
            font-size: var(--text-sm);
        }
        .toolbar {
            display: flex;
            justify-content: flex-end;
            margin-bottom: var(--space-3);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: var(--space-2) var(--space-3);
            border-bottom: 1px solid var(--glass-border-subtle);
            text-align: left;
            font-size: var(--text-sm);
            vertical-align: middle;
        }
        th {
            color: var(--text-tertiary);
            font-size: var(--text-xs);
            text-transform: uppercase;
        }
        td.actions { white-space: nowrap; text-align: right; }
        .actions-group {
            display: inline-flex;
            align-items: center;
            justify-content: flex-end;
            gap: var(--space-1);
        }
        .badge {
            font-size: var(--text-xs);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--glass-border-subtle);
            color: var(--text-tertiary);
        }
        .empty {
            padding: var(--space-4);
            text-align: center;
            color: var(--text-tertiary);
        }
        .history-drawer {
            margin-top: var(--space-3);
            padding: var(--space-3);
            border: 1px dashed var(--glass-border-subtle);
            border-radius: var(--radius-md);
        }
    `;

    constructor() {
        super();
        this.compact = false;
        this.showHelp = true;
        this._historyKey = '';
        this._historyItems = [];
        this._variables = this.useResource('secrets/variables', { autoload: true });
        this._versionsLoad = this.useOp('secrets/variable_versions_load');
    }

    _create(): void {
        this.openModal('platform.company_variable_editor', {});
    }

    _edit(item: CompanyVariableItem): void {
        this.openModal('platform.company_variable_editor', { variableKey: item.variable_key });
    }

    async _delete(item: CompanyVariableItem): Promise<void> {
        const ok = await platformConfirm(
            this.t('delete_message', { key: item.variable_key }),
            {
                title: this.t('delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('delete_confirm'),
                cancelText: this.t('delete_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._variables.remove(item.variable_key);
    }

    async _showHistory(variableKey: string): Promise<void> {
        const response = await this._versionsLoad.run({
            variable_key: variableKey,
            limit: 20,
            offset: 0,
        });
        this._historyKey = variableKey;
        this._historyItems = response === null ? [] : historyItems(this._versionsLoad.lastResult);
    }

    _renderHelp(): TemplateResult | string {
        if (!this.showHelp || this.compact) {
            return '';
        }
        return html`
            <aside class="help-panel">
                <h4>${this.t('help.overview')}</h4>
                <p>${this.t('help.secrets.masked')}</p>
                <p>${this.t('help.expressions')}</p>
                <p>${this.t('help.public_a2a')}</p>
                <p>${this.t('help.versioning')}</p>
                <h4>${this.t('system_variables.title')}</h4>
                <p>${this.t('system_variables.hint')}</p>
            </aside>
        `;
    }

    _renderHistory(): TemplateResult | string {
        if (!this._historyKey) {
            return '';
        }
        return html`
            <div class="history-drawer">
                <strong>${this.t('history.title')}: ${this._historyKey}</strong>
                ${this._historyItems.length === 0
                    ? html`<div class="empty">${this.t('history.empty')}</div>`
                    : html`
                        <table>
                            <thead>
                                <tr>
                                    <th>${this.t('history.col_version')}</th>
                                    <th>${this.t('history.col_updated')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${this._historyItems.map((item) => html`
                                    <tr>
                                        <td>${this.t('badge_version', { version: versionLabel(item.version) })}</td>
                                        <td>${historyTime(item)}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }

    override render(): TemplateResult {
        const items = companyVariableItems(this._variables.items);
        return html`
            <div class="layout">
                <div>
                    <div class="toolbar">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            title=${this.t('action_create')}
                            aria-label=${this.t('action_create')}
                            @click=${() => this._create()}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </platform-button>
                    </div>
                    ${this._variables.loading && items.length === 0
                        ? html`<glass-spinner></glass-spinner>`
                        : items.length === 0
                            ? html`<div class="empty">${this.t('empty')}</div>`
                            : html`
                                <table>
                                    <thead>
                                        <tr>
                                            <th>${this.t('col_key')}</th>
                                            <th>${this.t('col_title')}</th>
                                            <th>${this.t('col_source')}</th>
                                            <th>${this.t('col_value')}</th>
                                            <th>${this.t('col_version')}</th>
                                            <th>${this.t('col_access')}</th>
                                            <th>${this.t('col_actions')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${items.map((item) => html`
                                            <tr>
                                                <td><code>${item.variable_key}</code></td>
                                                <td>${titleText(item.title)}</td>
                                                <td><span class="badge">${this.t('source_company')}</span></td>
                                                <td>${_valueSummary(item, (key: string, params?: Record<string, string | number>) => this.t(key, params))}</td>
                                                <td>${this.t('badge_version', { version: versionLabel(item.version) })}</td>
                                                <td>${this.t(_accessLabelKey(item))}</td>
                                                <td class="actions">
                                                    <div class="actions-group">
                                                        <platform-button
                                                            variant="ghost"
                                                            icon-only
                                                            density="dense"
                                                            title=${this.t('action_edit')}
                                                            aria-label=${this.t('action_edit')}
                                                            @click=${() => this._edit(item)}
                                                        >
                                                            <platform-icon name="edit" size="14"></platform-icon>
                                                        </platform-button>
                                                        <platform-button
                                                            variant="ghost"
                                                            icon-only
                                                            density="dense"
                                                            title=${this.t('action_history')}
                                                            aria-label=${this.t('action_history')}
                                                            @click=${() => this._showHistory(item.variable_key)}
                                                        >
                                                            <platform-icon name="trace-timeline" size="14"></platform-icon>
                                                        </platform-button>
                                                        <platform-button
                                                            variant="ghost"
                                                            icon-only
                                                            density="dense"
                                                            danger
                                                            title=${this.t('action_delete')}
                                                            aria-label=${this.t('action_delete')}
                                                            @click=${() => this._delete(item)}
                                                        >
                                                            <platform-icon name="trash" size="14"></platform-icon>
                                                        </platform-button>
                                                    </div>
                                                </td>
                                            </tr>
                                        `)}
                                    </tbody>
                                </table>
                            `}
                    ${this._renderHistory()}
                </div>
                ${this._renderHelp()}
            </div>
        `;
    }
}

customElements.define('platform-company-variables-panel', PlatformCompanyVariablesPanel);

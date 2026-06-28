/**
 * Company variables list panel — shared between Console and Flows embed.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { platformConfirm } from '../platform-confirm-modal.js';
import '../platform-button.js';
import '../platform-icon.js';
import '../glass-spinner.js';
import './platform-company-variable-editor-modal.js';
import './platform-system-variables-catalog.js';

function _accessLabelKey(item) {
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

function _valueSummary(item, t) {
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
    if (Array.isArray(item.payload.scopes) && item.payload.scopes.length > 0) {
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

    static properties = {
        compact: { type: Boolean, reflect: true },
        showHelp: { type: Boolean, attribute: 'show-help' },
        _historyKey: { state: true },
        _historyItems: { state: true },
    };

    static styles = css`
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

    _create() {
        this.openModal('platform.company_variable_editor', {});
    }

    _edit(item) {
        this.openModal('platform.company_variable_editor', { variableKey: item.variable_key });
    }

    async _delete(item) {
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

    async _showHistory(variableKey) {
        const response = await this._versionsLoad.run({
            variable_key: variableKey,
            limit: 20,
            offset: 0,
        });
        this._historyKey = variableKey;
        this._historyItems = response && Array.isArray(response.items) ? response.items : [];
    }

    _renderHelp() {
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

    _renderHistory() {
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
                                        <td>${this.t('badge_version', { version: item.version })}</td>
                                        <td>${item.updated_at ?? item.created_at ?? ''}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }

    render() {
        const items = this._variables.items;
        return html`
            <div class="layout">
                <div>
                    <div class="toolbar">
                        <platform-button @click=${() => this._create()}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            ${this.t('action_create')}
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
                                                <td>${item.title ?? ''}</td>
                                                <td><span class="badge">${this.t('source_company')}</span></td>
                                                <td>${_valueSummary(item, (key, params) => this.t(key, params))}</td>
                                                <td>${this.t('badge_version', { version: item.version })}</td>
                                                <td>${this.t(_accessLabelKey(item))}</td>
                                                <td class="actions">
                                                    <platform-button @click=${() => this._edit(item)}>
                                                        ${this.t('action_edit')}
                                                    </platform-button>
                                                    <platform-button @click=${() => this._showHistory(item.variable_key)}>
                                                        ${this.t('action_history')}
                                                    </platform-button>
                                                    <platform-button danger @click=${() => this._delete(item)}>
                                                        ${this.t('action_delete')}
                                                    </platform-button>
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

/**
 * flows-variables-modal — таблица переменных company-уровня.
 *
 * Источник — useResource('flows/variables') (autoload). Создание/редактирование
 * через `flows.variable_editor`. Удаление через core platformConfirm + remove.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import './flows-variable-editor-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsVariablesModal extends PlatformLightModal {
    static modalKind = 'flows.variables';
    static i18nNamespace = 'flows';

    constructor() {
        super();
        this._variables = this.useResource('flows/variables', { autoload: true });
    }

    connectedCallback() {
        super.connectedCallback();
    }

    _create() {
        this.openModal('flows.variable_editor', {});
    }

    _edit(variable) {
        this.openModal('flows.variable_editor', {
            variableKey: variable.key,
            variableValue: typeof variable.value === 'string' ? variable.value : '',
            variableSecret: Boolean(variable.secret),
        });
    }

    async _delete(variable) {
        const ok = await platformConfirm(
            this.t('variables_modal.delete_message', { key: variable.key }),
            {
                title: this.t('variables_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('variables_modal.action_delete'),
                cancelText: this.t('variables_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._variables.remove(variable.key);
    }

    _renderRows() {
        const items = this._variables.items || [];
        if (this._variables.loading && items.length === 0) {
            return html`<div class="flows-vars-empty"><glass-spinner></glass-spinner></div>`;
        }
        if (items.length === 0) {
            return html`<div class="flows-vars-empty">${this.t('variables_modal.empty')}</div>`;
        }
        return items.map((v) => html`
            <tr>
                <td><code>${v.key}</code></td>
                <td>${v.secret ? html`<em>${this.t('variables_modal.value_secret')}</em>` : (v.value ?? '')}</td>
                <td>
                    ${v.system
                        ? html`<span class="flows-vars-badge">${this.t('variables_modal.badge_system')}</span>`
                        : html`
                            <platform-button @click=${() => this._edit(v)}>
                                <platform-icon name="edit" size="14"></platform-icon>
                            </platform-button>
                            <platform-button danger @click=${() => this._delete(v)}>
                                <platform-icon name="trash" size="14"></platform-icon>
                            </platform-button>
                        `}
                </td>
            </tr>
        `);
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container flows-vars-shell">
                <style>
                    .flows-vars-shell { padding: var(--space-4); gap: var(--space-3); }
                    .flows-vars-header { display: flex; align-items: center; justify-content: space-between; }
                    .flows-vars-header h2 { margin: 0; color: var(--text-primary); }
                    .flows-vars-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
                    .flows-vars-table th, .flows-vars-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
                    .flows-vars-table th { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.05em; }
                    .flows-vars-empty { padding: var(--space-6); text-align: center; color: var(--text-tertiary); }
                    .flows-vars-badge { font-size: var(--text-xs); color: var(--text-tertiary); padding: 2px 6px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); }
                </style>
                <div class="flows-vars-header">
                    <h2>${this.t('variables_modal.title')}</h2>
                    <div>
                        <platform-button variant="primary" @click=${this._create}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            ${this.t('variables_modal.action_create')}
                        </platform-button>
                        <platform-button @click=${() => this.close()}>
                            <platform-icon name="close" size="14"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <table class="flows-vars-table">
                    <thead>
                        <tr>
                            <th>${this.t('variables_modal.col_key')}</th>
                            <th>${this.t('variables_modal.col_value')}</th>
                            <th>${this.t('variables_modal.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>${this._renderRows()}</tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('flows-variables-modal', FlowsVariablesModal);
registerModalKind(FlowsVariablesModal.modalKind, 'flows-variables-modal');

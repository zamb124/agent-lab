/**
 * flows-integrations-modal — список OAuth credentials.
 *
 * Источник — useOp('flows/integrations_list'); удаление — useOp('flows/integrations_remove').
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsIntegrationsModal extends PlatformLightModal {
    static modalKind = 'flows.integrations';
    static i18nNamespace = 'flows';

    constructor() {
        super();
        this._listOp = this.useOp('flows/integrations_list');
        this._removeOp = this.useOp('flows/integrations_remove');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._listOp.run({});
    }

    async _delete(item) {
        const ok = await platformConfirm(
            this.t('integrations_modal.delete_message', { provider: item.provider, service: item.service }),
            {
                title: this.t('integrations_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('integrations_modal.action_delete'),
                cancelText: this.t('integrations_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._removeOp.run({ provider: item.provider, service: item.service });
        await this._listOp.run({});
    }

    _renderRows() {
        const result = this._listOp.lastResult;
        const items = Array.isArray(result?.items)
            ? result.items
            : Array.isArray(result)
                ? result
                : [];
        if (this._listOp.busy && items.length === 0) {
            return html`<tr><td colspan="4"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="4" class="int-empty">${this.t('integrations_modal.empty')}</td></tr>`;
        }
        return items.map((it) => html`
            <tr>
                <td>${it.provider}</td>
                <td>${it.service}</td>
                <td>${it.status || ''}</td>
                <td>
                    <platform-button danger @click=${() => this._delete(it)}>
                        ${this.t('integrations_modal.action_disconnect')}
                    </platform-button>
                </td>
            </tr>
        `);
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container int-shell">
                <style>
                    .int-shell { padding: var(--space-4); gap: var(--space-3); }
                    .int-header { display: flex; align-items: center; justify-content: space-between; }
                    .int-header h2 { margin: 0; color: var(--text-primary); }
                    .int-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
                    .int-table th, .int-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
                    .int-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
                </style>
                <div class="int-header">
                    <h2>${this.t('integrations_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                <table class="int-table">
                    <thead>
                        <tr>
                            <th>${this.t('integrations_modal.col_provider')}</th>
                            <th>${this.t('integrations_modal.col_service')}</th>
                            <th>${this.t('integrations_modal.col_status')}</th>
                            <th>${this.t('integrations_modal.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>${this._renderRows()}</tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('flows-integrations-modal', FlowsIntegrationsModal);
registerModalKind(FlowsIntegrationsModal.modalKind, 'flows-integrations-modal');

/**
 * flows-integrations-modal — список OAuth credentials.
 *
 * Источник — useOp('flows/integrations_list'); удаление — useOp('flows/integrations_remove').
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import { asString } from '../_helpers/flows-resolvers.js';

export class FlowsIntegrationsModal extends PlatformModal {
    static modalKind = 'flows.integrations';
    static i18nNamespace = 'flows';

    static styles = [
        ...PlatformModal.styles,
        css`
            .int-search {
                margin-bottom: var(--space-3);
            }
            .int-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
            .int-table th, .int-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
            .int-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        _query: { state: true },
    };

    constructor() {
        super();
        this.size = 'lg';
        this._query = '';
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
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) return;
        await this._removeOp.run({ provider: item.provider, service: item.service });
        await this._listOp.run({});
    }

    _onSearchChange(e) {
        const rawValue = e.detail.value;
        if (typeof rawValue !== 'string') {
            throw new TypeError('flows-integrations-modal: search expects string detail.value');
        }
        this._query = rawValue;
    }

    _listItems() {
        const result = this._listOp.lastResult;
        if (Array.isArray(result?.items)) {
            return result.items;
        }
        if (Array.isArray(result)) {
            return result;
        }
        return [];
    }

    _filteredItems() {
        const items = this._listItems();
        const query = this._query.trim().toLocaleLowerCase();
        if (query.length === 0) {
            return items;
        }
        return items.filter((item) => {
            if (!item || typeof item !== 'object') {
                return false;
            }
            const provider = typeof item.provider === 'string' ? item.provider : '';
            const service = typeof item.service === 'string' ? item.service : '';
            const status = asString(item.status);
            const haystack = `${provider} ${service} ${status}`.toLocaleLowerCase();
            return haystack.includes(query);
        });
    }

    _renderRows() {
        const items = this._filteredItems();
        if (this._listOp.busy && items.length === 0 && this._query.trim().length === 0) {
            return html`<tr><td colspan="4"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="4" class="int-empty">${this.t('integrations_modal.empty')}</td></tr>`;
        }
        return items.map((it) => html`
            <tr>
                <td>${it.provider}</td>
                <td>${it.service}</td>
                <td>${asString(it.status)}</td>
                <td>
                    <platform-button danger @click=${() => this._delete(it)}>
                        ${this.t('integrations_modal.action_disconnect')}
                    </platform-button>
                </td>
            </tr>
        `);
    }

    renderHeader() {
        return this.t('integrations_modal.title');
    }

    renderBody() {
        return html`
            <platform-modal-search-field
                class="int-search"
                layout="fill"
                .value=${this._query}
                placeholder=${this.t('integrations_modal.search')}
                @change=${this._onSearchChange}
            ></platform-modal-search-field>
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
        `;
    }
}

customElements.define('flows-integrations-modal', FlowsIntegrationsModal);
registerModalKind(FlowsIntegrationsModal.modalKind, 'flows-integrations-modal');

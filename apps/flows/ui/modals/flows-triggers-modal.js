/**
 * flows-triggers-modal — список триггеров flow.
 *
 * Источник — useOp('flows/triggers_list'); CRUD через trigger_create/update/remove ops.
 * Редактор открывается через `flows.trigger_editor`.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import './flows-trigger-editor-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsTriggersModal extends PlatformModal {
    static modalKind = 'flows.triggers';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .trg-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
            .trg-table th, .trg-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
            .trg-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.flowId = '';
        this._listOp = this.useOp('flows/triggers_list');
        this._removeOp = this.useOp('flows/trigger_remove');
        this._testOp = this.useOp('flows/trigger_test');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            void this._listOp.run({ flow_id: this.flowId });
        }
    }

    _create() {
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: null });
    }

    _edit(t) {
        this.openModal('flows.trigger_editor', { flowId: this.flowId, trigger: t });
    }

    async _delete(t) {
        const ok = await platformConfirm(
            this.t('triggers_modal.delete_message', { id: t.trigger_id }),
            {
                title: this.t('triggers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('triggers_modal.action_delete'),
                cancelText: this.t('triggers_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._removeOp.run({ flow_id: this.flowId, trigger_id: t.trigger_id });
        await this._listOp.run({ flow_id: this.flowId });
    }

    async _test(t) {
        await this._testOp.run({ flow_id: this.flowId, trigger_id: t.trigger_id, body: {} });
    }

    _renderRows() {
        const items = Array.isArray(this._listOp.lastResult) ? this._listOp.lastResult : [];
        if (this._listOp.busy && items.length === 0) {
            return html`<tr><td colspan="5"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="5" class="trg-empty">${this.t('triggers_modal.empty')}</td></tr>`;
        }
        return items.map((t) => html`
            <tr>
                <td><code>${t.trigger_id}</code></td>
                <td>${t.name}</td>
                <td>${t.type}</td>
                <td>${t.enabled ? this.t('triggers_modal.status_enabled') : this.t('triggers_modal.status_disabled')}</td>
                <td>
                    <platform-button @click=${() => this._test(t)}>${this.t('triggers_modal.action_test')}</platform-button>
                    <platform-button @click=${() => this._edit(t)}>${this.t('triggers_modal.action_edit')}</platform-button>
                    <platform-button danger @click=${() => this._delete(t)}>
                        <platform-icon name="trash" size="14"></platform-icon>
                    </platform-button>
                </td>
            </tr>
        `);
    }

    renderHeader() {
        return this.t('triggers_modal.title');
    }

    renderHeaderActions() {
        return html`
            <platform-button variant="primary" @click=${() => this._create()}>
                <platform-icon name="plus" size="14"></platform-icon>
                ${this.t('triggers_modal.action_create')}
            </platform-button>
        `;
    }

    renderBody() {
        return html`
            <table class="trg-table">
                <thead>
                    <tr>
                        <th>${this.t('triggers_modal.col_id')}</th>
                        <th>${this.t('triggers_modal.col_name')}</th>
                        <th>${this.t('triggers_modal.col_type')}</th>
                        <th>${this.t('triggers_modal.col_status')}</th>
                        <th>${this.t('triggers_modal.col_actions')}</th>
                    </tr>
                </thead>
                <tbody>${this._renderRows()}</tbody>
            </table>
        `;
    }
}

customElements.define('flows-triggers-modal', FlowsTriggersModal);
registerModalKind(FlowsTriggersModal.modalKind, 'flows-triggers-modal');

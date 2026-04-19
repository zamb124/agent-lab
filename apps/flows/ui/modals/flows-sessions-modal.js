/**
 * flows-sessions-modal — список сессий выбранного flow.
 *
 * Источник — useResource('flows/sessions') с фильтром `flow_id`. Открытие
 * сессии — `this.navigate('flow_chat_session', { flowId, sessionId })`.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsSessionsModal extends PlatformLightModal {
    static modalKind = 'flows.sessions';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        flowId: { type: String },
    };

    constructor() {
        super();
        this.flowId = '';
        this._sessions = this.useResource('flows/sessions');
    }

    connectedCallback() {
        super.connectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId')) {
            this._sessions.load(this.flowId ? { flow_id: this.flowId, limit: 200 } : { limit: 200 });
        }
    }

    _open(session) {
        const sessionId = session.session_id || session.id;
        if (!sessionId) return;
        this.navigate('flow_chat_session', { flowId: this.flowId, sessionId });
        this.close();
    }

    async _delete(session) {
        const sessionId = session.session_id || session.id;
        if (!sessionId) return;
        const ok = await platformConfirm(
            this.t('sessions_modal.delete_message', { id: sessionId }),
            {
                title: this.t('sessions_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('sessions_modal.delete_btn'),
                cancelText: this.t('sessions_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._sessions.remove(sessionId);
    }

    _renderRows() {
        const items = this._sessions.items || [];
        if (this._sessions.loading && items.length === 0) {
            return html`<tr><td colspan="3"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="3" class="flows-sessions-empty">${this.t('sessions_modal.empty')}</td></tr>`;
        }
        return items.map((s) => html`
            <tr>
                <td><code>${s.session_id || s.id}</code></td>
                <td>${s.flow_id || ''}</td>
                <td>${s.last_message_at || s.updated_at || ''}</td>
                <td>
                    <platform-button @click=${() => this._open(s)}>${this.t('sessions_modal.continue_title')}</platform-button>
                    <platform-button danger @click=${() => this._delete(s)}>
                        <platform-icon name="trash" size="14"></platform-icon>
                    </platform-button>
                </td>
            </tr>
        `);
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container flows-sessions-shell">
                <style>
                    .flows-sessions-shell { padding: var(--space-4); gap: var(--space-3); }
                    .flows-sessions-header { display: flex; align-items: center; justify-content: space-between; }
                    .flows-sessions-header h2 { margin: 0; color: var(--text-primary); }
                    .flows-sessions-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
                    .flows-sessions-table th, .flows-sessions-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
                    .flows-sessions-table th { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.05em; }
                    .flows-sessions-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-6); }
                </style>
                <div class="flows-sessions-header">
                    <h2>${this.t('sessions_modal.modal_title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                <table class="flows-sessions-table">
                    <thead>
                        <tr>
                            <th>${this.t('sessions_modal.col_session')}</th>
                            <th>${this.t('sessions_modal.col_flow')}</th>
                            <th>${this.t('sessions_modal.col_last')}</th>
                            <th>${this.t('sessions_modal.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>${this._renderRows()}</tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('flows-sessions-modal', FlowsSessionsModal);
registerModalKind(FlowsSessionsModal.modalKind, 'flows-sessions-modal');

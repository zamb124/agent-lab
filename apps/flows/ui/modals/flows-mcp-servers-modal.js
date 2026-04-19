/**
 * flows-mcp-servers-modal — управление MCP-серверами компании.
 *
 * Источник — useResource('flows/mcp_servers'); update через flows/mcp_server_update;
 * sync/test — через useOp('flows/mcp_server_sync')/useOp('flows/mcp_server_test').
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const SERVER_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]{1,63}$/;
const TRANSPORT_TYPES = Object.freeze(['http', 'sse']);

export class FlowsMcpServersModal extends PlatformLightModal {
    static modalKind = 'flows.mcp_servers';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        _editing: { state: true },
        _form: { state: true },
    };

    constructor() {
        super();
        this._editing = null;
        this._form = { server_id: '', name: '', url: '', transport_type: 'http', description: '' };
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
        this._update = this.useOp('flows/mcp_server_update');
        this._syncOp = this.useOp('flows/mcp_server_sync');
        this._testOp = this.useOp('flows/mcp_server_test');
    }

    connectedCallback() {
        super.connectedCallback();
    }

    _resetForm() {
        this._editing = null;
        this._form = { server_id: '', name: '', url: '', transport_type: 'http', description: '' };
    }

    _editServer(s) {
        this._editing = s.server_id;
        this._form = {
            server_id: s.server_id,
            name: s.name,
            url: s.url,
            transport_type: s.transport_type || 'http',
            description: s.description || '',
        };
    }

    async _save() {
        const f = this._form;
        if (!SERVER_ID_PATTERN.test(f.server_id) || !f.name.trim() || !f.url.trim()) return;
        if (this._editing) {
            await this._update.run({
                server_id: f.server_id,
                body: { name: f.name, url: f.url, transport_type: f.transport_type, description: f.description },
            });
        } else {
            await this._servers.create({
                server_id: f.server_id,
                name: f.name,
                url: f.url,
                transport_type: f.transport_type,
                description: f.description,
            });
        }
        this._resetForm();
    }

    async _sync(s) {
        await this._syncOp.run({ server_id: s.server_id });
        this._servers.load();
    }

    async _test(s) {
        await this._testOp.run({ server_id: s.server_id });
    }

    async _delete(s) {
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.delete_message', { id: s.server_id }),
            {
                title: this.t('mcp_servers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('mcp_servers_modal.action_delete'),
                cancelText: this.t('mcp_servers_modal.action_cancel'),
            },
        );
        if (!ok) return;
        await this._servers.remove(s.server_id);
    }

    _renderForm() {
        const f = this._form;
        const valid = SERVER_ID_PATTERN.test(f.server_id) && f.name.trim() && f.url.trim();
        return html`
            <div class="mcp-form">
                <div class="mcp-row">
                    <input
                        type="text"
                        placeholder=${this.t('mcp_servers_modal.field_id')}
                        .value=${f.server_id}
                        ?disabled=${Boolean(this._editing)}
                        @input=${(e) => { this._form = { ...this._form, server_id: e.target.value }; }}
                    />
                    <input
                        type="text"
                        placeholder=${this.t('mcp_servers_modal.field_name')}
                        .value=${f.name}
                        @input=${(e) => { this._form = { ...this._form, name: e.target.value }; }}
                    />
                    <select
                        .value=${f.transport_type}
                        @change=${(e) => { this._form = { ...this._form, transport_type: e.target.value }; }}
                    >
                        ${TRANSPORT_TYPES.map((t) => html`<option value=${t}>${t}</option>`)}
                    </select>
                </div>
                <div class="mcp-row">
                    <input
                        type="url"
                        placeholder=${this.t('mcp_servers_modal.field_url')}
                        .value=${f.url}
                        @input=${(e) => { this._form = { ...this._form, url: e.target.value }; }}
                        style="flex:2"
                    />
                    <input
                        type="text"
                        placeholder=${this.t('mcp_servers_modal.field_description')}
                        .value=${f.description}
                        @input=${(e) => { this._form = { ...this._form, description: e.target.value }; }}
                        style="flex:3"
                    />
                </div>
                <div class="mcp-row">
                    ${this._editing
                        ? html`<platform-button @click=${() => this._resetForm()}>${this.t('mcp_servers_modal.action_cancel')}</platform-button>`
                        : ''}
                    <platform-button variant="primary" ?disabled=${!valid} @click=${this._save}>
                        ${this._editing
                            ? this.t('mcp_servers_modal.action_save')
                            : this.t('mcp_servers_modal.action_add')}
                    </platform-button>
                </div>
            </div>
        `;
    }

    _renderRows() {
        const items = this._servers.items || [];
        if (this._servers.loading && items.length === 0) {
            return html`<tr><td colspan="5"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="5" class="mcp-empty">${this.t('mcp_servers_modal.empty')}</td></tr>`;
        }
        return items.map((s) => html`
            <tr>
                <td><code>${s.server_id}</code></td>
                <td>${s.name}</td>
                <td>${s.transport_type}</td>
                <td>${s.cached_tools?.length || 0}</td>
                <td>
                    <platform-button @click=${() => this._sync(s)}>${this.t('mcp_servers_modal.action_sync')}</platform-button>
                    <platform-button @click=${() => this._test(s)}>${this.t('mcp_servers_modal.action_test')}</platform-button>
                    <platform-button @click=${() => this._editServer(s)}>${this.t('mcp_servers_modal.action_edit')}</platform-button>
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
            <div class="light-modal-container mcp-shell">
                <style>
                    .mcp-shell { padding: var(--space-4); gap: var(--space-3); }
                    .mcp-header { display: flex; align-items: center; justify-content: space-between; }
                    .mcp-header h2 { margin: 0; color: var(--text-primary); }
                    .mcp-form { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); margin-bottom: var(--space-3); }
                    .mcp-row { display: flex; gap: var(--space-2); }
                    .mcp-form input, .mcp-form select { flex: 1; padding: var(--space-2); border-radius: var(--radius-sm); border: 1px solid var(--glass-border-subtle); background: var(--glass-solid-subtle); color: var(--text-primary); font: inherit; }
                    .mcp-table { width: 100%; border-collapse: collapse; color: var(--text-secondary); }
                    .mcp-table th, .mcp-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border-subtle); }
                    .mcp-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-4); }
                </style>
                <div class="mcp-header">
                    <h2>${this.t('mcp_servers_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                ${this._renderForm()}
                <table class="mcp-table">
                    <thead>
                        <tr>
                            <th>${this.t('mcp_servers_modal.col_id')}</th>
                            <th>${this.t('mcp_servers_modal.col_name')}</th>
                            <th>${this.t('mcp_servers_modal.col_transport')}</th>
                            <th>${this.t('mcp_servers_modal.col_tools')}</th>
                            <th>${this.t('mcp_servers_modal.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>${this._renderRows()}</tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('flows-mcp-servers-modal', FlowsMcpServersModal);
registerModalKind(FlowsMcpServersModal.modalKind, 'flows-mcp-servers-modal');

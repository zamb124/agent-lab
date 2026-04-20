/**
 * sync-call-link-edit-modal — редактирование scheduled call link.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncCallLinkEditModal extends PlatformFormModal {
    static modalKind = 'sync.call_link_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        linkToken: { type: String },
        _title: { state: true },
        _scheduledAt: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];

    constructor() {
        super();
        this.linkToken = '';
        this._title = '';
        this._scheduledAt = '';
        this._hydrated = false;
        this._links = this.useResource('sync/call_links_scheduled');
        this._linkUpdate = this.useOp('sync/call_link_update');
        this._linkRemove = this.useOp('sync/call_link_remove');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.linkToken) {
            const item = this._links.byId[this.linkToken];
            if (item) {
                this._title = typeof item.title === 'string' ? item.title : '';
                if (item.scheduled_at) {
                    this._scheduledAt = new Date(item.scheduled_at).toISOString().slice(0, 16);
                }
                this._hydrated = true;
            }
        }
    }

    renderHeader() { return html`<h3>${this.t('call_link.title_edit')}</h3>`; }

    renderBody() {
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('call_link.field_title')}</label>
                <input
                    class="form-input"
                    type="text"
                    .value=${this._title}
                    @input=${(e) => { this._title = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.t('call_link.field_scheduled_at')}</label>
                <input
                    class="form-input"
                    type="datetime-local"
                    .value=${this._scheduledAt}
                    @input=${(e) => { this._scheduledAt = e.target.value; this.isDirty = true; }}
                />
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="danger" @click=${this._onDelete}>${this.t('call_link.action_delete')}</platform-button>
                <platform-button variant="secondary" @click=${() => this.close()} style="margin-left: auto;">${this.t('call_link.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit}>${this.t('call_link.action_save')}</platform-button>
            </div>
        `;
    }

    _onSubmit() {
        if (!this.linkToken) return;
        const body = { link_token: this.linkToken, title: this._title.trim() };
        if (this._scheduledAt) body.scheduled_at = new Date(this._scheduledAt).toISOString();
        this._linkUpdate.run(body);
        this.closeAfterSave();
    }

    _onDelete() {
        if (!this.linkToken) return;
        this._linkRemove.run({ link_token: this.linkToken });
        this.closeAfterSave();
    }
}

customElements.define('sync-call-link-edit-modal', SyncCallLinkEditModal);
registerModalKind(SyncCallLinkEditModal.modalKind, 'sync-call-link-edit-modal');

/**
 * sync-call-link-create-modal — создание гостевой ссылки звонка / scheduled meeting.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncCallLinkCreateModal extends PlatformFormModal {
    static modalKind = 'sync.call_link_create';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        callId: { type: String },
        _title: { state: true },
        _scheduledAt: { state: true },
        _durationMinutes: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];

    constructor() {
        super();
        this.callId = '';
        this._title = '';
        this._scheduledAt = '';
        this._durationMinutes = 30;
        this._linkCreate = this.useOp('sync/call_link_create');
    }

    renderHeader() { return html`<h3>${this.t('call_link.title_create')}</h3>`; }

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
            <div class="form-group">
                <label class="form-label">${this.t('call_link.field_duration')}</label>
                <input
                    class="form-input"
                    type="number"
                    min="5"
                    max="480"
                    .value=${this._durationMinutes}
                    @input=${(e) => { const parsed = parseInt(e.target.value, 10); this._durationMinutes = Number.isFinite(parsed) && parsed > 0 ? parsed : 30; this.isDirty = true; }}
                />
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('call_link.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._title.trim().length === 0}>
                    ${this.t('call_link.action_create')}
                </platform-button>
            </div>
        `;
    }

    _onSubmit() {
        const body = {
            title: this._title.trim(),
            duration_minutes: this._durationMinutes,
        };
        if (this._scheduledAt) body.scheduled_at = new Date(this._scheduledAt).toISOString();
        if (this.callId) body.call_id = this.callId;
        this._linkCreate.run(body);
        this.closeAfterSave();
    }
}

customElements.define('sync-call-link-create-modal', SyncCallLinkCreateModal);
registerModalKind(SyncCallLinkCreateModal.modalKind, 'sync-call-link-create-modal');

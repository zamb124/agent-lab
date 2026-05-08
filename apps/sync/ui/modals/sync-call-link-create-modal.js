/**
 * sync-call-link-create-modal — создание гостевой ссылки звонка / scheduled meeting.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

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
            <platform-field
                type="string"
                mode="edit"
                label=${this.t('call_link.field_title')}
                .value=${this._title}
                @change=${(e) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('call link create: title expects detail.value string');
                    }
                    this._title = e.detail.value;
                    this.isDirty = true;
                }}
            ></platform-field>
            <platform-field
                type="datetime"
                mode="edit"
                label=${this.t('call_link.field_scheduled_at')}
                .value=${this._scheduledAt.length > 0 ? this._scheduledAt : null}
                @change=${(e) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('call link create: scheduled_at expects detail.value string');
                    }
                    this._scheduledAt = e.detail.value;
                    this.isDirty = true;
                }}
            ></platform-field>
            <platform-field
                type="integer"
                mode="edit"
                label=${this.t('call_link.field_duration')}
                .value=${this._durationMinutes}
                @change=${(e) => {
                    if (!e.detail) {
                        throw new Error('call link create: duration missing detail');
                    }
                    if (e.detail.value === null) {
                        this._durationMinutes = 30;
                        this.isDirty = true;
                        return;
                    }
                    if (typeof e.detail.value !== 'number') {
                        throw new Error('call link create: duration expects integer detail.value');
                    }
                    const parsed = e.detail.value;
                    this._durationMinutes = parsed > 0 ? parsed : 30;
                    this.isDirty = true;
                }}
            ></platform-field>
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

/**
 * sync-call-link-edit-modal — редактирование scheduled meeting.
 *
 * Scheduled meeting — platform calendar event kind="meeting"; SyncCallLink —
 * производная (создаётся/патчится/удаляется reconcile'ом CalendarService через
 * ServiceClient по metadata.sync_link_token). Поэтому модалка правит и удаляет
 * календарное событие (calendar/event/update_requested|delete_requested), а link
 * синхронизируется бэкендом.
 * Событие гидрачим через calendar/events/list (нужны attendees/timezone, чтобы
 * upsert их не затёр), находим по calendar_event_id из CallScheduledLinkRead.
 */

import { html } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { CALENDAR_EVENTS } from '@platform/lib/events/reducers/calendar.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

function linkRows(value: unknown[]): Record<string, unknown>[] {
    const rows: Record<string, unknown>[] = [];
    for (const row of value) {
        if (!isPlainRecord(row)) {
            throw new Error('sync-call-link-edit-modal: link must be an object');
        }
        rows.push(row);
    }
    return rows;
}

export class SyncCallLinkEditModal extends PlatformFormModal {
    static modalKind = 'sync.call_link_edit';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        linkToken: { type: String },
        _title: { state: true },
        _scheduledAt: { state: true },
        _durationMinutes: { state: true },
        _hydrated: { state: true },
        _saving: { state: true },
    };
    declare linkToken: string;
    declare _title: string;
    declare _scheduledAt: string;
    declare _durationMinutes: number;
    declare _hydrated: boolean;
    declare _saving: boolean;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];
    private _linksOp: OpController;
    private _eventId: string | null = null;
    private _eventAttendees: unknown[] = [];
    private _eventTimezone = 'UTC';
    private _eventStatus = 'confirmed';

    constructor() {
        super();
        this.linkToken = '';
        this._title = '';
        this._scheduledAt = '';
        this._durationMinutes = 30;
        this._hydrated = false;
        this._saving = false;
        this._linksOp = this.useOp('sync/call_links_scheduled');
        this.useEvent('sync/call_links_scheduled/succeeded', () => this.requestUpdate());
        this.useEvent(CALENDAR_EVENTS.EVENT_UPDATED, () => {
            if (this._saving) {
                this._saving = false;
                this.closeAfterSave();
            }
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_DELETED, () => {
            if (this._saving) {
                this._saving = false;
                this.closeAfterSave();
            }
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_UPDATE_FAILED, () => {
            this._saving = false;
            this.toast('call_link.err_save', { type: 'error' });
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_DELETE_FAILED, () => {
            this._saving = false;
            this.toast('call_link.err_save', { type: 'error' });
        });
        this.useEvent(CALENDAR_EVENTS.EVENTS_LOADED, (e) => {
            if (!isPlainRecord(e.payload) || !Array.isArray(e.payload.items)) return;
            const event = this._findEvent(e.payload.items);
            if (event) this._hydrateFromEvent(event);
        });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const now = Date.now();
        this._linksOp.run({
            start_at: new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString(),
            end_at: new Date(now + 365 * 24 * 60 * 60 * 1000).toISOString(),
            limit: 200,
            offset: 0,
        });
    }

    _resolveItems() {
        const result = this._linksOp.lastResult;
        if (Array.isArray(result)) return linkRows(result);
        if (isPlainRecord(result)) {
            const items = result.items;
            if (Array.isArray(items)) return linkRows(items);
        }
        return [];
    }

    private _findEvent(items: unknown[]): Record<string, unknown> | null {
        if (!this._eventId) return null;
        for (const raw of items) {
            if (isPlainRecord(raw) && raw.event_id === this._eventId) return raw;
        }
        return null;
    }

    private _hydrateFromEvent(event: Record<string, unknown>): void {
        if (typeof event.title === 'string') this._title = event.title;
        if (Array.isArray(event.attendees)) this._eventAttendees = event.attendees;
        if (typeof event.timezone === 'string' && event.timezone) this._eventTimezone = event.timezone;
        if (typeof event.status === 'string' && event.status) this._eventStatus = event.status;
        const start = typeof event.start_at === 'string' ? new Date(event.start_at) : null;
        const end = typeof event.end_at === 'string' ? new Date(event.end_at) : null;
        if (start && !Number.isNaN(start.getTime())) {
            this._scheduledAt = start.toISOString().slice(0, 16);
            if (end && !Number.isNaN(end.getTime()) && end.getTime() > start.getTime()) {
                this._durationMinutes = Math.round((end.getTime() - start.getTime()) / 60_000);
            }
        }
        this._hydrated = true;
        this.requestUpdate();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (!this._hydrated && this.linkToken) {
            const item = this._resolveItems().find((row) => row.link_token === this.linkToken);
            if (item) {
                this._title = typeof item.title === 'string' ? item.title : '';
                const eventId = typeof item.calendar_event_id === 'string' ? item.calendar_event_id : '';
                if (!eventId) {
                    this.toast('call_link.err_save', { type: 'error' });
                    this.close();
                    return;
                }
                this._eventId = eventId;
                const startRaw = typeof item.scheduled_start_at === 'string' ? item.scheduled_start_at : '';
                const endRaw = typeof item.scheduled_end_at === 'string' ? item.scheduled_end_at : '';
                const start = startRaw ? new Date(startRaw) : null;
                const end = endRaw ? new Date(endRaw) : null;
                if (start && !Number.isNaN(start.getTime())) {
                    this._scheduledAt = start.toISOString().slice(0, 16);
                    if (end && !Number.isNaN(end.getTime()) && end.getTime() > start.getTime()) {
                        this._durationMinutes = Math.round((end.getTime() - start.getTime()) / 60_000);
                    }
                }
                // Тянем сам event ради attendees/timezone — upsert не должен их затереть.
                const from = new Date((start?.getTime() ?? Date.now()) - 24 * 60 * 60 * 1000);
                const to = new Date((end?.getTime() ?? Date.now()) + 24 * 60 * 60 * 1000);
                this.dispatch(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {
                    start_at: from.toISOString(),
                    end_at: to.toISOString(),
                    include_sources: ['platform'],
                    limit: 100,
                });
                this._hydrated = true;
            }
        }
    }

    override renderHeader() { return html`<h3>${this.t('call_link.title_edit')}</h3>`; }

    override renderBody() {
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=${this.t('call_link.field_title')}
                .value=${this._title}
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('call link edit: title expects detail.value string');
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
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('call link edit: scheduled_at expects detail.value string');
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
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
                    if (!e.detail) {
                        throw new Error('call link edit: duration missing detail');
                    }
                    if (e.detail.value === null) {
                        this._durationMinutes = 30;
                        this.isDirty = true;
                        return;
                    }
                    if (typeof e.detail.value !== 'number') {
                        throw new Error('call link edit: duration expects integer detail.value');
                    }
                    const parsed = e.detail.value;
                    this._durationMinutes = parsed > 0 ? parsed : 30;
                    this.isDirty = true;
                }}
            ></platform-field>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="danger" @click=${this._onDelete} ?disabled=${this._saving}>${this.t('call_link.action_delete')}</platform-button>
                <platform-button variant="secondary" @click=${() => this.close()} style="margin-left: auto;">${this.t('call_link.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._saving}>${this.t('call_link.action_save')}</platform-button>
            </div>
        `;
    }

    override async _onSubmit(): Promise<void> {
        if (!this._eventId) return;
        const start = this._scheduledAt ? new Date(this._scheduledAt) : new Date();
        const end = new Date(start.getTime() + this._durationMinutes * 60_000);
        this._saving = true;
        this.dispatch(CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED, {
            event_id: this._eventId,
            title: this._title.trim(),
            kind: 'meeting',
            source: 'platform',
            status: this._eventStatus,
            timezone: this._eventTimezone,
            start_at: start.toISOString(),
            end_at: end.toISOString(),
            attendees: this._eventAttendees,
        });
    }

    _onDelete() {
        if (!this._eventId) return;
        this._saving = true;
        this.dispatch(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, { event_id: this._eventId });
    }
}

customElements.define('sync-call-link-edit-modal', SyncCallLinkEditModal);
registerModalKind(SyncCallLinkEditModal.modalKind, 'sync-call-link-edit-modal');

/**
 * sync-call-link-create-modal — создание scheduled meeting.
 *
 * Scheduled meeting — это platform calendar event с kind="meeting": при создании
 * CalendarService reconcile сам создаёт SyncCallLink через ServiceClient
 * (metadata.sync_link_token). Поэтому модалка диспатчит calendar/event/create_requested,
 * а не op sync/call_link_create (тот контракт обслуживает reconcile).
 * Для platform-события обязателен mailbox_binding_id — берём активный ящик юзера
 * из mail state (bindings грузим при открытии модалки).
 */

import { html } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { CALENDAR_EVENTS } from '@platform/lib/events/reducers/calendar.js';
import { MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

interface MailSlice {
    bindings?: unknown[];
    activeMailboxBindingId?: string | null;
}

export class SyncCallLinkCreateModal extends PlatformFormModal {
    static modalKind = 'sync.call_link_create';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        _title: { state: true },
        _scheduledAt: { state: true },
        _durationMinutes: { state: true },
        _saving: { state: true },
    };
    declare _title: string;
    declare _scheduledAt: string;
    declare _durationMinutes: number;
    declare _saving: boolean;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];
    private _mailSelect: SelectController<MailSlice>;

    constructor() {
        super();
        this._title = '';
        this._scheduledAt = '';
        this._durationMinutes = 30;
        this._saving = false;
        this._mailSelect = this.select((state) => state.mail as unknown as MailSlice);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(CALENDAR_EVENTS.EVENT_CREATED, () => {
            if (this._saving) {
                this._saving = false;
                this.closeAfterSave();
            }
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_CREATE_FAILED, () => {
            this._saving = false;
            this.toast('call_link.err_save', { type: 'error' });
        });
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate?.(changed);
        if (changed.has('open') && this.open) {
            this._saving = false;
            const mail = this._mailSelect.value;
            const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
            if (bindings.length === 0) {
                this.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null);
            }
        }
    }

    _mailboxBindingId(): string | null {
        const mail = this._mailSelect.value;
        const bindings = Array.isArray(mail?.bindings) ? mail.bindings : [];
        const active = typeof mail?.activeMailboxBindingId === 'string' ? mail.activeMailboxBindingId : null;
        const pick = (predicate: (b: Record<string, unknown>) => boolean): string | null => {
            for (const raw of bindings) {
                if (!isPlainRecord(raw)) continue;
                if (!predicate(raw)) continue;
                const id = raw.mailbox_binding_id;
                if (typeof id === 'string' && id !== '') return id;
            }
            return null;
        };
        if (active) {
            const found = pick((b) => b.mailbox_binding_id === active);
            if (found) return found;
        }
        return pick(() => true);
    }

    override renderHeader() { return html`<h3>${this.t('call_link.title_create')}</h3>`; }

    override renderBody() {
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=${this.t('call_link.field_title')}
                .value=${this._title}
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
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
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
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
                @change=${(e: CustomEvent<{ value?: unknown }>) => {
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

    override renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('call_link.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._saving || this._title.trim().length === 0}>
                    ${this.t('call_link.action_create')}
                </platform-button>
            </div>
        `;
    }

    override async _onSubmit(): Promise<void> {
        const mailboxBindingId = this._mailboxBindingId();
        if (!mailboxBindingId) {
            this.toast('call_link.err_no_mailbox', { type: 'error' });
            return;
        }
        const start = this._scheduledAt ? new Date(this._scheduledAt) : new Date();
        const end = new Date(start.getTime() + this._durationMinutes * 60_000);
        this._saving = true;
        this.dispatch(CALENDAR_EVENTS.EVENT_CREATE_REQUESTED, {
            title: this._title.trim(),
            kind: 'meeting',
            source: 'platform',
            status: 'confirmed',
            start_at: start.toISOString(),
            end_at: end.toISOString(),
            attendees: [],
            mailbox_binding_id: mailboxBindingId,
        });
    }
}

customElements.define('sync-call-link-create-modal', SyncCallLinkCreateModal);
registerModalKind(SyncCallLinkCreateModal.modalKind, 'sync-call-link-create-modal');

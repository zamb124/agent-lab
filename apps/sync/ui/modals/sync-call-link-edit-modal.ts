/**
 * sync-call-link-edit-modal — редактирование scheduled call link.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { isPlainRecord } from '@platform/lib/events/payload.js';

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
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

export class SyncCallLinkEditModal extends PlatformFormModal {
    static modalKind = 'sync.call_link_edit';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        linkToken: { type: String },
        _title: { state: true },
        _scheduledAt: { state: true },
        _hydrated: { state: true },
    };
    declare linkToken: string;
    declare _title: string;
    declare _scheduledAt: string;
    declare _hydrated: boolean;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];
    private _linksOp: OpController;
    private _linkUpdate: OpController;
    private _linkRemove: OpController;

    constructor() {
        super();
        this.linkToken = '';
        this._title = '';
        this._scheduledAt = '';
        this._hydrated = false;
        this._linksOp = this.useOp('sync/call_links_scheduled');
        this._linkUpdate = this.useOp('sync/call_link_update');
        this._linkRemove = this.useOp('sync/call_link_remove');
        this.useEvent('sync/call_links_scheduled/succeeded', () => this.requestUpdate());
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

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (!this._hydrated && this.linkToken) {
            const item = this._resolveItems().find((row) => row.link_token === this.linkToken);
            if (item) {
                this._title = typeof item.title === 'string' ? item.title : '';
                const raw = typeof item.scheduled_start_at === 'string'
                    ? item.scheduled_start_at
                    : (typeof item.scheduled_at === 'string' ? item.scheduled_at : '');
                if (raw) {
                    const d = new Date(raw);
                    if (!Number.isNaN(d.getTime())) {
                        this._scheduledAt = d.toISOString().slice(0, 16);
                    }
                }
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
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="danger" @click=${this._onDelete}>${this.t('call_link.action_delete')}</platform-button>
                <platform-button variant="secondary" @click=${() => this.close()} style="margin-left: auto;">${this.t('call_link.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit}>${this.t('call_link.action_save')}</platform-button>
            </div>
        `;
    }

    override async _onSubmit(): Promise<void> {
        if (!this.linkToken) return;
        const body: Record<string, unknown> = { link_token: this.linkToken, title: this._title.trim() };
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

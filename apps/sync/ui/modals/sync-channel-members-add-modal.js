/**
 * sync-channel-members-add-modal — добавить участника в канал.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

export class SyncChannelMembersAddModal extends PlatformFormModal {
    static modalKind = 'sync.channel_members_add';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _selected: { state: true },
        _query: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .members {
                max-height: 320px;
                overflow-y: auto;
                margin-top: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.channelId = '';
        this._selected = new Set();
        this._query = '';
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._addMember = this.useOp('sync/channel_add_member');
    }

    _toggleMember(userId) {
        const next = new Set(this._selected);
        if (next.has(userId)) next.delete(userId);
        else next.add(userId);
        this._selected = next;
        this.isDirty = true;
    }

    _filteredMembers() {
        if (this._query.length === 0) return this._members.items;
        const q = this._query.toLowerCase();
        return this._members.items.filter((m) => resolveDisplayName(m).toLowerCase().includes(q));
    }

    renderHeader() { return html`<h3>${this.t('channel_members_add.title')}</h3>`; }

    renderBody() {
        const filtered = this._filteredMembers();
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=""
                placeholder=${this.t('channel_members_add.search_placeholder')}
                .value=${this._query}
                @change=${(e) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('sync channel members add: query expects detail.value string');
                    }
                    this._query = e.detail.value;
                }}
            ></platform-field>
            <div class="members">
                ${filtered.map((m) => html`
                    <div
                        class=${this._selected.has(m.user_id) ? 'form-item selected' : 'form-item'}
                        @click=${() => this._toggleMember(m.user_id)}
                    >
                        <div class="form-checkbox">
                            ${this._selected.has(m.user_id) ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                        </div>
                        <div class="form-item-content">
                            <platform-user-chip user-id=${m.user_id} size="sm" ?interactive=${false}></platform-user-chip>
                        </div>
                    </div>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('channel_members_add.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._selected.size === 0}>
                    ${this.t('channel_members_add.action_add', { count: this._selected.size })}
                </platform-button>
            </div>
        `;
    }

    _onSubmit() {
        if (!this.channelId || this._selected.size === 0) return;
        for (const userId of this._selected) {
            this._addMember.run({ channel_id: this.channelId, user_id: userId, role: 'member' });
        }
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-members-add-modal', SyncChannelMembersAddModal);
registerModalKind(SyncChannelMembersAddModal.modalKind, 'sync-channel-members-add-modal');

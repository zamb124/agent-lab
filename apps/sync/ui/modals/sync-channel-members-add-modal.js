/**
 * sync-channel-members-add-modal — добавить участника в канал.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveDisplayName } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-user-chip.js';

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
            input { padding: var(--space-2); border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-solid); color: var(--text-primary); width: 100%; margin-bottom: var(--space-2); }
            .members { max-height: 300px; overflow-y: auto; }
            .member { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2); cursor: pointer; border-radius: var(--radius-sm); }
            .member:hover { background: var(--glass-hover); }
            .member.selected { background: var(--glass-active, var(--accent)); color: white; }
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
        this.markDirty();
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
            <input
                type="text"
                placeholder=${this.t('channel_members_add.search_placeholder')}
                .value=${this._query}
                @input=${(e) => { this._query = e.target.value; }}
            />
            <div class="members">
                ${filtered.map((m) => html`
                    <div
                        class=${this._selected.has(m.user_id) ? 'member selected' : 'member'}
                        @click=${() => this._toggleMember(m.user_id)}
                    >
                        <platform-user-chip user-id=${m.user_id} size="sm" ?interactive=${false}></platform-user-chip>
                    </div>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('channel_members_add.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._selected.size === 0}>
                ${this.t('channel_members_add.action_add', { count: this._selected.size })}
            </platform-button>
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

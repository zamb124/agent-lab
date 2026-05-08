/**
 * sync-forward-modal — выбор каналов для пересылки сообщения(й).
 *
 * Открывается через chat_ui.openForward({ message }) или openModal напрямую.
 * Список — все каналы, кроме исключаемого. Подтверждение —
 * useOp('sync/messages_forward').run для каждой пары (target, message).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import './../components/sync-channel-row.js';
import '@platform/lib/components/fields/platform-field.js';

export class SyncForwardModal extends PlatformModal {
    static modalKind = 'sync.forward';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformModal.properties,
        message: { type: Object },
        _selectedIds: { state: true },
        _query: { state: true },
    };

    static styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        formStyles,
        css`
            .list {
                max-height: 360px;
                overflow-y: auto;
                margin-top: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .empty {
                padding: var(--space-3);
                color: var(--text-tertiary);
                text-align: center;
                font-size: var(--text-sm);
            }
            .form-item-content {
                flex: 1;
                min-width: 0;
            }
            .form-actions {
                flex-wrap: wrap;
            }
        `,
    ];

    constructor() {
        super();
        this.message = null;
        this._selectedIds = [];
        this._query = '';
        this._channels = this.useResource('sync/channels');
        this._forward = this.useOp('sync/messages_forward');
        this._chatUi = this.useSlice('sync/chat_ui');
    }

    _excludeId() {
        if (!this.message || typeof this.message !== 'object') return '';
        if (typeof this.message.channel_id === 'string') return this.message.channel_id;
        return '';
    }

    _filteredChannels() {
        const exclude = this._excludeId();
        const q = this._query.trim().toLowerCase();
        return this._channels.items.filter((c) => {
            if (c.id === exclude) return false;
            if (q !== '') {
                const title = typeof c.name === 'string' ? c.name.toLowerCase() : '';
                const peer = c.peer && typeof c.peer.display_name === 'string' ? c.peer.display_name.toLowerCase() : '';
                if (!title.includes(q) && !peer.includes(q)) return false;
            }
            return true;
        });
    }

    _toggle(id) {
        if (this._selectedIds.includes(id)) {
            this._selectedIds = this._selectedIds.filter((x) => x !== id);
        } else {
            this._selectedIds = [...this._selectedIds, id];
        }
    }

    async _onConfirm() {
        if (!this.message || this._selectedIds.length === 0) return;
        const messageIds = Array.isArray(this.message.batch_message_ids)
            ? this.message.batch_message_ids
            : (typeof this.message.message_id === 'string' ? [this.message.message_id] : []);
        const sourceChannelId = this._excludeId();
        for (const targetChannelId of this._selectedIds) {
            for (const messageId of messageIds) {
                this._forward.run({
                    from_channel_id: sourceChannelId,
                    message_id: messageId,
                    to_channel_id: targetChannelId,
                });
            }
        }
        this._chatUi.closeForward(null);
        this.close();
    }

    renderHeader() {
        return html`<h3>${this.t('chat_view.forward_modal_title')}</h3>`;
    }

    renderBody() {
        const channels = this._filteredChannels();
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=""
                placeholder=${this.t('sidebar.direct_search_placeholder')}
                .value=${this._query}
                @change=${(e) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('sync forward: query expects detail.value string');
                    }
                    this._query = e.detail.value;
                }}
            ></platform-field>
            ${channels.length === 0
                ? html`<div class="empty">${this.t('chat_view.no_other_channels')}</div>`
                : html`<div class="list">
                    ${channels.map((c) => html`
                        <div
                            class=${this._selectedIds.includes(c.id) ? 'form-item selected' : 'form-item'}
                            @click=${() => this._toggle(c.id)}
                        >
                            <div class="form-checkbox">
                                ${this._selectedIds.includes(c.id) ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                            </div>
                            <div class="form-item-content">
                                <sync-channel-row pick-mode .channel=${c}></sync-channel-row>
                            </div>
                        </div>
                    `)}
                </div>`}
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('chat_view.cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onConfirm} ?disabled=${this._selectedIds.length === 0}>
                    ${this.t('chat_view.forward')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('sync-forward-modal', SyncForwardModal);
registerModalKind(SyncForwardModal.modalKind, 'sync-forward-modal');

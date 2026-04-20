/**
 * sync-selection-bar — отображается при chat_ui.selectionMode === true.
 *
 * Источник: useSlice('sync/chat_ui') (selectionMode + selectedMessageIds).
 * Действия: forward (открывает sync.forward), delete (массово useOp('sync/messages').remove),
 * cancel (clearSelection).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class SyncSelectionBar extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            display: block;
            background: var(--glass-solid);
            border-bottom: 1px solid var(--glass-border);
        }
        .row {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2) var(--space-3);
        }
        .count {
            flex: 1;
            font-size: var(--text-sm);
            font-weight: 500;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            padding: var(--space-1) var(--space-2);
            background: transparent;
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-sm);
            color: var(--text-primary);
            cursor: pointer;
            font-size: var(--text-sm);
        }
        .btn:hover { background: var(--glass-hover); }
        .btn.danger { color: var(--error, #ef4444); border-color: var(--error, #ef4444); }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._chatUi = this.useSlice('sync/chat_ui');
        this._messages = this.useOp('sync/messages');
    }

    _onCancel() {
        this._chatUi.clearSelection(null);
    }

    _onForward() {
        const ids = this._chatUi.value.selectedMessageIds;
        if (!Array.isArray(ids) || ids.length === 0) return;
        this._chatUi.openForward({ message: { batch_message_ids: ids, channel_id: this.channelId } });
    }

    _onDelete() {
        const ids = this._chatUi.value.selectedMessageIds;
        if (!Array.isArray(ids) || ids.length === 0) return;
        this._chatUi.startDeletion({ messageIds: ids });
        for (const messageId of ids) {
            this._messages.remove({ channel_id: this.channelId, message_id: messageId });
        }
        this._chatUi.clearSelection(null);
    }

    render() {
        const slice = this._chatUi.value;
        if (!slice || slice.selectionMode !== true) return html``;
        const count = Array.isArray(slice.selectedMessageIds) ? slice.selectedMessageIds.length : 0;
        return html`
            <div class="row">
                <div class="count">${this.t('chat_view.selected_count', { count })}</div>
                <button class="btn" @click=${this._onForward} ?disabled=${count === 0}>
                    <platform-icon name="forward" size="14"></platform-icon>
                    ${this.t('chat_view.forward')}
                </button>
                <button class="btn danger" @click=${this._onDelete} ?disabled=${count === 0}>
                    <platform-icon name="trash" size="14"></platform-icon>
                    ${this.t('chat_view.delete')}
                </button>
                <button class="btn" @click=${this._onCancel}>${this.t('chat_view.cancel')}</button>
            </div>
        `;
    }
}

customElements.define('sync-selection-bar', SyncSelectionBar);

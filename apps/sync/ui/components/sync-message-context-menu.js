/**
 * sync-message-context-menu — ПКМ / long-press меню сообщения.
 *
 * Источник состояния: slice 'syncMessages.contextMenuTarget' (фабрика
 * заполняется при dispatch 'sync/messages/context_menu_requested', очищается
 * 'sync/messages/context_menu_dismissed'). Всплытие вне меню/Esc → dismiss.
 *
 * Действия:
 *   - reply  → 'sync/messages/reply_mode_set' { messageId }
 *   - edit   → 'sync/messages/edit_mode_set' { messageId } (только своё)
 *   - delete → useOp('sync/messages').actions.remove(...)
 *   - react  → встроенный picker эмодзи
 *   - copy   → this.copyToClipboard(text, ...)
 *   - pin    → useOp('sync/messages').actions.pin(...)
 *   - thread → useResource('sync/threads').create(...)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const QUICK_REACTIONS = ['👍', '❤️', '😄', '🎉', '🤔', '👀'];

export class SyncMessageContextMenu extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            position: fixed;
            display: none;
            z-index: 1000;
        }
        :host([open]) { display: block; }
        .menu {
            background: var(--glass-solid);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius-md);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            min-width: 180px;
            padding: var(--space-1) 0;
        }
        .item {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-2) var(--space-3);
            cursor: pointer;
            font-size: var(--text-sm);
            color: var(--text-primary);
        }
        .item:hover { background: var(--glass-hover); }
        .item.danger { color: var(--color-danger, #ff6b6b); }
        .reactions {
            display: flex;
            gap: var(--space-1);
            padding: var(--space-2);
            border-bottom: 1px solid var(--glass-border);
        }
        .reactions span {
            cursor: pointer;
            font-size: var(--text-base);
            padding: 4px;
            border-radius: var(--radius-sm);
        }
        .reactions span:hover { background: var(--glass-hover); }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._messages = this.useOp('sync/messages');
        this._threads = this.useResource('sync/threads');
        this._messagesSel = this.select((s) => s.syncMessages);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._boundOnDocClick = (e) => this._onDocumentClick(e);
        this._boundOnKey = (e) => this._onKey(e);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._boundOnDocClick, true);
        document.addEventListener('keydown', this._boundOnKey);
    }

    disconnectedCallback() {
        document.removeEventListener('pointerdown', this._boundOnDocClick, true);
        document.removeEventListener('keydown', this._boundOnKey);
        super.disconnectedCallback();
    }

    _currentTarget() {
        const slice = this._messagesSel.value;
        return slice && slice.contextMenuTarget;
    }

    _currentMessage() {
        const target = this._currentTarget();
        if (!target) return null;
        const slice = this._messagesSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m) => m.message_id === target.messageId);
        return found ? found : null;
    }

    _dismiss() {
        this.dispatch('sync/messages/context_menu_dismissed', null);
    }

    _onDocumentClick(e) {
        if (!this.hasAttribute('open')) return;
        const path = e.composedPath();
        if (path.includes(this)) return;
        this._dismiss();
    }

    _onKey(e) {
        if (e.key === 'Escape' && this.hasAttribute('open')) this._dismiss();
    }

    _onReply() {
        const t = this._currentTarget();
        if (!t) return;
        this.dispatch('sync/messages/reply_mode_set', { messageId: t.messageId });
        this._dismiss();
    }

    _onEdit() {
        const t = this._currentTarget();
        if (!t) return;
        this.dispatch('sync/messages/edit_mode_set', { messageId: t.messageId });
        this._dismiss();
    }

    _onDelete() {
        const t = this._currentTarget();
        if (!t) return;
        this._messages.actions.remove({
            channel_id: this.channelId,
            message_id: t.messageId,
        });
        this._dismiss();
    }

    _onReact(emoji) {
        const t = this._currentTarget();
        if (!t) return;
        this._messages.actions.react({
            channel_id: this.channelId,
            message_id: t.messageId,
            emoji,
        });
        this._dismiss();
    }

    _onPin() {
        const t = this._currentTarget();
        if (!t) return;
        this._messages.actions.pin({
            channel_id: this.channelId,
            message_id: t.messageId,
            action: 'add',
        });
        this._dismiss();
    }

    _onCopy() {
        const m = this._currentMessage();
        if (!m || !Array.isArray(m.contents)) return;
        const textBlock = m.contents.find((c) => c.type === 'text/plain');
        const text = textBlock && textBlock.data && textBlock.data.text;
        if (typeof text !== 'string' || text.length === 0) {
            this._dismiss();
            return;
        }
        this.copyToClipboard(text, {
            success_i18n_key: 'sync:context_menu.toast_copied',
            error_i18n_key:   'sync:context_menu.toast_copy_failed',
        });
        this._dismiss();
    }

    _onOpenThread() {
        const t = this._currentTarget();
        if (!t) return;
        const message = this._currentMessage();
        if (message && message.thread_id) {
            this.dispatch('sync/threads/open_requested', { threadId: message.thread_id });
        } else {
            this._threads.create({
                channel_id: this.channelId,
                root_message_id: t.messageId,
            });
        }
        this._dismiss();
    }

    updated() {
        const target = this._currentTarget();
        if (target) {
            this.setAttribute('open', '');
            this.style.left = `${target.x}px`;
            this.style.top  = `${target.y}px`;
        } else {
            this.removeAttribute('open');
        }
    }

    render() {
        const target = this._currentTarget();
        if (!target) return html``;
        const message = this._currentMessage();
        const me = this._authSel.value;
        const myId = (me && typeof me.user_id === 'string') ? me.user_id : '';
        const isOwn = Boolean(message && message.sender && message.sender.user_id === myId);
        const hasText = Boolean(
            message && Array.isArray(message.contents) && message.contents.some((c) => c.type === 'text/plain')
        );
        return html`
            <div class="menu">
                <div class="reactions">
                    ${QUICK_REACTIONS.map((emoji) => html`
                        <span @click=${() => this._onReact(emoji)}>${emoji}</span>
                    `)}
                </div>
                <div class="item" @click=${this._onReply}>
                    <platform-icon name="reply" size="14"></platform-icon>
                    ${this.t('context_menu.action_reply')}
                </div>
                <div class="item" @click=${this._onOpenThread}>
                    <platform-icon name="message-square" size="14"></platform-icon>
                    ${this.t('context_menu.action_open_thread')}
                </div>
                ${isOwn && hasText ? html`
                    <div class="item" @click=${this._onEdit}>
                        <platform-icon name="edit" size="14"></platform-icon>
                        ${this.t('context_menu.action_edit')}
                    </div>
                ` : ''}
                ${hasText ? html`
                    <div class="item" @click=${this._onCopy}>
                        <platform-icon name="copy" size="14"></platform-icon>
                        ${this.t('context_menu.action_copy')}
                    </div>
                ` : ''}
                <div class="item" @click=${this._onPin}>
                    <platform-icon name="pin" size="14"></platform-icon>
                    ${this.t('context_menu.action_pin')}
                </div>
                ${isOwn ? html`
                    <div class="item danger" @click=${this._onDelete}>
                        <platform-icon name="trash" size="14"></platform-icon>
                        ${this.t('context_menu.action_delete')}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('sync-message-context-menu', SyncMessageContextMenu);

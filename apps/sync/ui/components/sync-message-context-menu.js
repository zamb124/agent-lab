/**
 * sync-message-context-menu — ПКМ / long-press меню сообщения.
 *
 * Источник состояния: slice 'syncMessagesStore.contextMenuTarget'
 * (фабрика заполняется через action `showContextMenu` slice'а
 * `sync/messages_store`, очищается `dismissContextMenu`). Всплытие вне
 * меню/Esc → dismiss.
 *
 * Действия:
 *   - reply  → action `setReplyMode` slice'а `sync/messages_store`
 *   - edit   → action `setEditMode` slice'а `sync/messages_store` (только своё)
 *   - delete → useOp('sync/messages_delete').run(...)
 *   - react  → useOp('sync/messages_react').run(...)
 *   - copy   → this.copyToClipboard(text, ...)
 *   - pin    → useOp('sync/messages_pin').run(...)
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
            top: 0;
            left: 0;
        }
        :host([open]) { display: block; }
        .menu {
            background: var(--glass-solid-strong);
            border: 1px solid var(--glass-border-subtle, var(--glass-border));
            border-radius: var(--radius-xl, 16px);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.18);
            min-width: 200px;
            max-width: 280px;
            padding: var(--space-1) 0;
            overflow: hidden;
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
        .item:hover { background: var(--glass-tint-medium); }
        .item.danger { color: var(--color-error, #ef4444); }
        .reactions {
            display: flex;
            flex-wrap: nowrap;
            gap: var(--space-1);
            padding: var(--space-2) var(--space-3);
            border-bottom: 1px solid var(--glass-border-subtle, var(--glass-border));
        }
        .reactions span {
            cursor: pointer;
            font-size: var(--text-lg, 18px);
            padding: 4px;
            border-radius: var(--radius-sm);
            line-height: 1;
        }
        .reactions span:hover { background: var(--glass-tint-medium); }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._messagesStore = this.useSlice('sync/messages_store');
        this._delete = this.useOp('sync/messages_delete');
        this._react = this.useOp('sync/messages_react');
        this._pin = this.useOp('sync/messages_pin');
        this._threads = this.useResource('sync/threads');
        this._messagesStoreSel = this.select((s) => s.syncMessagesStore);
        this._authSel = this.select((s) => s.auth && s.auth.user);
        this._boundOnDocClick = (e) => this._onDocumentClick(e);
        this._boundOnKey = (e) => this._onKey(e);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._boundOnDocClick, true);
        document.addEventListener('keydown', this._boundOnKey);
        // Перенос хоста в body: гарантирует, что position: fixed работает
        // от viewport, без containing-block эффектов от ancestor с
        // backdrop-filter / will-change / transform / contain — свойства предков,
        if (this.parentNode !== document.body) {
            document.body.appendChild(this);
        }
    }

    disconnectedCallback() {
        document.removeEventListener('pointerdown', this._boundOnDocClick, true);
        document.removeEventListener('keydown', this._boundOnKey);
        super.disconnectedCallback();
    }

    _currentTarget() {
        const slice = this._messagesStoreSel.value;
        return slice && slice.contextMenuTarget;
    }

    _currentMessage() {
        const target = this._currentTarget();
        if (!target) return null;
        const slice = this._messagesStoreSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m) => m.message_id === target.messageId);
        return found ? found : null;
    }

    _dismiss() {
        this._messagesStore.dismissContextMenu(null);
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
        this._messagesStore.setReplyMode({ messageId: t.messageId });
        this._dismiss();
    }

    _onEdit() {
        const t = this._currentTarget();
        if (!t) return;
        this._messagesStore.setEditMode({ messageId: t.messageId });
        this._dismiss();
    }

    _onDelete() {
        const t = this._currentTarget();
        if (!t) return;
        this._delete.run({
            channel_id: this.channelId,
            message_id: t.messageId,
        });
        this._dismiss();
    }

    _onReact(emoji) {
        const t = this._currentTarget();
        if (!t) return;
        this._react.run({
            channel_id: this.channelId,
            message_id: t.messageId,
            emoji,
        });
        this._dismiss();
    }

    _onPin() {
        const t = this._currentTarget();
        if (!t) return;
        this._pin.run({
            channel_id: this.channelId,
            message_id: t.messageId,
            action: 'add',
        });
        this._dismiss();
    }

    _onForward() {
        const t = this._currentTarget();
        if (!t) return;
        this.openModal('sync.forward', {
            message: { channel_id: this.channelId, message_id: t.messageId },
        });
        this._dismiss();
    }

    _onCopy() {
        const m = this._currentMessage();
        if (!m || !Array.isArray(m.contents)) return;
        const textBlock = m.contents.find((c) => c.type === 'text/plain');
        const data = textBlock && textBlock.data;
        const text = data && (typeof data.body === 'string' ? data.body : (typeof data.text === 'string' ? data.text : ''));
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
                body: { root_message_id: t.messageId },
            });
        }
        this._dismiss();
    }

    updated() {
        const target = this._currentTarget();
        if (target) {
            this.setAttribute('open', '');
            const requestedX = typeof target.x === 'number' ? target.x : 0;
            const requestedY = typeof target.y === 'number' ? target.y : 0;
            this.style.left = `${requestedX}px`;
            this.style.top = `${requestedY}px`;
            requestAnimationFrame(() => {
                if (!this.hasAttribute('open')) return;
                const rect = this.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const margin = 8;
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                let x = requestedX;
                let y = requestedY;
                if (x + rect.width > vw - margin) x = Math.max(margin, vw - rect.width - margin);
                if (y + rect.height > vh - margin) y = Math.max(margin, vh - rect.height - margin);
                if (x < margin) x = margin;
                if (y < margin) y = margin;
                this.style.left = `${x}px`;
                this.style.top = `${y}px`;
            });
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
                <div class="item" @click=${this._onForward}>
                    <platform-icon name="forward" size="14"></platform-icon>
                    ${this.t('context_menu.forward')}
                </div>
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

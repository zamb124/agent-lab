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

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-popover.js';

const QUICK_REACTIONS = ['👍', '❤️', '😄', '🎉', '🤔', '👀'];

export class SyncMessageContextMenu extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host { display: contents; }
        .menu {
            min-width: 200px;
            max-width: 280px;
        }
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
    }

    _currentTarget() {
        const slice = this._messagesStoreSel.value;
        return slice && slice.contextMenuTarget;
    }

    _resolveChannelId() {
        const target = this._currentTarget();
        if (target && typeof target.channelId === 'string' && target.channelId !== '') {
            return target.channelId;
        }
        if (typeof this.channelId === 'string' && this.channelId !== '') {
            return this.channelId;
        }
        return '';
    }

    _currentMessage() {
        const target = this._currentTarget();
        if (!target) return null;
        const slice = this._messagesStoreSel.value;
        if (!slice || !slice.byChannelId || typeof slice.byChannelId !== 'object') {
            return null;
        }
        const channelId = this._resolveChannelId();
        if (channelId === '') return null;
        const channelData = slice.byChannelId[channelId];
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m) => m.message_id === target.messageId);
        if (found) return found;
        const pendingMap = channelData.pendingByLocalId;
        if (pendingMap && typeof pendingMap === 'object' && pendingMap[target.messageId]) {
            return pendingMap[target.messageId];
        }
        return null;
    }

    _dismiss() {
        this._messagesStore.dismissContextMenu(null);
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
        const channelId = this._resolveChannelId();
        if (channelId === '') return;
        this._delete.run({
            channel_id: channelId,
            message_id: t.messageId,
        });
        this._dismiss();
    }

    _onReact(emoji) {
        const t = this._currentTarget();
        if (!t) return;
        const channelId = this._resolveChannelId();
        if (channelId === '') return;
        this._react.run({
            channel_id: channelId,
            message_id: t.messageId,
            emoji,
        });
        this._dismiss();
    }

    _onPin() {
        const t = this._currentTarget();
        if (!t) return;
        const channelId = this._resolveChannelId();
        if (channelId === '') return;
        this._pin.run({
            channel_id: channelId,
            message_id: t.messageId,
            action: 'add',
        });
        this._dismiss();
    }

    _onForward() {
        const t = this._currentTarget();
        if (!t) return;
        const channelId = this._resolveChannelId();
        if (channelId === '') return;
        this.openModal('sync.forward', {
            message: { channel_id: channelId, message_id: t.messageId },
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

    _actionItems(isOwn, hasText) {
        const items = [
            { id: 'reply', label: this.t('context_menu.action_reply'), icon: 'reply' },
            { id: 'thread', label: this.t('context_menu.action_open_thread'), icon: 'message-square' },
        ];
        if (isOwn && hasText) {
            items.push({ id: 'edit', label: this.t('context_menu.action_edit'), icon: 'edit' });
        }
        if (hasText) {
            items.push({ id: 'copy', label: this.t('context_menu.action_copy'), icon: 'copy' });
        }
        items.push(
            { id: 'forward', label: this.t('context_menu.forward'), icon: 'forward' },
            { id: 'pin', label: this.t('context_menu.action_pin'), icon: 'pin' },
        );
        if (isOwn) {
            items.push({
                id: 'delete',
                label: this.t('context_menu.action_delete'),
                icon: 'trash',
                danger: true,
            });
        }
        return items;
    }

    _onActionSelect(event) {
        const handlers = {
            reply: () => this._onReply(),
            thread: () => this._onOpenThread(),
            edit: () => this._onEdit(),
            copy: () => this._onCopy(),
            forward: () => this._onForward(),
            pin: () => this._onPin(),
            delete: () => this._onDelete(),
        };
        const handler = handlers[event.detail.id];
        if (handler === undefined) {
            throw new Error(`sync-message-context-menu: неизвестное действие ${event.detail.id}`);
        }
        handler();
    }

    render() {
        const target = this._currentTarget();
        if (!target) return nothing;
        const message = this._currentMessage();
        const me = this._authSel.value;
        const myId = (me && typeof me.user_id === 'string') ? me.user_id : '';
        const isOwn = Boolean(message && message.sender && message.sender.user_id === myId);
        const hasText = Boolean(
            message && Array.isArray(message.contents) && message.contents.some((c) => c.type === 'text/plain')
        );
        const anchor = {
            x: typeof target.x === 'number' ? target.x : 0,
            y: typeof target.y === 'number' ? target.y : 0,
        };
        return html`
            <platform-popover
                trigger="manual"
                role="menu"
                placement="bottom-start"
                offset="2"
                .anchor=${anchor}
                open
                @popover-dismiss=${() => this._dismiss()}
            >
            <div class="menu">
                <div class="reactions">
                    ${QUICK_REACTIONS.map((emoji) => html`
                        <span @click=${() => this._onReact(emoji)}>${emoji}</span>
                    `)}
                </div>
                <platform-menu
                    compact
                    .items=${this._actionItems(isOwn, hasText)}
                    @menu-select=${this._onActionSelect}
                ></platform-menu>
            </div>
            </platform-popover>
        `;
    }
}

customElements.define('sync-message-context-menu', SyncMessageContextMenu);

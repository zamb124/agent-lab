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

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import { html, css, nothing } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-popover.js';

const QUICK_REACTIONS = ['👍', '❤️', '😄', '🎉', '🤔', '👀'];

function isStoreRecord(value: unknown): value is Record<string, unknown> {
    return isPlainRecord(value);
}

export class SyncMessageContextMenu extends PlatformElement {
    static override properties: PropertyDeclarations = {
        channelId: { type: String },
    };
    declare channelId: string;

    static override styles: CSSResultGroup = css`
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
            border-bottom: 1px solid var(--glass-border-subtle);
        }
        .reactions span {
            cursor: pointer;
            font-size: var(--text-lg);
            padding: 4px;
            border-radius: var(--radius-sm);
            line-height: 1;
        }
        .reactions span:hover { background: var(--glass-tint-medium); }
    `;
    private _messagesStore: ControllerFor<'sync/messages_store'>;
    private _delete: OpController;
    private _react: OpController;
    private _pin: OpController;
    private _threads: ControllerFor<'sync/threads'>;
    private _messagesStoreSel: SelectController<Record<string, unknown> | undefined>;
    private _authSel: SelectController<AuthUser | null>;

    constructor() {
        super();
        this.channelId = '';
        this._messagesStore = this.useSlice('sync/messages_store');
        this._delete = this.useOp('sync/messages_delete');
        this._react = this.useOp('sync/messages_react');
        this._pin = this.useOp('sync/messages_pin');
        this._threads = this.useResource('sync/threads');
        this._messagesStoreSel = this.select((s) => isStoreRecord(s.syncMessagesStore) ? s.syncMessagesStore : undefined);
        this._authSel = this.select((s) => s.auth.user);
    }

    _currentTarget(): Record<string, unknown> | null {
        const slice = this._messagesStoreSel.value;
        const t = slice && slice.contextMenuTarget;
        return isStoreRecord(t) ? t : null;
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

    _currentMessage(): Record<string, unknown> | null {
        const target = this._currentTarget();
        if (!target) return null;
        const slice = this._messagesStoreSel.value;
        if (!slice || !isPlainRecord(slice.byChannelId)) {
            return null;
        }
        const channelId = this._resolveChannelId();
        if (channelId === '') return null;
        const channelData = isPlainRecord(slice.byChannelId[channelId]) ? slice.byChannelId[channelId] : null;
        if (!channelData || !Array.isArray(channelData.items)) return null;
        const found = channelData.items.find((m: Record<string, unknown>) => m.message_id === target.messageId);
        if (found) return found;
        const pendingMap = channelData.pendingByLocalId;
        const pendingMessageId = typeof target.messageId === 'string' ? target.messageId : '';
        const pending = isPlainRecord(pendingMap) ? pendingMap[pendingMessageId] : null;
        return isPlainRecord(pending) ? pending : null;
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

    _onReact(emoji: unknown) {
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

    _actionItems(isOwn: boolean, hasText: boolean) {
        const items: Array<{ id: string; label: string; icon: string; danger?: boolean }> = [
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

    _onActionSelect(event: Event) {
        if (!(event instanceof CustomEvent)) {
            throw new Error('sync-message-context-menu: action event required');
        }
        const detail = isStoreRecord(event.detail) ? event.detail : null;
        const actionId = detail === null || typeof detail.id !== 'string' ? '' : detail.id;
        if (actionId === 'reply') return this._onReply();
        if (actionId === 'thread') return this._onOpenThread();
        if (actionId === 'edit') return this._onEdit();
        if (actionId === 'copy') return this._onCopy();
        if (actionId === 'forward') return this._onForward();
        if (actionId === 'pin') return this._onPin();
        if (actionId === 'delete') return this._onDelete();
        throw new Error(`sync-message-context-menu: неизвестное действие ${actionId}`);
    }

    override render(): TemplateResult | typeof nothing {
        const target = this._currentTarget();
        if (!target) return nothing;
        const message = this._currentMessage();
        const me = this._authSel.value;
        const userId = me === null ? undefined : me.user_id;
        const myId = typeof userId === 'string' ? userId : '';
        const sender = message === null ? null : message.sender;
        const isOwn = isStoreRecord(sender) && sender.user_id === myId;
        const contents = message === null ? undefined : message.contents;
        const hasText = Array.isArray(contents) && contents.some((part) => isStoreRecord(part) && part.type === 'text/plain');
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

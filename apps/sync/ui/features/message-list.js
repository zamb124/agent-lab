/**
 * MessageList — список сообщений с автоскроллом вниз и фильтрацией по треду
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { SyncStore } from '../store/sync.store.js';
import { senderUserId } from '../utils/sender.js';
import './message-bubble.js';

function startOfLocalDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function localDayKey(iso) {
    const t = new Date(iso);
    if (Number.isNaN(t.getTime())) return '';
    return `${t.getFullYear()}-${t.getMonth()}-${t.getDate()}`;
}

function formatDayDividerLabel(iso) {
    const msgDate = new Date(iso);
    if (Number.isNaN(msgDate.getTime())) return '';
    const msgStart = startOfLocalDay(msgDate);
    const todayStart = startOfLocalDay(new Date());
    const diffDays = Math.round((todayStart - msgStart) / 86400000);
    if (diffDays === 0) return 'Сегодня';
    if (diffDays === 1) return 'Вчера';
    return msgDate.toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });
}

function buildListItems(messages) {
    const items = [];
    let prevDayKey = null;
    for (const msg of messages) {
        const key = localDayKey(msg.sent_at);
        if (key !== prevDayKey) {
            prevDayKey = key;
            items.push({ kind: 'day', sentAt: msg.sent_at });
        }
        items.push({ kind: 'msg', msg });
    }
    return items;
}

export class MessageList extends PlatformElement {
    static properties = {
        channelId: { type: String },
        _messages: { state: true },
        _loading: { state: true },
        _focusedThreadId: { state: true },
        _currentUserId: { state: true },
        _selectionMode: { state: true },
        _selectedMessageIds: { state: true },
        _pinnedMessageIds: { state: true },
        _flashMessageId: { state: true },
        _deletingMessageIds: { state: true },
        _peerReadAtByChannel: { state: true },
        _selectedChannelType: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
            }

            .list {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                scroll-behavior: smooth;
            }

            .loading-text {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-4);
                text-align: center;
            }

            .empty-text {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-4);
                text-align: center;
            }

            .day-divider {
                display: flex;
                justify-content: center;
                margin: var(--space-2) 0 var(--space-3);
            }

            .day-divider span {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                padding: 4px 14px;
                border-radius: var(--radius-full);
            }
        `
    ];

    constructor() {
        super();
        this.channelId = null;
        this._messages = [];
        this._loading = false;
        this._focusedThreadId = null;
        this._currentUserId = null;
        this._stickToBottom = true;
        this._listRef = null;
        this._selectionMode = false;
        this._selectedMessageIds = [];
        this._pinnedMessageIds = [];
        this._flashMessageId = null;
        this._flashMessageSeq = 0;
        this._deletingMessageIds = [];
        this._peerReadAtByChannel = {};
        this._selectedChannelType = null;
    }

    _syncChannelMeta(state) {
        const cid = this.channelId;
        if (!cid) {
            this._pinnedMessageIds = [];
            this._selectedChannelType = null;
            return;
        }
        const ch = state.channels.list.find(c => c.id === cid);
        const pins = ch?.pinned_message_ids;
        this._pinnedMessageIds = Array.isArray(pins) ? pins : [];
        this._selectedChannelType = ch?.type ?? null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._loading = state.messages.loading;
            this._focusedThreadId = state.chat.focusedThreadId;
            this._messages = SyncStore.getDisplayMessages();
            this._selectionMode = state.ui.selectionMode;
            this._selectedMessageIds = state.ui.selectedMessageIds;
            this._syncChannelMeta(state);
            this._flashMessageId = state.ui.flashMessageId ?? null;
            this._flashMessageSeq = state.ui.flashMessageSeq ?? 0;
            this._deletingMessageIds = Array.isArray(state.ui.deletingMessageIds)
                ? state.ui.deletingMessageIds
                : [];
            this._peerReadAtByChannel = state.peerReadAtByChannel ?? {};
            this._syncCurrentUserId();
            this._scrollIfSticky();
        });

        this._syncCurrentUserId();
        this._onAuthChange = () => this._syncCurrentUserId();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
    }

    _syncCurrentUserId() {
        const id = ServiceRegistry.auth?.user?.id ?? null;
        if (this._currentUserId !== id) {
            this._currentUserId = id;
        }
    }

    updated() {
        this._scrollIfSticky();
    }

    _onScroll(e) {
        const el = e.target;
        const atBottom = el.scrollHeight - (el.scrollTop + el.clientHeight) <= 40;
        this._stickToBottom = atBottom;
    }

    _scrollIfSticky() {
        if (!this._stickToBottom) return;
        const el = this.shadowRoot?.querySelector('.list');
        if (el) {
            requestAnimationFrame(() => {
                el.scrollTop = el.scrollHeight;
            });
        }
    }

    /**
     * Прокрутка к сообщению по id (якорь для закрепов).
     * @param {string} messageId
     */
    scrollToMessageId(messageId) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error('messageId обязателен.');
        }
        const list = this.shadowRoot?.querySelector('.list');
        if (!list) {
            throw new Error('Список сообщений не готов.');
        }
        const bubble = list.querySelector(`message-bubble[data-msg-id="${CSS.escape(messageId)}"]`);
        if (!bubble) {
            throw new Error(
                `Сообщение ${messageId} не найдено в ленте (возможно не загружено или в другом треде).`
            );
        }
        bubble.scrollIntoView({ block: 'center', behavior: 'smooth' });
        this._stickToBottom = false;
    }

    _onScrollToMessage(e) {
        const id = e.detail?.messageId;
        if (typeof id !== 'string' || id === '') {
            this.error('messageId обязателен.');
            return;
        }
        try {
            this.scrollToMessageId(id);
            SyncStore.flashMessageHighlight(id);
        } catch (err) {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        }
    }

    render() {
        const filtered = this._messages.filter(m => {
            if (this._focusedThreadId === null) return true;
            return m.thread_id === this._focusedThreadId;
        });

        const items = buildListItems(filtered);
        const peerReadAt = this._peerReadAtByChannel[this.channelId] ?? null;

        return html`
            <div class="list" @scroll=${this._onScroll} @scroll-to-message=${this._onScrollToMessage}>
                ${this._loading ? html`<div class="loading-text">Загрузка сообщений...</div>` : ''}
                ${!this._loading && filtered.length === 0 ? html`<div class="empty-text">Сообщений пока нет.</div>` : ''}
                ${items.map((item) => {
                    if (item.kind === 'day') {
                        return html`
                            <div class="day-divider">
                                <span>${formatDayDividerLabel(item.sentAt)}</span>
                            </div>
                        `;
                    }
                    const msg = item.msg;
                    const selected = this._selectedMessageIds.includes(msg.id);
                    const flashActive = this._flashMessageId === msg.id;
                    const flashSeq = flashActive ? this._flashMessageSeq : 0;
                    const deleting = this._deletingMessageIds.includes(msg.id);
                    return html`
                        <message-bubble
                            data-msg-id=${msg.id}
                            .msg=${msg}
                            .channelId=${this.channelId}
                            .pinnedMessageIds=${this._pinnedMessageIds}
                            .selectionMode=${this._selectionMode}
                            .selected=${selected}
                            .deleting=${deleting}
                            .flashActive=${flashActive}
                            .flashSeq=${flashSeq}
                            .isOwn=${this._currentUserId !== null && senderUserId(msg.sender) === this._currentUserId}
                            .peerReadAt=${peerReadAt}
                            .channelType=${this._selectedChannelType}
                            .canFocusThread=${this._focusedThreadId === null && msg.thread_id !== null}
                            @focus-thread=${(e) => SyncStore.setFocusedThread(e.detail.threadId)}
                        ></message-bubble>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('message-list', MessageList);

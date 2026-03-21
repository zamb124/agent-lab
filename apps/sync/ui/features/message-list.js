/**
 * MessageList — список сообщений с автоскроллом вниз и фильтрацией по треду
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import './message-bubble.js';

export class MessageList extends PlatformElement {
    static properties = {
        channelId: { type: String },
        _messages: { state: true },
        _loading: { state: true },
        _focusedThreadId: { state: true },
        _currentUserId: { state: true },
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
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._loading = state.messages.loading;
            this._focusedThreadId = state.chat.focusedThreadId;
            this._messages = SyncStore.getDisplayMessages();
            this._scrollIfSticky();
        });

        this._currentUserId = ServiceRegistry.auth?.user?.id ?? null;
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
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

    render() {
        const filtered = this._messages.filter(m => {
            if (this._focusedThreadId === null) return true;
            return m.thread_id === this._focusedThreadId;
        });

        return html`
            <div class="list" @scroll=${this._onScroll}>
                ${this._loading ? html`<div class="loading-text">Загрузка сообщений...</div>` : ''}
                ${!this._loading && filtered.length === 0 ? html`<div class="empty-text">Сообщений пока нет.</div>` : ''}
                ${filtered.map(msg => html`
                    <message-bubble
                        .msg=${msg}
                        .isOwn=${this._currentUserId !== null && msg.sender?.id === this._currentUserId}
                        .canFocusThread=${this._focusedThreadId === null && msg.thread_id !== null}
                        @focus-thread=${(e) => SyncStore.setFocusedThread(e.detail.threadId)}
                    ></message-bubble>
                `)}
            </div>
        `;
    }
}

customElements.define('message-list', MessageList);

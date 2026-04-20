/**
 * sync-message-list — лента сообщений канала.
 *
 * Источник: slice `sync/messages_store.byChannelId[channelId]`
 * (`select((s) => s.syncMessagesStore)`).
 * Группировка: по дням (sync-day-grouping helper) + по отправителю
 * (window 120s) — `position` прокидывается в каждый bubble.
 *
 * Sticky-bottom: при добавлении новых сообщений лента скроллится вниз,
 * если пользователь не отскроллил вверх вручную.
 *
 * Infinite scroll up: при scrollTop <= 60 → useOp('sync/messages_load_older')
 * + slice action `loadedOlder` для merge в slice. Компенсация scroll.
 *
 * Скрытое API для родителя: scrollToMessageId(id, { flash }) — листает
 * до сообщения, при необходимости подгружает историю циклом, диспатчит
 * `flash` action slice'а.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-spinner.js';
import './sync-message-bubble.js';
import { groupMessagesForRender } from '../_helpers/sync-day-grouping.js';

const SCROLL_TOP_THRESHOLD = 60;

export class SyncMessageList extends PlatformElement {
    static properties = {
        channelId: { type: String },
        myUserId: { type: String, attribute: 'my-user-id' },
        channelType: { type: String, attribute: 'channel-type' },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            position: relative;
        }
        .scroll {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: var(--space-3);
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .day {
            text-align: center;
            margin: var(--space-3) 0 var(--space-1);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            position: relative;
        }
        .day::before, .day::after {
            content: '';
            position: absolute;
            top: 50%;
            width: 35%;
            height: 1px;
            background: var(--glass-border);
        }
        .day::before { left: 0; }
        .day::after  { right: 0; }
        .empty {
            margin: auto;
            color: var(--text-secondary);
            font-size: var(--text-sm);
        }
        .loading-banner {
            text-align: center;
            padding: var(--space-2);
            font-size: var(--text-xs);
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2);
        }
        .skeleton {
            display: flex;
            flex-direction: column;
            gap: var(--space-3);
            padding: var(--space-3);
        }
        .skeleton-row {
            height: 48px;
            background: linear-gradient(90deg, var(--glass-hover) 0%, var(--glass-active, var(--glass-hover)) 50%, var(--glass-hover) 100%);
            background-size: 200% 100%;
            border-radius: var(--radius-md);
            animation: skeleton-shimmer 1.4s ease-in-out infinite;
        }
        .skeleton-row.short { width: 50%; }
        .skeleton-row.own { align-self: flex-end; width: 60%; }
        @keyframes skeleton-shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this.myUserId = '';
        this.channelType = '';
        this._channelMembers = [];
        this._store = this.useSlice('sync/messages_store');
        this._messagesStoreSel = this.select((s) => s.syncMessagesStore);
        this._channelsSel = this.select((s) => s.syncChannels);
        this._loadOlder = this.useOp('sync/messages_load_older');
        this._loadNewer = this.useOp('sync/messages_load_newer');
        this._stickToBottom = true;
        this._lastItemsLength = 0;
        this._scrollEl = null;
        this._observer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('jump-to-message', this._onJumpToMessage);
    }

    disconnectedCallback() {
        this.removeEventListener('jump-to-message', this._onJumpToMessage);
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
        super.disconnectedCallback();
    }

    firstUpdated() {
        this._scrollEl = this.renderRoot.querySelector('.scroll');
        if (!this._scrollEl) return;
        this._scrollEl.addEventListener('scroll', this._onScroll);
        if (typeof ResizeObserver === 'function') {
            this._observer = new ResizeObserver(() => this._maybeStickBottom());
            this._observer.observe(this._scrollEl);
        }
        this._maybeStickBottom();
    }

    _items() {
        const slice = this._messagesStoreSel.value;
        if (!slice || !slice.byChannelId) return [];
        const channelData = slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return [];
        const items = [...channelData.items];
        if (channelData.pendingByLocalId && typeof channelData.pendingByLocalId === 'object') {
            for (const pending of Object.values(channelData.pendingByLocalId)) {
                if (pending && typeof pending === 'object') items.push(pending);
            }
        }
        items.sort((a, b) => {
            const ta = typeof a.sent_at === 'string' ? a.sent_at : '';
            const tb = typeof b.sent_at === 'string' ? b.sent_at : '';
            if (ta < tb) return -1;
            if (ta > tb) return 1;
            return 0;
        });
        return items;
    }

    _channelData() {
        const slice = this._messagesStoreSel.value;
        if (!slice || !slice.byChannelId) return null;
        return slice.byChannelId[this.channelId];
    }

    _onScroll = () => {
        if (!this._scrollEl) return;
        const distanceFromBottom = this._scrollEl.scrollHeight - this._scrollEl.scrollTop - this._scrollEl.clientHeight;
        this._stickToBottom = distanceFromBottom < 80;
        if (this._scrollEl.scrollTop <= SCROLL_TOP_THRESHOLD) {
            this._maybeLoadOlder();
        }
    };

    async _maybeLoadOlder() {
        const channelData = this._channelData();
        if (!channelData) return;
        if (channelData.loadingOlder) return;
        if (!channelData.pagination || channelData.pagination.hasOlder !== true) return;
        const oldestCursor = channelData.pagination.oldestCursor;
        if (typeof oldestCursor !== 'string' || oldestCursor === '') return;
        const prevHeight = this._scrollEl.scrollHeight;
        const prevTop = this._scrollEl.scrollTop;
        this._store.startOlder({ channelId: this.channelId });
        await this._loadOlder.run({
            channel_id: this.channelId,
            limit: 50,
            before: oldestCursor,
            direction: 'older',
        });
        const result = this._loadOlder.lastResult;
        if (!result || !Array.isArray(result.items)) return;
        const hasOlder = typeof result.has_older === 'boolean'
            ? result.has_older
            : (typeof result.prev_cursor === 'string' && result.prev_cursor !== '');
        const oldestCursorNext = typeof result.oldest_cursor === 'string'
            ? result.oldest_cursor
            : (typeof result.prev_cursor === 'string' ? result.prev_cursor : null);
        this._store.loadedOlder({
            channelId: this.channelId,
            items: result.items,
            hasOlder,
            oldestCursor: oldestCursorNext,
        });
        await this.updateComplete;
        const newHeight = this._scrollEl.scrollHeight;
        this._scrollEl.scrollTop = prevTop + (newHeight - prevHeight);
    }

    _maybeStickBottom() {
        if (!this._scrollEl) return;
        if (!this._stickToBottom) return;
        this._scrollEl.scrollTop = this._scrollEl.scrollHeight;
    }

    updated() {
        const items = this._items();
        if (items.length !== this._lastItemsLength) {
            this._lastItemsLength = items.length;
            requestAnimationFrame(() => this._maybeStickBottom());
        }
    }

    _onJumpToMessage = (e) => {
        if (!e.detail || typeof e.detail.messageId !== 'string') return;
        this.scrollToMessageId(e.detail.messageId);
    };

    async scrollToMessageId(messageId) {
        if (typeof messageId !== 'string' || messageId === '') return;
        for (let i = 0; i < 30; i += 1) {
            await this.updateComplete;
            const el = this.renderRoot.querySelector(`sync-message-bubble[data-id="${CSS.escape(messageId)}"]`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                this._store.flash({ messageId });
                window.setTimeout(() => this._store.clearFlash(null), 1800);
                return;
            }
            const channelData = this._channelData();
            if (!channelData || !channelData.pagination || channelData.pagination.hasOlder !== true) return;
            await this._maybeLoadOlder();
        }
    }

    render() {
        const channelData = this._channelData();
        const items = this._items();
        if (!channelData || (channelData.loading && items.length === 0)) {
            return html`
                <div class="skeleton">
                    <div class="skeleton-row"></div>
                    <div class="skeleton-row own"></div>
                    <div class="skeleton-row short"></div>
                    <div class="skeleton-row own"></div>
                </div>
            `;
        }
        if (items.length === 0) {
            return html`<div class="scroll"><div class="empty">${this.t('message_list.empty')}</div></div>`;
        }
        const grouped = groupMessagesForRender(items, (k, v) => this.t(k, v));
        const hasOlder = channelData.pagination && channelData.pagination.hasOlder === true;
        const loadingOlder = channelData.loadingOlder === true;
        return html`
            <div class="scroll">
                ${loadingOlder ? html`<div class="loading-banner"><glass-spinner size="14"></glass-spinner>${this.t('message_list.loading_history')}</div>` : ''}
                ${!hasOlder && items.length > 0 ? '' : ''}
                ${grouped.map((entry) => entry.kind === 'day'
                    ? html`<div class="day" data-day-key=${entry.key}>${entry.label}</div>`
                    : html`<sync-message-bubble
                        .message=${entry.message}
                        my-user-id=${this.myUserId}
                        channel-type=${this.channelType}
                        data-position=${entry.position}
                        data-id=${entry.message.message_id}
                    ></sync-message-bubble>`
                )}
            </div>
        `;
    }
}

customElements.define('sync-message-list', SyncMessageList);

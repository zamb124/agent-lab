/**
 * sync-message-list — лента сообщений канала.
 *
 * Источник: slice `sync/messages_store.byChannelId[channelId]`
 * (`select((s) => s.syncMessagesStore)`).
 * Группировка: по дням (sync-day-grouping helper) + по отправителю
 * (window 120s) — `position` прокидывается в каждый bubble.
 *
 * Прилипание к низу: при добавлении новых сообщений лента скроллится вниз,
 * если пользователь не отскроллил вверх вручную.
 *
 * Бесконечная прокрутка вверх: при scrollTop <= 60 → useOp('sync/messages_load_older')
 * + slice action `loadedOlder` для merge в slice. Компенсация scroll.
 *
 * Скрытое API для родителя: scrollToMessageId(id, { flash }) — листает
 * до сообщения, при необходимости подгружает историю циклом, диспатчит
 * `flash` action slice'а.
 */

import type { SyncChannelsSlice, SyncMessagesStoreSlice } from '../events/sync.types.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import './sync-message-bubble.js';
import { groupMessagesForRender } from '../_helpers/sync-day-grouping.js';

const SCROLL_TOP_THRESHOLD = 60;

function isMessagesStore(value: unknown): value is SyncMessagesStoreSlice {
    return isPlainRecord(value) && isPlainRecord(value.byChannelId);
}

function isChannelsSlice(value: unknown): value is SyncChannelsSlice {
    return isPlainRecord(value) && Array.isArray(value.items);
}

export class SyncMessageList extends PlatformElement {
    static override properties: PropertyDeclarations = {
        channelId: { type: String },
        threadId: { type: String, attribute: 'thread-id' },
        myUserId: { type: String, attribute: 'my-user-id' },
        channelType: { type: String, attribute: 'channel-type' },
    };
    declare channelId: string;
    declare threadId: string;
    declare myUserId: string;
    declare channelType: string;

    static override styles: CSSResultGroup = css`
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
            overscroll-behavior: contain;
            touch-action: pan-y;
            padding: var(--space-6) var(--space-8);
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            align-items: stretch;
            gap: var(--space-3);
            background: var(--bg-primary, var(--glass-solid));
        }
        .scroll > sync-message-bubble {
            flex: 0 0 auto;
            width: 100%;
            height: auto;
        }
        @media (max-width: 767px) {
            .scroll { padding: var(--space-4); }
        }
        .day {
            display: flex;
            justify-content: center;
            margin: var(--space-3) 0;
        }
        .day-pill {
            font-size: var(--text-xs);
            color: var(--text-secondary);
            background: var(--glass-tint-subtle, var(--glass-hover));
            border: 1px solid var(--glass-border);
            padding: 4px 12px;
            border-radius: var(--radius-full, 999px);
            font-weight: var(--font-medium);
        }
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
        .unread-jump {
            position: absolute;
            right: var(--space-6);
            bottom: var(--space-4);
            z-index: 5;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            background: var(--accent);
            color: var(--text-inverse, #fff);
            border: none;
            border-radius: var(--radius-full, 999px);
            font-size: var(--text-sm);
            font-weight: var(--font-semibold);
            cursor: pointer;
            box-shadow: 0 6px 18px var(--accent-subtle, rgba(153, 166, 249, 0.32));
            transition: transform var(--duration-fast), background var(--duration-fast);
        }
        .unread-jump:hover { background: var(--accent-hover, var(--accent)); transform: translateY(-1px); }
        .unread-jump:active { transform: translateY(0); }
    `;
    private _store: ControllerFor<'sync/messages_store'>;
    private _messagesStoreSel: SelectController<SyncMessagesStoreSlice | undefined>;
    private _channelsSel: SelectController<SyncChannelsSlice | undefined>;
    private _members: ResourceController;
    private _loadOlder: OpController;
    private _loadNewer: OpController;
    private _channelMembers: readonly any[];
    private _stickToBottom: boolean;
    private _lastItemsLength: number;
    private _lastItemId: string;
    private _scrollEl: any;
    private _observer: any;

    constructor() {
        super();
        this.channelId = '';
        this.threadId = '';
        this.myUserId = '';
        this.channelType = '';
        this._channelMembers = [];
        this._store = this.useSlice('sync/messages_store');
        this._messagesStoreSel = this.select((s) => {
            const store = s.syncMessagesStore;
            return isMessagesStore(store) ? store : undefined;
        });
        this._channelsSel = this.select((s) => {
            const channels = s.syncChannels;
            return isChannelsSlice(channels) ? channels : undefined;
        });
        this._members = this.useResource('sync/company_members', { autoload: true });
        this._loadOlder = this.useOp('sync/messages_load_older');
        this._loadNewer = this.useOp('sync/messages_load_newer');
        this._stickToBottom = true;
        this._lastItemsLength = 0;
        this._lastItemId = '';
        this._scrollEl = null;
        this._observer = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.addEventListener('jump-to-message', this._onJumpToMessage);
    }

    override disconnectedCallback(): void {
        this.removeEventListener('jump-to-message', this._onJumpToMessage);
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
        super.disconnectedCallback();
    }

    override firstUpdated(changed: PropertyValues<this>): void {
        this._ensureScrollBindings();
    }

    _ensureScrollBindings() {
        const el = this.renderRoot.querySelector('.scroll');
        if (!el) return false;
        if (this._scrollEl === el) return true;
        // Если нашли новый .scroll (например, после skeleton → реальный список),
        // переподписываемся: отвязываемся от старого, привязываемся к новому.
        if (this._scrollEl) {
            this._scrollEl.removeEventListener('scroll', this._onScroll);
        }
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
        this._scrollEl = el;
        this._scrollEl.addEventListener('scroll', this._onScroll);
        if (typeof ResizeObserver === 'function') {
            this._observer = new ResizeObserver(() => this._maybeStickBottom());
            this._observer.observe(this._scrollEl);
        }
        // Сразу к низу — после skeleton мы хотим показать самые свежие сообщения.
        this._scrollEl.scrollTop = this._scrollEl.scrollHeight;
        this._stickToBottom = true;
        return true;
    }

    _items() {
        const slice = this._messagesStoreSel.value;
        if (!slice || !slice.byChannelId) return [];
        const channelData = slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return [];
        const targetThreadId = typeof this.threadId === 'string' ? this.threadId : '';
        const items = channelData.items.filter((item) => {
            const itemThreadId = typeof item.thread_id === 'string' ? item.thread_id : '';
            return targetThreadId ? itemThreadId === targetThreadId : itemThreadId === '';
        });
        if (channelData.pendingByLocalId && typeof channelData.pendingByLocalId === 'object') {
            for (const pending of Object.values(channelData.pendingByLocalId)) {
                if (!pending || typeof pending !== 'object') continue;
                const pendingThreadId = typeof pending.thread_id === 'string' ? pending.thread_id : '';
                if (targetThreadId ? pendingThreadId === targetThreadId : pendingThreadId === '') {
                    items.push(pending);
                }
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
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return;
        const hasOlderValue = result.has_older;
        const prevCursor = result.prev_cursor;
        const oldestCursorValue = result.oldest_cursor;
        const hasOlder = typeof hasOlderValue === 'boolean'
            ? hasOlderValue
            : (typeof prevCursor === 'string' && prevCursor !== '');
        const oldestCursorNext = typeof oldestCursorValue === 'string'
            ? oldestCursorValue
            : (typeof prevCursor === 'string' ? prevCursor : null);
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
        this._scrollEl.scrollTo({ top: this._scrollEl.scrollHeight, behavior: 'smooth' });
    }

    _scrollToBottomSmooth() {
        if (!this._scrollEl) return;
        this._stickToBottom = true;
        this._scrollEl.scrollTo({ top: this._scrollEl.scrollHeight, behavior: 'smooth' });
    }

    _channelUnread() {
        const slice = this._channelsSel.value;
        if (!slice || !Array.isArray(slice.items)) return 0;
        const ch = slice.items.find((c: Record<string, any>) => c && c.channel_id === this.channelId);
        if (!ch) return 0;
        const n = typeof ch.unread_count === 'number' ? ch.unread_count : 0;
        return n > 0 ? n : 0;
    }

    /** Закрепы хранятся на канале (`pinned_message_ids`), не в теле MessageRead. */
    _pinnedIdsSet(): Set<string> {
        const slice = this._channelsSel.value;
        if (!slice || !Array.isArray(slice.items)) return new Set<string>();
        const ch = slice.items.find((c: Record<string, any>) => c && c.channel_id === this.channelId);
        if (!ch || !Array.isArray(ch.pinned_message_ids)) return new Set<string>();
        return new Set<string>((ch.pinned_message_ids as string[]).filter((id) => typeof id === 'string' && id !== ''));
    }

    _messageForBubble(raw: Record<string, any>, pinnedSet: ReadonlySet<string>) {
        const mid = typeof raw.message_id === 'string' ? raw.message_id : '';
        const pinned = mid !== '' && pinnedSet.has(mid);
        return Object.freeze({ ...raw, is_pinned: pinned });
    }

    override updated(changed: PropertyValues<this>): void {
        // Скролл-контейнер может появиться позже первого render'а
        // (skeleton → реальный список). Подвязываемся как только увидим .scroll.
        const bound = this._ensureScrollBindings();
        const items = this._items();
        const lastId = items.length > 0
            ? (() => {
                const last = items[items.length - 1];
                if (typeof last.message_id === 'string' && last.message_id.length > 0) return last.message_id;
                if (typeof last.local_id === 'string' && last.local_id.length > 0) return last.local_id;
                return '';
            })()
            : '';
        const itemsChanged = items.length !== this._lastItemsLength || lastId !== this._lastItemId;
        if (bound && itemsChanged) {
            this._lastItemsLength = items.length;
            this._lastItemId = lastId;
            requestAnimationFrame(() => this._maybeStickBottom());
        }
    }

    _onJumpToMessage = (e: Event) => {
        if (!(e instanceof CustomEvent)) return;
        const detail = e.detail;
        if (!isPlainRecord(detail)) return;
        const messageId = detail.messageId;
        if (typeof messageId !== 'string') return;
        this.scrollToMessageId(messageId);
    };

    async scrollToMessageId(messageId: string) {
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

    override render(): TemplateResult {
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
        const grouped = groupMessagesForRender(items, (k: string) => this.t(k));
        const pinnedSet = this._pinnedIdsSet();
        const hasOlder = channelData.pagination && channelData.pagination.hasOlder === true;
        const loadingOlder = channelData.loadingOlder === true;
        const unread = this._channelUnread();
        const showJump = unread > 0 && !this._stickToBottom;
        return html`
            <div class="scroll">
                ${loadingOlder ? html`<div class="loading-banner"><glass-spinner size="xs"></glass-spinner></div>` : ''}
                ${!hasOlder && items.length > 0 ? '' : ''}
                ${grouped.map((entry) => entry.kind === 'day'
                    ? html`<div class="day" data-day-key=${entry.key}><span class="day-pill">${entry.label}</span></div>`
                    : html`<sync-message-bubble
                        .message=${this._messageForBubble(entry.message, pinnedSet)}
                        .members=${this._members.items}
                        my-user-id=${this.myUserId}
                        channel-type=${this.channelType}
                        data-position=${entry.position}
                        data-id=${entry.message.message_id}
                    ></sync-message-bubble>`
                )}
            </div>
            ${showJump ? html`
                <button
                    class="unread-jump"
                    @click=${this._onUnreadJump}
                    title=${this.t('message_list.unread_jump_title', { count: unread })}
                >
                    <span>${unread}</span>
                    <platform-icon name="arrow-down" size="14"></platform-icon>
                </button>
            ` : ''}
        `;
    }

    _onUnreadJump = () => {
        this._scrollToBottomSmooth();
    };
}

customElements.define('sync-message-list', SyncMessageList);

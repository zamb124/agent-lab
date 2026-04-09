/**
 * MessageList — список сообщений с автоскроллом вниз и фильтрацией по треду
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { SyncStore } from '../store/sync.store.js';
import { senderUserId } from '../utils/sender.js';
import '@platform/lib/components/glass-spinner.js';
import './message-bubble.js';

/** Детерминированный PRNG для набора скелетонов на одну сессию загрузки. */
function mulberry32(seed) {
    return function next() {
        let t = (seed += 0x6d2b79f5);
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

/**
 * Случайно 3–5 строк слева (голубой оттенок) и 3–5 справа (зелёный), разные размеры пузырей.
 * Порядок: по очереди other, own, пока не исчерпаются квоты.
 */
function buildSkeletonPlan(seed) {
    const rnd = mulberry32(seed >>> 0);
    const nLeft = 3 + Math.floor(rnd() * 3);
    const nRight = 3 + Math.floor(rnd() * 3);
    const rows = [];
    let left = nLeft;
    let right = nRight;
    while (left > 0 || right > 0) {
        if (left > 0) {
            rows.push({
                side: 'other',
                widthPct: 50 + Math.floor(rnd() * 36),
                minH: 28 + Math.floor(rnd() * 36),
            });
            left -= 1;
        }
        if (right > 0) {
            rows.push({
                side: 'own',
                widthPct: 48 + Math.floor(rnd() * 38),
                minH: 28 + Math.floor(rnd() * 36),
            });
            right -= 1;
        }
    }
    return rows;
}

function startOfLocalDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function localDayKey(iso) {
    const t = new Date(iso);
    if (Number.isNaN(t.getTime())) return '';
    return `${t.getFullYear()}-${t.getMonth()}-${t.getDate()}`;
}

const GROUP_WINDOW_MS = 2 * 60 * 1000;

function sameGroupSender(a, b) {
    const sa = senderUserId(a.sender);
    const sb = senderUserId(b.sender);
    if (!sa || !sb) return false;
    if (sa !== sb) return false;
    const ta = new Date(a.sent_at).getTime();
    const tb = new Date(b.sent_at).getTime();
    if (Number.isNaN(ta) || Number.isNaN(tb)) return false;
    return Math.abs(tb - ta) < GROUP_WINDOW_MS;
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

    const msgItems = items.filter(it => it.kind === 'msg');
    for (let i = 0; i < msgItems.length; i++) {
        const prev = i > 0 ? msgItems[i - 1].msg : null;
        const cur = msgItems[i].msg;
        const next = i < msgItems.length - 1 ? msgItems[i + 1].msg : null;
        const linkedPrev = prev && sameGroupSender(prev, cur);
        const linkedNext = next && sameGroupSender(cur, next);
        if (linkedPrev && linkedNext) {
            msgItems[i].groupPosition = 'middle';
        } else if (linkedPrev) {
            msgItems[i].groupPosition = 'last';
        } else if (linkedNext) {
            msgItems[i].groupPosition = 'first';
        } else {
            msgItems[i].groupPosition = 'single';
        }
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
        _skeletonPlan: { state: true },
        _hasMoreOlder: { state: true },
        _loadingOlder: { state: true },
        _activeCallOverlay: { state: true },
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

            /*
             * Без smooth: иначе scrollTop = scrollHeight анимируется и при смене scrollHeight
             * (новое сообщение, картинка в пузыре) лента не доезжает до низа.
             */
            .list {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                scroll-behavior: auto;
            }

            .messages-loading-bar {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-2) 0 var(--space-4);
                flex-shrink: 0;
            }

            .messages-loading-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .skeleton-row {
                display: flex;
                align-items: flex-end;
                gap: var(--space-2);
            }

            .skeleton-row.other {
                justify-content: flex-start;
            }

            .skeleton-row.own {
                justify-content: flex-end;
            }

            .skeleton-avatar {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                flex-shrink: 0;
                background-size: 200% 100%;
                animation: skeleton-shimmer 1.35s ease-in-out infinite;
            }

            .skeleton-avatar--other {
                border: 1px solid rgba(56, 189, 248, 0.28);
                background: linear-gradient(
                    90deg,
                    rgba(56, 189, 248, 0.1) 0%,
                    rgba(56, 189, 248, 0.24) 50%,
                    rgba(56, 189, 248, 0.1) 100%
                );
            }

            .skeleton-bubble {
                max-width: min(320px, 88%);
                border-radius: var(--radius-lg);
                background-size: 200% 100%;
                animation: skeleton-shimmer 1.35s ease-in-out infinite;
            }

            .skeleton-bubble--other {
                border: 1px solid rgba(56, 189, 248, 0.32);
                background: linear-gradient(
                    90deg,
                    rgba(56, 189, 248, 0.12) 0%,
                    rgba(56, 189, 248, 0.28) 50%,
                    rgba(56, 189, 248, 0.12) 100%
                );
            }

            .skeleton-bubble--own {
                border: 1px solid rgba(34, 197, 94, 0.32);
                background: linear-gradient(
                    90deg,
                    rgba(34, 197, 94, 0.1) 0%,
                    rgba(34, 197, 94, 0.26) 50%,
                    rgba(34, 197, 94, 0.1) 100%
                );
            }

            @keyframes skeleton-shimmer {
                0% {
                    background-position: 100% 0;
                }
                100% {
                    background-position: -100% 0;
                }
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
        this._skeletonPlan = [];
        this._wasLoading = false;
        this._hasMoreOlder = false;
        this._loadingOlder = false;
        this._activeCallOverlay = null;
        this._lastScrollTop = 0;
        /** @type {ResizeObserver | null} */
        this._listResizeObs = null;
        /** @type {HTMLElement | null} */
        this._listResizeTarget = null;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    _formatDayDividerLabel(iso) {
        const msgDate = new Date(iso);
        if (Number.isNaN(msgDate.getTime())) return '';
        const msgStart = startOfLocalDay(msgDate);
        const todayStart = startOfLocalDay(new Date());
        const diffDays = Math.round((todayStart - msgStart) / 86400000);
        if (diffDays === 0) return this._tp('message_list.today');
        if (diffDays === 1) return this._tp('message_list.yesterday');
        const loc = this.i18n.getCurrentLocale();
        return msgDate.toLocaleDateString(loc === 'ru' ? 'ru-RU' : 'en-US', {
            day: 'numeric',
            month: 'long',
            year: 'numeric',
        });
    }

    _regenerateSkeletonPlan() {
        const seed = (Date.now() ^ (Math.floor(Math.random() * 0x7fffffff) << 16)) >>> 0;
        this._skeletonPlan = buildSkeletonPlan(seed);
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
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._unsubscribe = SyncStore.subscribe(state => {
            const loading = state.messages.loading;
            if (loading && !this._wasLoading) {
                this._regenerateSkeletonPlan();
            }
            if (!loading) {
                this._skeletonPlan = [];
            }
            this._wasLoading = loading;
            this._loading = loading;
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
            if (this.channelId) {
                const history = SyncStore.getMessageHistoryState(this.channelId);
                this._hasMoreOlder = history.hasMoreOlder;
                this._loadingOlder = history.loadingOlder;
            } else {
                this._hasMoreOlder = false;
                this._loadingOlder = false;
            }
            this._activeCallOverlay = state.ui.activeCallOverlay ?? null;
            this._syncCurrentUserId();
            this._scrollIfSticky();
        });

        this._syncCurrentUserId();
        this._onAuthChange = () => this._syncCurrentUserId();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._unsubscribe?.();
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
        this._detachListResizeObserver();
    }

    _syncCurrentUserId() {
        const id = this.auth?.user?.id ?? null;
        if (this._currentUserId !== id) {
            this._currentUserId = id;
        }
    }

    updated(changed) {
        if (changed.has('channelId') && this._loading) {
            this._regenerateSkeletonPlan();
        }
        if (changed.has('channelId')) {
            // При переключении канала всегда стартуем из нижней точки ленты.
            this._stickToBottom = true;
            this._lastScrollTop = 0;
            this._detachListResizeObserver();
        }
        const listEl = this.shadowRoot?.querySelector('.list');
        if (listEl instanceof HTMLElement && listEl !== this._listResizeTarget) {
            this._detachListResizeObserver();
            this._listResizeTarget = listEl;
            this._listResizeObs = new ResizeObserver(() => {
                if (!this._stickToBottom) {
                    return;
                }
                listEl.scrollTop = listEl.scrollHeight;
                this._lastScrollTop = listEl.scrollTop;
            });
            this._listResizeObs.observe(listEl);
        }
        void this.updateComplete.then(() => {
            this._scrollIfSticky();
            requestAnimationFrame(() => {
                this._scrollIfSticky();
                requestAnimationFrame(() => this._scrollIfSticky());
            });
        });
    }

    _detachListResizeObserver() {
        if (this._listResizeObs) {
            this._listResizeObs.disconnect();
            this._listResizeObs = null;
        }
        this._listResizeTarget = null;
    }

    _onScroll(e) {
        const el = e.target;
        const scrolledUp = el.scrollTop < this._lastScrollTop;
        this._lastScrollTop = el.scrollTop;
        const atBottom = el.scrollHeight - (el.scrollTop + el.clientHeight) <= 40;
        if (scrolledUp) {
            // Пользователь явно пошёл в историю: отключаем автоприлипание к низу.
            this._stickToBottom = false;
        } else {
            this._stickToBottom = atBottom;
        }
        if (scrolledUp && el.scrollTop <= 60) {
            void this._loadOlderOnTop(el);
        }
    }

    async _loadOlderOnTop(listEl) {
        if (!this.channelId || this._loading || !this._hasMoreOlder || this._loadingOlder) {
            return;
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            throw new Error(this._tp('message_list.err_sync_api'));
        }
        const prevHeight = listEl.scrollHeight;
        const prevTop = listEl.scrollTop;
        this._stickToBottom = false;
        await SyncStore.loadOlderMessages(syncApi, this.channelId);
        await this.updateComplete;
        const nextHeight = listEl.scrollHeight;
        const delta = nextHeight - prevHeight;
        if (delta > 0) {
            listEl.scrollTop = prevTop + delta;
            this._lastScrollTop = listEl.scrollTop;
        }
    }

    _scrollIfSticky() {
        if (!this._stickToBottom) {
            return;
        }
        const el = this.shadowRoot?.querySelector('.list');
        if (!(el instanceof HTMLElement)) {
            return;
        }
        const apply = () => {
            el.scrollTop = el.scrollHeight;
            this._lastScrollTop = el.scrollTop;
        };
        apply();
        requestAnimationFrame(() => {
            apply();
            requestAnimationFrame(apply);
        });
    }

    /**
     * Прокрутка к сообщению по id (якорь для закрепов).
     * @param {string} messageId
     */
    async scrollToMessageId(messageId) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(this._tp('message_list.err_message_id'));
        }
        const list = this.shadowRoot?.querySelector('.list');
        if (!list) {
            throw new Error(this._tp('message_list.err_list_not_ready'));
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            throw new Error(this._tp('message_list.err_sync_api'));
        }
        let bubble = list.querySelector(`message-bubble[data-msg-id="${CSS.escape(messageId)}"]`);
        let pagesLoaded = 0;
        while (!bubble) {
            if (!this.channelId) {
                throw new Error(this._tp('message_list.err_channel'));
            }
            const history = SyncStore.getMessageHistoryState(this.channelId);
            if (!history.hasMoreOlder) {
                throw new Error(this._tp('message_list.err_message_not_found', { id: messageId }));
            }
            const prevHeight = list.scrollHeight;
            const prevTop = list.scrollTop;
            const older = await SyncStore.loadOlderMessages(syncApi, this.channelId);
            if (!Array.isArray(older) || older.length === 0) {
                throw new Error(this._tp('message_list.err_message_not_found', { id: messageId }));
            }
            pagesLoaded += 1;
            if (pagesLoaded > 300) {
                throw new Error(this._tp('message_list.err_history_limit'));
            }
            await this.updateComplete;
            const nextHeight = list.scrollHeight;
            const delta = nextHeight - prevHeight;
            if (delta > 0) {
                list.scrollTop = prevTop + delta;
            }
            bubble = list.querySelector(`message-bubble[data-msg-id="${CSS.escape(messageId)}"]`);
        }
        bubble.scrollIntoView({ block: 'center', behavior: 'smooth' });
        this._stickToBottom = false;
    }

    async _onScrollToMessage(e) {
        const id = e.detail?.messageId;
        if (typeof id !== 'string' || id === '') {
            this.error(this._tp('message_list.err_message_id'));
            return;
        }
        try {
            await this.scrollToMessageId(id);
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

        if (this._loading) {
            const plan = this._skeletonPlan.length > 0
                ? this._skeletonPlan
                : buildSkeletonPlan(0x9e3779b9);
            return html`
                <div class="list" @scroll=${this._onScroll} @scroll-to-message=${this._onScrollToMessage}>
                    <div class="messages-loading-bar" aria-busy="true" aria-live="polite">
                        <glass-spinner size="md"></glass-spinner>
                        <span class="messages-loading-label">${this._tp('message_list.loading_messages')}</span>
                    </div>
                    <div class="skeleton-list" aria-hidden="true">
                        ${plan.map((row, i) => {
            const delay = `${i * 0.06}s`;
            const bubbleClass = row.side === 'other'
                ? 'skeleton-bubble skeleton-bubble--other'
                : 'skeleton-bubble skeleton-bubble--own';
            const avatar = row.side === 'other'
                ? html`<div
                                    class="skeleton-avatar skeleton-avatar--other"
                                    style=${`animation-delay: ${delay}`}
                                ></div>`
                : '';
            return html`
                            <div class="skeleton-row ${row.side}">
                                ${avatar}
                                <div
                                    class=${bubbleClass}
                                    style=${`width: ${row.widthPct}%; min-height: ${row.minH}px; animation-delay: ${delay}`}
                                ></div>
                            </div>
                        `;
        })}
                    </div>
                </div>
            `;
        }

        return html`
            <div class="list" @scroll=${this._onScroll} @scroll-to-message=${this._onScrollToMessage}>
                ${filtered.length === 0 ? html`<div class="empty-text">${this._tp('message_list.empty_messages')}</div>` : ''}
                ${this._loadingOlder ? html`
                    <div class="messages-loading-bar" aria-live="polite">
                        <glass-spinner size="sm"></glass-spinner>
                        <span class="messages-loading-label">${this._tp('message_list.loading_history')}</span>
                    </div>
                ` : ''}
                ${items.map((item) => {
                    if (item.kind === 'day') {
                        return html`
                            <div class="day-divider">
                                <span>${this._formatDayDividerLabel(item.sentAt)}</span>
                            </div>
                        `;
                    }
                    const msg = item.msg;
                    const selected = this._selectedMessageIds.includes(msg.id);
                    const flashActive = this._flashMessageId === msg.id;
                    const flashSeq = flashActive ? this._flashMessageSeq : 0;
                    const deleting = this._deletingMessageIds.includes(msg.id);
                    const groupPosition = item.groupPosition ?? 'single';
                    return html`
                        <message-bubble
                            data-msg-id=${msg.id}
                            .msg=${msg}
                            .channelId=${this.channelId}
                            .activeCallOverlay=${this._activeCallOverlay}
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
                            .groupPosition=${groupPosition}
                            @focus-thread=${(e) => SyncStore.setFocusedThread(e.detail.threadId)}
                        ></message-bubble>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('message-list', MessageList);

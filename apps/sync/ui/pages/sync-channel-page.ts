/**
 * sync-channel-page — главный экран чата (по `/sync/c/:channelId`).
 *
 * Состав: <sync-chat-header>, <sync-pin-strip>, <sync-selection-bar>,
 * <sync-message-list>, <sync-message-composer>, <sync-thread-drawer>,
 * <sync-message-context-menu>.
 *
 * Mount-логика: при смене channelId — `useOp('sync/messages').run({ channel_id })`
 * + `useResource('sync/channels') as SyncChannelsController.selectChannel({ channelId })` (channel_selected)
 * + `useOp('sync/channel_mark_read').run` для обнуления unread.
 */

import type { SyncMessagesStoreController, SyncChannelsController} from '../events/sync.types.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/sync-chat-header.js';
import '../components/sync-pin-strip.js';
import '../components/sync-selection-bar.js';
import '../components/sync-message-list.js';
import '../components/sync-message-composer.js';
import '../components/sync-message-context-menu.js';
import '../components/sync-thread-drawer.js';
import { SYNC_MESSAGE_CREATED } from '../events/types.js';

export class SyncChannelPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        channelId: { type: String },
    };
    declare channelId: string;

    static override styles: CSSResultGroup = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            height: 100%;
            min-height: 0;
            position: relative;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow: hidden;
            display: flex;
        }
        .body-main {
            flex: 1;
            min-height: 0;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
    `;
    private _channels: SyncChannelsController;
    private _messages: OpController;
    private _messagesStore: SyncMessagesStoreController;
    private _markRead: OpController;
    private _authSel: SelectController<Record<string, any> | undefined>;
    private _lastLoadedChannel: string;
    private _loadSeq: number;

    constructor() {
        super();
        this.channelId = '';
        this._channels = this.useResource('sync/channels', { autoload: true }) as SyncChannelsController;
        this._messages = this.useOp('sync/messages');
        this._messagesStore = this.useSlice('sync/messages_store') as SyncMessagesStoreController;
        this._markRead = this.useOp('sync/channel_mark_read');
        this._authSel = this.select((s) => (s.auth as Record<string, any> | undefined)?.user);
        this._lastLoadedChannel = '';
        this._loadSeq = 0;
        this.useEvent(SYNC_MESSAGE_CREATED, (event) => this._onMessageCreated(event));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.addEventListener('jump-to-message', this._onJumpToMessageFromPinStrip);
    }

    override disconnectedCallback(): void {
        this.removeEventListener('jump-to-message', this._onJumpToMessageFromPinStrip);
        super.disconnectedCallback();
    }

    /**
     * Полоска закрепов — sibling `sync-message-list`, не предок: всплывающее
     * DOM-событие ловим на странице и вызываем публичный API списка (скролл + flash).
     */
    _onJumpToMessageFromPinStrip = (e: Event) => {
        const detail = (e as CustomEvent<{ messageId?: unknown }>).detail;
        if (!detail || typeof detail.messageId !== 'string' || detail.messageId === '') return;
        const list = this.shadowRoot && this.shadowRoot.querySelector('sync-message-list') as { scrollToMessageId?: (id: string) => void } | null;
        if (!list || typeof list.scrollToMessageId !== 'function') return;
        e.stopPropagation();
        list.scrollToMessageId(detail.messageId);
    };

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this.channelId && this._lastLoadedChannel !== this.channelId) {
            const channelId = this.channelId;
            this._lastLoadedChannel = channelId;
            this._channels.selectChannel({ channelId });
            this._loadMessagesForChannel(channelId);
            this._markRead.run({ channel_id: channelId });
        }
    }

    async _loadMessagesForChannel(channelId: string) {
        const seq = ++this._loadSeq;
        this._messagesStore.startInitial({ channelId });
        try {
            await this._messages.run({ channel_id: channelId, limit: 50 });
        } catch (err) {
            const message = err instanceof Error ? err.message : 'failed';
            this._messagesStore.failInitial({ channelId, message });
            return;
        }
        if (seq !== this._loadSeq || this.channelId !== channelId) return;
        this._messagesStore.loadedInitial({ channelId, result: this._messages.lastResult });
    }

    _onMessageCreated(event: PlatformEvent) {
        const m = event && event.payload as Record<string, unknown> | null;
        if (!m || m.channel_id !== this.channelId) return;
        this._markRead.run({ channel_id: this.channelId });
    }

    _resolveMyUserId() {
        const me = this._authSel.value;
        if (!me || typeof me.user_id !== 'string') return '';
        return me.user_id;
    }

    _channel() {
        return this._channels.items.find((c) => c.channel_id === this.channelId);
    }

    override render(): TemplateResult {
        const channel = this._channel();
        const channelType = channel && typeof channel.type === 'string' ? channel.type : '';
        const myUserId = this._resolveMyUserId();
        return html`
            <sync-chat-header .channelId=${this.channelId}></sync-chat-header>
            <sync-pin-strip .channelId=${this.channelId}></sync-pin-strip>
            <sync-selection-bar .channelId=${this.channelId}></sync-selection-bar>
            <div class="body">
                <div class="body-main">
                    <sync-message-list
                        .channelId=${this.channelId}
                        my-user-id=${myUserId}
                        channel-type=${channelType}
                    ></sync-message-list>
                    <sync-message-composer .channelId=${this.channelId}></sync-message-composer>
                </div>
                <sync-thread-drawer .channelId=${this.channelId}></sync-thread-drawer>
            </div>
            <sync-message-context-menu .channelId=${this.channelId}></sync-message-context-menu>
        `;
    }
}

customElements.define('sync-channel-page', SyncChannelPage);

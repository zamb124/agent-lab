/**
 * ChatView — основной контейнер чата: хедер + список сообщений + composer
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import './channel-picker.js';
import './message-list.js';
import './message-composer.js';
import './thread-drawer.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-icon.js';

export class ChatView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                overflow: hidden;
                box-sizing: border-box;
            }

            .chat-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                flex-shrink: 0;
            }

            .header-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .header-subtitle {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }

            .header-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .icon-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                padding: var(--space-2);
                transition: all var(--duration-fast);
                display: flex;
                align-items: center;
            }

            .icon-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .icon-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }

            .back-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                display: flex;
                align-items: center;
                gap: var(--space-2);
                transition: all var(--duration-fast);
            }

            .back-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .content {
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            .ws-badge {
                font-size: 10px;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                border: 1px solid;
            }

            .ws-badge.open {
                background: rgba(16, 185, 129, 0.1);
                border-color: rgba(16, 185, 129, 0.4);
                color: rgb(16, 185, 129);
            }

            .ws-badge.connecting {
                background: rgba(245, 158, 11, 0.1);
                border-color: rgba(245, 158, 11, 0.4);
                color: rgb(245, 158, 11);
            }

            .ws-badge.closed {
                background: rgba(239, 68, 68, 0.1);
                border-color: rgba(239, 68, 68, 0.4);
                color: rgb(239, 68, 68);
            }

            .pin-strip {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: rgba(245, 158, 11, 0.08);
                cursor: pointer;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .pin-strip:hover {
                background: rgba(245, 158, 11, 0.14);
            }

            .selection-bar {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid rgba(244, 114, 182, 0.35);
                background: rgba(244, 114, 182, 0.14);
                font-size: var(--text-xs);
            }

            .selection-actions {
                display: flex;
                gap: var(--space-2);
            }

            .modal-overlay {
                position: fixed;
                inset: 0;
                z-index: 300;
                background: rgba(0, 0, 0, 0.45);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }

            .modal-box {
                width: min(420px, 100%);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                padding: var(--space-4);
                max-height: 70vh;
                overflow: auto;
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-3);
            }

            .channel-pick {
                width: 100%;
                text-align: left;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                cursor: pointer;
                margin-bottom: var(--space-2);
                font-size: var(--text-sm);
            }

            .channel-pick:hover {
                background: var(--glass-solid-medium);
            }
        `
    ];

    static properties = {
        _chat: { state: true },
        _channels: { state: true },
        _wsState: { state: true },
        _threadIds: { state: true },
        _ui: { state: true },
    };

    constructor() {
        super();
        const s = SyncStore.state;
        this._chat = s.chat;
        this._channels = s.channels;
        this._wsState = s.ws.state;
        this._threadIds = [];
        this._ui = SyncStore.state.ui;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._chat = state.chat;
            this._channels = state.channels;
            this._wsState = state.ws.state;
            this._threadIds = SyncStore.getThreadIds();
            this._ui = state.ui;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _selectedChannel() {
        const { selectedChannelId } = this._chat;
        if (!selectedChannelId) return null;
        return this._channels.list.find(c => c.id === selectedChannelId) ?? null;
    }

    _getTitle() {
        const { focusedThreadId, selectedChannelId } = this._chat;
        if (focusedThreadId) return 'Тред';
        if (!selectedChannelId) return 'Выбери канал';
        const ch = this._selectedChannel();
        if (!ch) return selectedChannelId;
        if (ch.type === 'direct' && ch.peer && typeof ch.peer.display_name === 'string') {
            return ch.peer.display_name;
        }
        return ch.name ?? selectedChannelId;
    }

    _getSubtitle() {
        const { focusedThreadId } = this._chat;
        const ch = this._selectedChannel();
        if (!ch) return '';
        const chLabel = ch.type === 'direct' && ch.peer?.display_name
            ? ch.peer.display_name
            : (ch.name ?? ch.id);
        if (focusedThreadId) return `Канал: ${chLabel} • thread_id: ${focusedThreadId}`;
        return ch.type ?? '';
    }

    _messageListEl() {
        return this.shadowRoot?.querySelector('message-list');
    }

    _onPinStripClick() {
        const ch = this._selectedChannel();
        const ids = ch?.pinned_message_ids;
        if (!Array.isArray(ids) || ids.length === 0) return;
        const i = this._chat.pinnedNavigateIndex % ids.length;
        const targetId = ids[i];
        SyncStore.setPinnedNavigateIndex((i + 1) % ids.length);
        this.updateComplete.then(() => {
            const ml = this._messageListEl();
            if (!ml) {
                throw new Error('message-list не найден.');
            }
            ml.scrollToMessageId(targetId);
            SyncStore.flashMessageHighlight(targetId);
        }).catch((err) => {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        });
    }

    async _deleteSelected() {
        const syncApi = ServiceRegistry.get('syncApi');
        const channelId = this._chat.selectedChannelId;
        if (!channelId) throw new Error('Канал не выбран.');
        const ids = this._ui.selectedMessageIds;
        for (const mid of ids) {
            await syncApi.deleteMessage(channelId, mid);
        }
        SyncStore.clearMessageSelection();
        SyncStore.setSelectionMode(false);
        await SyncStore.loadMessages(syncApi, channelId);
    }

    async _forwardSelectedToChannel(toChannelId) {
        const syncApi = ServiceRegistry.get('syncApi');
        const fromId = this._chat.selectedChannelId;
        if (!fromId) throw new Error('Канал не выбран.');
        const ids = this._ui.selectedMessageIds;
        for (const mid of ids) {
            await syncApi.forwardMessage(fromId, mid, toChannelId, null);
        }
        SyncStore.clearMessageSelection();
        SyncStore.setSelectionMode(false);
        SyncStore.setForwardModal(false, null);
        await SyncStore.loadMessages(syncApi, fromId);
    }

    async _forwardModalPick(toChannelId) {
        const syncApi = ServiceRegistry.get('syncApi');
        const fwd = this._ui.forwardMessage;
        const fromId = this._chat.selectedChannelId;
        if (!fwd?.id || !fromId) throw new Error('Нет сообщения для пересылки.');
        await syncApi.forwardMessage(fromId, fwd.id, toChannelId, null);
        SyncStore.setForwardModal(false, null);
        await SyncStore.loadMessages(syncApi, fromId);
    }

    render() {
        const { selectedChannelId, focusedThreadId } = this._chat;
        const selectedChannel = this._selectedChannel();
        const pins = selectedChannel?.pinned_message_ids;
        const pinCount = Array.isArray(pins) ? pins.length : 0;
        const selMode = this._ui.selectionMode;
        const selIds = this._ui.selectedMessageIds;
        const fwdOpen = this._ui.forwardModalOpen;
        const otherChannels = this._channels.list.filter(c => c.id !== selectedChannelId);

        return html`
            <div class="chat-header">
                <div>
                    <div class="header-title">${this._getTitle()}</div>
                    ${this._getSubtitle() ? html`<div class="header-subtitle">${this._getSubtitle()}</div>` : ''}
                </div>
                <div class="header-actions">
                    <span class="ws-badge ${this._wsState}">${this._wsState}</span>

                    ${focusedThreadId ? html`
                        <button class="back-btn" @click=${() => SyncStore.setFocusedThread(null)}>
                            <platform-icon name="chevron-left" size="14"></platform-icon>
                            Назад
                        </button>
                    ` : html`
                        <button
                            class="icon-btn"
                            title="Треды"
                            ?disabled=${this._threadIds.length === 0}
                            @click=${() => SyncStore.setThreadDrawerOpen(true)}
                        >
                            <platform-icon name="chat" size="16"></platform-icon>
                        </button>
                        <button
                            class="icon-btn"
                            title="Меню"
                            @click=${() => SyncStore.setMobileSidebarOpen(true)}
                        >
                            <platform-icon name="hamburger" size="16"></platform-icon>
                        </button>
                    `}
                </div>
            </div>

            <div class="content">
                ${!selectedChannelId ? html`
                    <channel-picker></channel-picker>
                ` : html`
                    ${pinCount > 0 && !focusedThreadId ? html`
                        <div class="pin-strip" @click=${this._onPinStripClick} title="Перейти к закреплённому">
                            <platform-icon name="target" size="14"></platform-icon>
                            <span>Закреплённые сообщения (${pinCount}) — нажмите для перехода по кругу</span>
                        </div>
                    ` : ''}
                    ${selMode ? html`
                        <div class="selection-bar">
                            <span>Выбрано: ${selIds.length}</span>
                            <div class="selection-actions">
                                <button type="button" class="back-btn" @click=${() => {
        SyncStore.setSelectionMode(false);
    }}>Отмена</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${() => SyncStore.setForwardModal(true, null)}
                                >Переслать</button>
                                <button
                                    type="button"
                                    class="back-btn"
                                    ?disabled=${selIds.length === 0}
                                    @click=${this._deleteSelected}
                                >Удалить</button>
                            </div>
                        </div>
                    ` : ''}
                    <message-list .channelId=${selectedChannelId}></message-list>
                    <message-composer .channelId=${selectedChannelId}></message-composer>
                `}
            </div>

            ${fwdOpen ? html`
                <div class="modal-overlay" @click=${(e) => {
        if (e.target === e.currentTarget) SyncStore.setForwardModal(false, null);
    }}>
                    <div class="modal-box" @click=${(e) => e.stopPropagation()}>
                        <div class="modal-title">Куда переслать</div>
                        ${otherChannels.length === 0 ? html`<p class="header-subtitle">Нет других каналов.</p>` : ''}
                        ${otherChannels.map(c => html`
                            <button
                                type="button"
                                class="channel-pick"
                                @click=${() => {
        const one = this._ui.forwardMessage;
        if (one?.id) {
            this._forwardModalPick(c.id);
        } else if (this._ui.selectedMessageIds.length > 0) {
            this._forwardSelectedToChannel(c.id);
        } else {
            SyncStore.setForwardModal(false, null);
        }
    }}
                            >${c.name ?? c.id}</button>
                        `)}
                        <button type="button" class="back-btn" style="margin-top:var(--space-3)" @click=${() => SyncStore.setForwardModal(false, null)}>Закрыть</button>
                    </div>
                </div>
            ` : ''}

            <thread-drawer></thread-drawer>
        `;
    }
}

customElements.define('chat-view', ChatView);

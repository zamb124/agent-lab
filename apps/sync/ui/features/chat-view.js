/**
 * ChatView — основной контейнер чата: хедер + список сообщений + composer
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
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
        `
    ];

    static properties = {
        _chat: { state: true },
        _channels: { state: true },
        _wsState: { state: true },
        _threadIds: { state: true },
    };

    constructor() {
        super();
        const s = SyncStore.state;
        this._chat = s.chat;
        this._channels = s.channels;
        this._wsState = s.ws.state;
        this._threadIds = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._chat = state.chat;
            this._channels = state.channels;
            this._wsState = state.ws.state;
            this._threadIds = SyncStore.getThreadIds();
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
        return ch?.name ?? selectedChannelId;
    }

    _getSubtitle() {
        const { focusedThreadId } = this._chat;
        const ch = this._selectedChannel();
        if (!ch) return '';
        if (focusedThreadId) return `Канал: ${ch.name ?? ch.id} • thread_id: ${focusedThreadId}`;
        return ch.type ?? '';
    }

    render() {
        const { selectedChannelId, focusedThreadId } = this._chat;
        const selectedChannel = this._selectedChannel();

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
                    <message-list .channelId=${selectedChannelId}></message-list>
                    <message-composer .channelId=${selectedChannelId}></message-composer>
                `}
            </div>

            <thread-drawer></thread-drawer>
        `;
    }
}

customElements.define('chat-view', ChatView);

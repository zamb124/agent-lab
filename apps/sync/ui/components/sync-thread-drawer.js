/**
 * sync-thread-drawer — боковая панель тредов канала.
 *
 * Слайдер справа от чата. Отображается когда `state.syncThreads.selectedThreadId !== null`.
 * Не блокирующая модалка — composer основного чата остаётся доступен.
 *
 * Действия:
 *   - закрыть: dispatch('sync/threads/drawer_closed')
 *   - открыть тред: dispatch('sync/threads/open_requested', { threadId })
 *
 * Внутри:
 *   - <sync-message-list> с props.thread-id
 *   - <sync-message-composer> с props.threadId
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import './sync-message-list.js';
import './sync-message-composer.js';

export class SyncThreadDrawer extends PlatformElement {
    static properties = {
        channelId: { type: String },
    };

    static styles = css`
        :host {
            display: none;
            width: 360px;
            border-left: 1px solid var(--glass-border);
            background: var(--glass-solid);
            flex-direction: column;
            min-height: 0;
        }
        :host([open]) { display: flex; }
        @media (max-width: 767px) {
            :host([open]) {
                position: absolute;
                inset: 0;
                width: 100%;
                z-index: 5;
            }
        }
        .header {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            padding: var(--space-3);
            border-bottom: 1px solid var(--glass-border);
            font-weight: 600;
        }
        .close {
            background: transparent;
            border: none;
            color: var(--text-primary);
            cursor: pointer;
            padding: var(--space-1);
            margin-left: auto;
        }
        .body {
            flex: 1;
            min-height: 0;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
    `;

    constructor() {
        super();
        this.channelId = '';
        this._threadsSel = this.select((s) => s.syncThreads);
    }

    _selectedThreadId() {
        const slice = this._threadsSel.value;
        return slice && slice.selectedThreadId;
    }

    _onClose() {
        this.dispatch('sync/threads/drawer_closed', null);
    }

    updated() {
        this.toggleAttribute('open', Boolean(this._selectedThreadId()));
    }

    render() {
        const threadId = this._selectedThreadId();
        if (!threadId) return html``;
        return html`
            <div class="header">
                <span>${this.t('thread_drawer.title')}</span>
                <button class="close" @click=${this._onClose} title=${this.t('thread_drawer.close')}>
                    <platform-icon name="x" size="16"></platform-icon>
                </button>
            </div>
            <div class="body">
                <sync-message-list .channelId=${this.channelId} thread-id=${threadId}></sync-message-list>
                <sync-message-composer .channelId=${this.channelId} thread-id=${threadId}></sync-message-composer>
            </div>
        `;
    }
}

customElements.define('sync-thread-drawer', SyncThreadDrawer);

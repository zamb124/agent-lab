/**
 * ThreadDrawer — боковой drawer со списком тредов в текущем канале
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { modalShellStyles } from '@platform/lib/platform-element/styles.js';

export class ThreadDrawer extends PlatformElement {
    static properties = {
        _open: { state: true },
        _threadIds: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        modalShellStyles,
        css`
            .backdrop {
                position: fixed;
                inset: 0;
                z-index: 40;
                background: rgba(0, 0, 0, 0.4);
            }

            .drawer {
                position: fixed;
                right: var(--space-4);
                top: var(--space-4);
                z-index: 50;
                width: min(420px, calc(100% - 32px));
                max-height: calc(100% - 32px);
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            .drawer-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }

            .drawer-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .close-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
                padding: 4px 10px;
                transition: all var(--duration-fast);
            }

            .close-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .drawer-body {
                overflow-y: auto;
                padding: var(--space-4);
                flex: 1;
            }

            .empty-text {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            .thread-item {
                width: 100%;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                margin-bottom: var(--space-2);
                transition: all var(--duration-fast);
            }

            .thread-item:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
        `
    ];

    constructor() {
        super();
        this._open = SyncStore.state.ui.threadDrawerOpen;
        this._threadIds = SyncStore.getThreadIds();
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._open = state.ui.threadDrawerOpen;
            this._threadIds = SyncStore.getThreadIds();
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _close() {
        SyncStore.setThreadDrawerOpen(false);
    }

    _focusThread(tid) {
        SyncStore.setFocusedThread(tid);
        SyncStore.setThreadDrawerOpen(false);
    }

    render() {
        if (!this._open) return html``;

        return html`
            <div class="backdrop" @click=${this._close}></div>
            <aside class="drawer">
                <div class="drawer-header">
                    <span class="drawer-title">Треды</span>
                    <button class="close-btn" @click=${this._close}>Закрыть</button>
                </div>
                <div class="drawer-body">
                    ${this._threadIds.length === 0 ? html`
                        <div class="empty-text">Тредов пока нет.</div>
                    ` : this._threadIds.map(tid => html`
                        <button class="thread-item" @click=${() => this._focusThread(tid)}>${tid}</button>
                    `)}
                </div>
            </aside>
        `;
    }
}

customElements.define('thread-drawer', ThreadDrawer);

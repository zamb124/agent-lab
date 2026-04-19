/**
 * Platform Notification Manager — индикатор inbox-уведомлений в хедере.
 *
 * Полностью event-driven: список приходит из state.notifications.list. WS-канал
 * уведомлений уже обслуживает core/lib/events/effects/ws.effect.js — этот
 * компонент только отображает.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { NOTIFICATIONS_EVENTS } from '../events/reducers/notifications.js';
import { CoreEvents } from '../events/contract.js';
import { PWA_EVENTS } from '../events/effects/pwa.effect.js';
import './platform-icon.js';

export class PlatformNotificationManager extends PlatformElement {
    static properties = {
        _panelOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: inline-block; position: relative; }

            .bell {
                position: relative;
                display: inline-flex; align-items: center; justify-content: center;
                width: 36px; height: 36px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .bell:hover { color: var(--text-primary); }
            .badge {
                position: absolute; top: -2px; right: -2px;
                min-width: 16px; height: 16px;
                padding: 0 4px;
                border-radius: 8px;
                background: var(--error);
                color: white;
                font-size: 10px; font-weight: 700;
                display: flex; align-items: center; justify-content: center;
            }

            .panel {
                position: absolute; bottom: calc(100% + 8px); left: 0;
                width: 360px; max-height: 480px; overflow: auto;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong);
                z-index: var(--z-dropdown, 100);
            }
            .panel-header {
                display: flex; align-items: center; justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .panel-title { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--text-primary); }
            .panel-action {
                background: none; border: none; color: var(--text-tertiary);
                font-size: var(--text-xs); cursor: pointer;
            }
            .panel-action:hover { color: var(--accent); }

            .item {
                display: flex; flex-direction: column; gap: 2px;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                cursor: pointer;
            }
            .item:hover { background: var(--glass-solid-medium); }
            .item-title { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--text-primary); }
            .item-message { font-size: var(--text-xs); color: var(--text-secondary); }
            .item-meta { font-size: 10px; color: var(--text-tertiary); margin-top: 2px; }

            .empty { padding: var(--space-6); text-align: center; color: var(--text-tertiary); font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this._panelOpen = false;
        this._notifSelect = this.select((s) => ({ list: s.notifications.list, unread: s.notifications.unread }));
        this._pushSelect = this.select((s) => ({ permission: s.pwa.pushPermission, registered: s.pwa.pushRegistered }));
        this._onClickOutside = this._onClickOutside.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onClickOutside);
        // По первому показу — попросим разрешение на push, если ещё default.
        const push = this._pushSelect.value;
        if (push && push.permission === 'default') {
            this.dispatch(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED, null);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onClickOutside);
    }

    _onClickOutside(e) {
        if (this._panelOpen && !this.contains(e.target)) {
            this._panelOpen = false;
        }
    }

    _togglePanel(e) {
        e?.stopPropagation();
        this._panelOpen = !this._panelOpen;
    }

    _onItemClick(item) {
        this.dispatch(NOTIFICATIONS_EVENTS.READ, { id: item.id });
        if (item.action_url) {
            window.location.href = item.action_url;
        }
    }

    _dismissAll() {
        this.dispatch(NOTIFICATIONS_EVENTS.DISMISS_ALL, null);
    }

    render() {
        const { list = [], unread = 0 } = this._notifSelect.value || {};

        return html`
            <button class="bell" @click=${this._togglePanel} title=${this.t('notifications.title') || 'Notifications'}>
                <platform-icon name="bell" size="18"></platform-icon>
                ${unread > 0 ? html`<span class="badge">${unread > 99 ? '99+' : unread}</span>` : ''}
            </button>

            ${this._panelOpen ? html`
                <div class="panel" @click=${(e) => e.stopPropagation()}>
                    <div class="panel-header">
                        <span class="panel-title">${this.t('notifications.title') || 'Notifications'}</span>
                        ${list.length > 0 ? html`<button class="panel-action" @click=${this._dismissAll}>${this.t('notifications.dismiss_all') || 'Clear all'}</button>` : ''}
                    </div>
                    ${list.length === 0 ? html`
                        <div class="empty">${this.t('notifications.empty') || 'No notifications yet'}</div>
                    ` : list.map((n) => html`
                        <div class="item" @click=${() => this._onItemClick(n)}>
                            ${n.title ? html`<div class="item-title">${n.title}</div>` : ''}
                            ${n.message ? html`<div class="item-message">${n.message}</div>` : ''}
                            <div class="item-meta">${n.scope}/${n.kind}</div>
                        </div>
                    `)}
                </div>
            ` : ''}
        `;
    }
}

customElements.define('platform-notification-manager', PlatformNotificationManager);

/**
 * Platform Notification Manager — индикатор inbox-уведомлений в хедере.
 *
 * Полностью event-driven: список приходит из state.notifications.list. WS-канал
 * уведомлений уже обслуживает core/lib/events/effects/ws.effect.js — этот
 * компонент только отображает.
 *
 * Сама панель порталится в `document.body` (а не рендерится в shadow root),
 * чтобы не клиппиться `overflow: hidden`/`backdrop-filter`/`contain` любого
 * родителя — bell обычно живёт в `slot="user-toolbar"` платформенного
 * sidebar или в `<platform-island>`, у которых стек контейнеров может
 * обрезать абсолютно позиционированный dropdown. Portal-узел адаптируется
 * к смене viewport через `window resize` и capture-`scroll`.
 */

import { html, css, render as litRender } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { NOTIFICATIONS_EVENTS } from '../events/reducers/notifications.js';
import { PWA_EVENTS } from '../events/effects/pwa.effect.js';
import { translate } from '../events/effects/i18n.effect.js';
import './platform-icon.js';

const PANEL_WIDTH = 360;
const PANEL_GAP = 8;
const PANEL_VIEWPORT_PADDING = 8;

let _panelStylesInjected = false;

function _ensurePanelStyles() {
    if (_panelStylesInjected) return;
    _panelStylesInjected = true;
    const style = document.createElement('style');
    style.id = 'platform-notification-portal-styles';
    style.textContent = `
        .platform-notif-portal {
            position: fixed;
            width: ${PANEL_WIDTH}px;
            max-height: 480px;
            overflow: auto;
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-strong));
            -webkit-backdrop-filter: blur(var(--glass-blur-strong));
            border: 1px solid var(--glass-border-medium);
            border-radius: var(--radius-lg);
            box-shadow: var(--glass-shadow-strong);
            z-index: var(--z-popover, 1100);
        }
        .platform-notif-portal__header {
            display: flex; align-items: center; justify-content: space-between;
            padding: var(--space-3) var(--space-4);
            border-bottom: 1px solid var(--glass-border-subtle);
        }
        .platform-notif-portal__title {
            font-size: var(--text-sm);
            font-weight: var(--font-semibold);
            color: var(--text-primary);
        }
        .platform-notif-portal__action {
            background: none; border: none;
            color: var(--text-tertiary);
            font-size: var(--text-xs);
            cursor: pointer;
        }
        .platform-notif-portal__action:hover { color: var(--accent); }
        .platform-notif-portal__item {
            display: flex; flex-direction: column; gap: 2px;
            padding: var(--space-3) var(--space-4);
            border-bottom: 1px solid var(--glass-border-subtle);
            cursor: pointer;
        }
        .platform-notif-portal__item:hover { background: var(--glass-solid-medium); }
        .platform-notif-portal__item-title {
            font-size: var(--text-sm);
            font-weight: var(--font-semibold);
            color: var(--text-primary);
            overflow-wrap: anywhere;
        }
        .platform-notif-portal__item-message {
            font-size: var(--text-xs);
            color: var(--text-secondary);
            overflow-wrap: anywhere;
        }
        .platform-notif-portal__item-actions {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-top: var(--space-2);
        }
        .platform-notif-portal__item-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 28px;
            max-width: 100%;
            padding: 0 var(--space-3);
            border-radius: var(--radius-full);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-solid-medium);
            color: var(--accent);
            font-size: var(--text-xs);
            font-weight: var(--font-medium);
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .platform-notif-portal__item-link:hover {
            border-color: var(--accent);
            background: var(--glass-tint-medium);
        }
        .platform-notif-portal__item-meta {
            font-size: 10px;
            color: var(--text-tertiary);
            margin-top: 2px;
        }
        .platform-notif-portal__empty {
            padding: var(--space-6);
            text-align: center;
            color: var(--text-tertiary);
            font-size: var(--text-sm);
        }
    `;
    document.head.appendChild(style);
}

export class PlatformNotificationManager extends PlatformElement {
    static i18nNamespace = 'platform';

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
        `,
    ];

    constructor() {
        super();
        this._panelOpen = false;
        this._notifSelect = this.select((s) => ({
            list: s.notifications.list,
            unread: s.notifications.unread,
        }));
        this._pushSelect = this.select((s) => ({
            permission: s.pwa.pushPermission,
            registered: s.pwa.pushRegistered,
        }));
        this._portal = null;
        this._onClickOutside = this._onClickOutside.bind(this);
        this._onReposition = this._onReposition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        _ensurePanelStyles();
        document.addEventListener('click', this._onClickOutside);
        const push = this._pushSelect.value;
        if (push && push.permission === 'default') {
            this.dispatch(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED, null);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onClickOutside);
        this._closePanel();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('_panelOpen')) {
            if (this._panelOpen) this._openPanel();
            else this._closePanel();
        } else if (this._panelOpen && this._portal) {
            this._renderPortal();
        }
    }

    _onClickOutside(e) {
        if (!this._panelOpen) return;
        const path = e.composedPath ? e.composedPath() : [e.target];
        if (path.includes(this)) return;
        if (this._portal && path.includes(this._portal)) return;
        this._panelOpen = false;
    }

    _togglePanel(e) {
        if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
        this._panelOpen = !this._panelOpen;
    }

    _openPanel() {
        if (this._portal) return;
        const node = document.createElement('div');
        node.className = 'platform-notif-portal';
        node.addEventListener('click', (e) => e.stopPropagation());
        document.body.appendChild(node);
        this._portal = node;
        this._renderPortal();
        this._reposition();
        window.addEventListener('resize', this._onReposition);
        document.addEventListener('scroll', this._onReposition, true);
    }

    _closePanel() {
        window.removeEventListener('resize', this._onReposition);
        document.removeEventListener('scroll', this._onReposition, true);
        if (this._portal && this._portal.parentNode) {
            litRender(null, this._portal);
            this._portal.remove();
        }
        this._portal = null;
    }

    _onReposition() {
        if (!this._portal) return;
        requestAnimationFrame(() => this._reposition());
    }

    _reposition() {
        if (!this._portal) return;
        const bell = this.renderRoot && this.renderRoot.querySelector('.bell');
        if (!bell) return;
        const rect = bell.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        let left = rect.left;
        if (left + PANEL_WIDTH > vw - PANEL_VIEWPORT_PADDING) {
            left = Math.max(PANEL_VIEWPORT_PADDING, vw - PANEL_WIDTH - PANEL_VIEWPORT_PADDING);
        }
        const bottom = vh - rect.top + PANEL_GAP;
        this._portal.style.left = `${Math.round(left)}px`;
        this._portal.style.bottom = `${Math.round(bottom)}px`;
        this._portal.style.top = '';
        this._portal.style.right = '';
    }

    _onItemClick(item) {
        this.dispatch(NOTIFICATIONS_EVENTS.READ, { id: item.id });
        const href = this._safeHref(item.action_url);
        if (href) {
            window.location.href = href;
        }
    }

    _onActionClick(event, item) {
        event.stopPropagation();
        this.dispatch(NOTIFICATIONS_EVENTS.READ, { id: item.id });
        this._panelOpen = false;
    }

    _dismissAll() {
        this.dispatch(NOTIFICATIONS_EVENTS.DISMISS_ALL, null);
    }

    _splitQualifiedKey(raw) {
        if (typeof raw !== 'string' || raw.length === 0) return null;
        const [nsOrKey, ...rest] = raw.split(':');
        if (rest.length === 0) return { key: raw, namespace: undefined };
        return { key: rest.join(':'), namespace: nsOrKey };
    }

    _translateKey(raw, vars) {
        const parsed = this._splitQualifiedKey(raw);
        if (!parsed) return '';
        const state = this.bus.getState().i18n;
        return translate(state, parsed.key, vars || undefined, parsed.namespace);
    }

    _looksLikeI18nKey(value) {
        return typeof value === 'string'
            && /^[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+|\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)$/i.test(value);
    }

    _resolveNotifText(item, field) {
        const text = typeof item[field] === 'string' ? item[field] : '';
        const key = typeof item[`${field}_i18n_key`] === 'string' ? item[`${field}_i18n_key`] : '';
        const vars = item[`${field}_i18n_vars`] || item.data || undefined;
        if (key.length > 0) {
            const resolved = this._translateKey(key, vars);
            if (resolved.length > 0 && resolved !== key) return resolved;
            return text || resolved;
        }
        if (this._looksLikeI18nKey(text)) {
            const resolved = this._translateKey(text, vars);
            if (resolved !== text) return resolved;
        }
        return text;
    }

    _safeHref(raw) {
        if (typeof raw !== 'string') return '';
        const href = raw.trim();
        if (href.length === 0) return '';
        if (href.startsWith('/') || href.startsWith('#')) return href;
        if (/^https?:\/\//i.test(href)) return href;
        return '';
    }

    _resolveActionLabel(action) {
        const key = typeof action.label_i18n_key === 'string' ? action.label_i18n_key : '';
        const vars = action.label_i18n_vars || action.data || undefined;
        if (key.length > 0) {
            const resolved = this._translateKey(key, vars);
            if (resolved.length > 0 && resolved !== key) return resolved;
        }
        if (typeof action.label === 'string' && action.label.trim().length > 0) {
            return action.label.trim();
        }
        return this.t('notifications.open');
    }

    _notificationActions(item) {
        const out = [];
        const seen = new Set();
        const add = (raw) => {
            if (!raw || typeof raw !== 'object') return;
            const href = this._safeHref(raw.url || raw.href || raw.action_url);
            if (!href || seen.has(href)) return;
            seen.add(href);
            out.push({ ...raw, href, label: this._resolveActionLabel(raw) });
        };
        if (Array.isArray(item.actions)) {
            for (const action of item.actions) add(action);
        }
        add({
            url: item.action_url,
            label: item.action_label,
            label_i18n_key: item.action_label_i18n_key,
        });
        return out;
    }

    _renderPortal() {
        if (!this._portal) return;
        const { list = [], unread: _unread = 0 } = this._notifSelect.value || {};
        const title = this.t('notifications.title');
        const dismissAll = this.t('notifications.dismiss_all');
        const empty = this.t('notifications.empty');
        const tpl = html`
            <div class="platform-notif-portal__header">
                <span class="platform-notif-portal__title">${title}</span>
                ${list.length > 0 ? html`
                    <button class="platform-notif-portal__action"
                            @click=${() => this._dismissAll()}>
                        ${dismissAll}
                    </button>
                ` : ''}
            </div>
            ${list.length === 0
                ? html`<div class="platform-notif-portal__empty">${empty}</div>`
                : list.map((n) => {
                    const titleText = this._resolveNotifText(n, 'title');
                    const messageText = this._resolveNotifText(n, 'message');
                    const actions = this._notificationActions(n);
                    return html`
                        <div class="platform-notif-portal__item"
                             @click=${() => this._onItemClick(n)}>
                            ${titleText ? html`<div class="platform-notif-portal__item-title">${titleText}</div>` : ''}
                            ${messageText ? html`<div class="platform-notif-portal__item-message">${messageText}</div>` : ''}
                            ${actions.length > 0 ? html`
                                <div class="platform-notif-portal__item-actions">
                                    ${actions.map((action) => html`
                                        <a class="platform-notif-portal__item-link"
                                           href=${action.href}
                                           @click=${(event) => this._onActionClick(event, n)}>
                                            ${action.label}
                                        </a>
                                    `)}
                                </div>
                            ` : ''}
                            <div class="platform-notif-portal__item-meta">${n.scope}/${n.kind}</div>
                        </div>
                    `;
                })}
        `;
        litRender(tpl, this._portal);
    }

    render() {
        const { unread = 0 } = this._notifSelect.value || {};
        return html`
            <button class="bell"
                    @click=${this._togglePanel}
                    title=${this.t('notifications.title')}>
                <platform-icon name="bell" size="18"></platform-icon>
                ${unread > 0 ? html`<span class="badge">${unread > 99 ? '99+' : unread}</span>` : ''}
            </button>
        `;
    }
}

customElements.define('platform-notification-manager', PlatformNotificationManager);

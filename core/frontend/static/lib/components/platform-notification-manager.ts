/**
 * Менеджер уведомлений платформы — индикатор inbox-уведомлений в хедере.
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

import { html, css, unsafeCSS } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';
import { NOTIFICATIONS_EVENTS } from '../events/reducers/notifications.js';
import type { NotificationItem } from '../events/reducers/notifications.js';
import type { PwaState } from '../events/reducers/pwa.js';
import type { I18nState } from '../events/reducers/i18n.js';
import type { SelectController } from '../events/select-controller.js';
import { PlatformPopover } from './platform-popover.js';
import { MAIL_EVENTS } from '../events/reducers/mail.js';
import { PWA_EVENTS } from '../events/effects/pwa.effect.js';
import { translate } from '../events/effects/i18n.effect.js';
import { isPlainRecord } from '../events/payload.js';
import { mergePlatformI18nVars } from '../utils/platform-i18n-vars.js';
import './platform-icon.js';
import './platform-work-item-badge.js';

function firstHref(raw: Record<string, unknown>): unknown {
    if (typeof raw.url === 'string' && raw.url.length > 0) return raw.url;
    if (typeof raw.href === 'string' && raw.href.length > 0) return raw.href;
    return raw.action_url;
}

function notificationVars(primary: unknown, fallback: unknown): Record<string, string | number> | undefined {
    const source = isPlainRecord(primary) ? primary : (isPlainRecord(fallback) ? fallback : null);
    if (source === null) return undefined;
    const vars: Record<string, string | number> = {};
    for (const [key, value] of Object.entries(source)) {
        if (typeof value === 'string' || typeof value === 'number') {
            vars[key] = value;
        }
    }
    return vars;
}

function presentString(value: string | null): string | undefined {
    return value === null || value.length === 0 ? undefined : value;
}

const PANEL_WIDTH = 360;
const PANEL_GAP = 8;
const PANEL_VIEWPORT_PADDING = 8;

interface NotificationAction {
    href: string;
    label: string;
    url?: string;
    action_url?: string | null;
    label_i18n_key?: string | null;
    label_i18n_vars?: Record<string, unknown> | null;
    data?: Record<string, unknown>;
}

const NOTIF_PANEL_CSS = `
        .platform-notif-portal {
            width: ${PANEL_WIDTH}px;
            max-width: 90vw;
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

export class PlatformNotificationManager extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        _panelOpen: { state: true },
        _anchor: { state: true },
    };
    declare _panelOpen: boolean;
    declare _anchor: HTMLElement | null;

    private _notifSelect: SelectController<{ list: NotificationItem[]; unread: number }>;
    private _pushSelect: SelectController<{ permission: PwaState['pushPermission']; registered: boolean }>;
    private _i18nSelect: SelectController<I18nState>;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        unsafeCSS(NOTIF_PANEL_CSS),
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
        this._i18nSelect = this.select((s) => s.i18n);
        this._anchor = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const push = this._pushSelect.value;
        if (push.permission === 'default') {
            this.dispatch(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED, null);
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        if (this._anchor === null) {
            const bell = this.renderRoot?.querySelector?.('.bell');
            if (bell instanceof HTMLElement) {
                this._anchor = bell;
            }
        }
        if (this._panelOpen) {
            const popover = this.renderRoot.querySelector('platform-popover');
            if (!(popover instanceof PlatformPopover)) {
                throw new Error('platform-notification-manager: open panel popover is missing');
            }
            popover.reposition();
        }
    }

    _togglePanel(e: Event) {
        if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
        this._panelOpen = !this._panelOpen;
    }

    _onPopoverDismiss(): void {
        this._panelOpen = false;
    }

    _onItemClick(item: NotificationItem): void {
        this.dispatch(NOTIFICATIONS_EVENTS.READ, { id: item.id });
        if (item.scope === 'mail' && item.kind === 'mail_new_message') {
            this._openMailFromNotification(item);
            this._panelOpen = false;
            return;
        }
        const href = this._safeHref(item.action_url);
        if (href) {
            window.location.href = href;
        }
    }

    _openMailFromNotification(item: NotificationItem): void {
        const data: Record<string, unknown> = item && item.data && typeof item.data === 'object' ? item.data : {};
        const bindingId = typeof data.mailbox_binding_id === 'string' ? data.mailbox_binding_id : '';
        const uid = typeof data.uid === 'string' ? data.uid : '';
        if (bindingId.length === 0 || uid.length === 0) {
            throw new Error('platform-notification-manager: mail notification requires mailbox_binding_id and uid');
        }
        this.dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.mail', props: {} });
        this.dispatch(MAIL_EVENTS.OPEN_FROM_NOTIFICATION, {
            mailbox_binding_id: bindingId,
            uid,
        });
    }

    _onActionClick(event: Event, item: NotificationItem): void {
        event.preventDefault();
        event.stopPropagation();
        this.dispatch(NOTIFICATIONS_EVENTS.READ, { id: item.id });
        if (item.scope === 'mail' && item.kind === 'mail_new_message') {
            this._openMailFromNotification(item);
            this._panelOpen = false;
            return;
        }
        this._panelOpen = false;
    }

    _dismissAll(): void {
        this.dispatch(NOTIFICATIONS_EVENTS.DISMISS_ALL, null);
    }

    _splitQualifiedKey(raw: string | null | undefined): { key: string; namespace?: string } | null {
        if (typeof raw !== 'string' || raw.length === 0) return null;
        const [nsOrKey, ...rest] = raw.split(':');
        if (rest.length === 0) return { key: raw, namespace: undefined };
        return { key: rest.join(':'), namespace: nsOrKey };
    }

    _translateKey(raw: string | null | undefined, vars?: Record<string, string | number>): string {
        const parsed = this._splitQualifiedKey(raw);
        if (!parsed) return '';
        const state = this._i18nSelect.value;
        if (!state) return '';
        return translate(state, parsed.key, mergePlatformI18nVars(vars), parsed.namespace);
    }

    _looksLikeI18nKey(value: unknown): boolean {
        return typeof value === 'string'
            && /^[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+|\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)$/i.test(value);
    }

    _resolveNotifText(item: NotificationItem, field: 'title' | 'message'): string {
        const i18nVars = notificationVars(item[`${field}_i18n_vars`], item.data);
        const text = typeof item[field] === 'string' ? item[field] : '';
        const keyRaw = item[`${field}_i18n_key`];
        const key = typeof keyRaw === 'string' ? keyRaw : '';
        const vars = i18nVars;
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

    _safeHref(raw: unknown): string {
        if (typeof raw !== 'string') return '';
        const href = raw.trim();
        if (href.length === 0) return '';
        if (href.startsWith('/') || href.startsWith('#')) return href;
        if (/^https?:\/\//i.test(href)) return href;
        return '';
    }

    _workItemIdFromNotification(item: NotificationItem): string {
        if (!item || item.service !== 'worktracker') {
            return '';
        }
        const href = this._safeHref(item.action_url);
        if (href.length === 0) {
            return '';
        }
        const queryIndex = href.indexOf('?');
        if (queryIndex === -1) {
            return '';
        }
        const params = new URLSearchParams(href.slice(queryIndex + 1));
        const workItemId = params.get('work_item_id');
        return typeof workItemId === 'string' ? workItemId : '';
    }

    _resolveActionLabel(action: Record<string, unknown>): string {
        const keyRaw = action.label_i18n_key;
        const key = typeof keyRaw === 'string' ? keyRaw : '';
        const vars = notificationVars(action.label_i18n_vars, action.data);
        if (key.length > 0) {
            const resolved = this._translateKey(key, vars);
            if (resolved.length > 0 && resolved !== key) return resolved;
        }
        const label = action.label;
        if (typeof label === 'string' && label.trim().length > 0) {
            return label.trim();
        }
        return this.t('notifications.open');
    }

    _actionFrom(raw: Record<string, unknown>, href: string): NotificationAction {
        const action: NotificationAction = {
            href,
            label: this._resolveActionLabel(raw),
        };
        if (typeof raw.url === 'string') action.url = raw.url;
        if (typeof raw.action_url === 'string' || raw.action_url === null) action.action_url = raw.action_url;
        if (typeof raw.label_i18n_key === 'string' || raw.label_i18n_key === null) action.label_i18n_key = raw.label_i18n_key;
        const vars = raw.label_i18n_vars;
        if (isPlainRecord(vars)) action.label_i18n_vars = vars;
        else if (vars === null) action.label_i18n_vars = null;
        if (isPlainRecord(raw.data)) action.data = raw.data;
        return action;
    }

    _notificationActions(item: NotificationItem): NotificationAction[] {
        const out: NotificationAction[] = [];
        const seen = new Set<string>();
        const add = (raw: unknown) => {
            if (!isPlainRecord(raw)) return;
            const href = this._safeHref(firstHref(raw));
            if (href.length === 0 || seen.has(href)) return;
            seen.add(href);
            out.push(this._actionFrom(raw, href));
        };
        if (item.scope === 'mail' && item.kind === 'mail_new_message') {
            add({
                url: '#mail',
                label_i18n_key: 'mail:notifications.open_message',
                label: 'Open message',
            });
            return out;
        }
        if (Array.isArray(item.actions)) {
            for (const action of item.actions) add(action);
        }
        add({
            url: presentString(item.action_url),
            label: item.action_label,
            label_i18n_key: presentString(item.action_label_i18n_key),
        });
        return out;
    }

    _renderPanel(): TemplateResult {
        const { list } = this._notifSelect.value;
        const title = this.t('notifications.title');
        const dismissAll = this.t('notifications.dismiss_all');
        const empty = this.t('notifications.empty');
        return html`
            <div class="platform-notif-portal">
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
                : list.map((n: NotificationItem) => {
                    const titleText = this._resolveNotifText(n, 'title');
                    const messageText = this._resolveNotifText(n, 'message');
                    const actions = this._notificationActions(n);
                    const workItemId = this._workItemIdFromNotification(n);
                    return html`
                        <div class="platform-notif-portal__item"
                             @click=${() => this._onItemClick(n)}>
                            ${titleText ? html`<div class="platform-notif-portal__item-title">${titleText}</div>` : ''}
                            ${workItemId.length > 0
                                ? html`<platform-work-item-badge
                                    work-item-id=${workItemId}
                                    variant="chip"
                                    size="sm"
                                    interactive
                                    ?show-preview=${false}
                                ></platform-work-item-badge>`
                                : (messageText
                                    ? html`<div class="platform-notif-portal__item-message">${messageText}</div>`
                                    : '')}
                            ${actions.length > 0 ? html`
                                <div class="platform-notif-portal__item-actions">
                                    ${actions.map((action) => html`
                                        <a class="platform-notif-portal__item-link"
                                           href=${action.href}
                                           @click=${(event: Event) => this._onActionClick(event, n)}>
                                            ${action.label}
                                        </a>
                                    `)}
                                </div>
                            ` : ''}
                            <div class="platform-notif-portal__item-meta">${n.scope}/${n.kind}</div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    override render(): TemplateResult {
        const { unread } = this._notifSelect.value;
        return html`
            <button class="bell"
                    @click=${this._togglePanel}
                    title=${this.t('notifications.title')}>
                <platform-icon name="bell" size="18"></platform-icon>
                ${unread > 0 ? html`<span class="badge">${unread > 99 ? '99+' : unread}</span>` : ''}
            </button>
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="top-start"
                offset=${PANEL_GAP}
                viewport-padding=${PANEL_VIEWPORT_PADDING}
                .anchor=${this._anchor}
                ?open=${this._panelOpen}
                @popover-dismiss=${this._onPopoverDismiss}
            >
                ${this._panelOpen ? this._renderPanel() : ''}
            </platform-popover>
        `;
    }
}

customElements.define('platform-notification-manager', PlatformNotificationManager);

/**
 * Менеджер уведомлений платформы.
 * 
 * Особенности:
 * - Автоматическое подключение к WebSocket
 * - Поддержка множественных вкладок (все получают уведомления)
 * - Авто-переподключение с exponential backoff
 * - Browser notifications при наличии разрешений
 * - Toast уведомления
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import './glass-toast.js';

export class PlatformNotificationManager extends PlatformElement {
    static properties = {
        notifications: { type: Array },
        unreadCount: { type: Number },
        isConnected: { type: Boolean },
        showPanel: { type: Boolean },
        _panelRect: { state: true },
    };

    constructor() {
        super();
        this.notifications = [];
        this.unreadCount = 0;
        this.isConnected = false;
        this.showPanel = false;
        this._panelRect = null;
        this._panelGlobalListeners = false;
        this._ws = null;
        this._reconnectAttempts = 0;
        this._maxReconnectAttempts = 5;
        this._heartbeatInterval = null;
        this._onSwMessage = this._onSwMessage.bind(this);
        this._onScrollOrResize = this._onScrollOrResize.bind(this);
        this._onDocumentPointerDown = this._onDocumentPointerDown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._connect();
        this._requestNotificationPermission();
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', this._onSwMessage);
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('notifications') && this.showPanel) {
            this._onScrollOrResize();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._detachPanelGlobalListeners();
        this._disconnect();
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.removeEventListener('message', this._onSwMessage);
        }
    }

    _computePanelRect(buttonEl) {
        const r = buttonEl.getBoundingClientRect();
        const width = Math.min(400, window.innerWidth - 16);
        let left = r.left;
        if (left + width > window.innerWidth - 8) {
            left = Math.max(8, window.innerWidth - width - 8);
        }
        const bottom = window.innerHeight - r.top + 8;
        return { left, bottom, width };
    }

    _onScrollOrResize() {
        if (!this.showPanel) {
            return;
        }
        const btn = this.shadowRoot?.querySelector('.notification-button');
        if (!btn) {
            return;
        }
        this._panelRect = this._computePanelRect(btn);
        this.requestUpdate();
    }

    _onDocumentPointerDown(e) {
        if (!this.showPanel) {
            return;
        }
        const path = e.composedPath();
        if (path.includes(this)) {
            return;
        }
        this.showPanel = false;
        this._panelRect = null;
        this._detachPanelGlobalListeners();
    }

    _attachPanelGlobalListeners() {
        if (this._panelGlobalListeners) {
            return;
        }
        window.addEventListener('resize', this._onScrollOrResize);
        window.addEventListener('scroll', this._onScrollOrResize, true);
        document.addEventListener('pointerdown', this._onDocumentPointerDown, true);
        this._panelGlobalListeners = true;
    }

    _detachPanelGlobalListeners() {
        if (!this._panelGlobalListeners) {
            return;
        }
        window.removeEventListener('resize', this._onScrollOrResize);
        window.removeEventListener('scroll', this._onScrollOrResize, true);
        document.removeEventListener('pointerdown', this._onDocumentPointerDown, true);
        this._panelGlobalListeners = false;
    }

    /**
     * Push из service worker: при открытой вкладке ОС часто не показывает баннер —
     * дублируем в список и toast (без второго вызова Notification API).
     */
    _onSwMessage(event) {
        if (event.data?.type !== 'humanitec-web-push' || !event.data?.payload) {
            return;
        }
        const p = event.data.payload;
        const notification = {
            title: p.title || 'Humanitec',
            message: p.message || '',
            type: p.tag || 'system',
            service: 'push',
            priority: p.priority || 'normal',
            created_at: new Date().toISOString(),
            data: typeof p.data === 'object' && p.data !== null ? p.data : {},
        };
        if (typeof p.url === 'string' && p.url) {
            notification.action_url = p.url;
        }
        this.notifications = [notification, ...this.notifications].slice(0, 50);
        this.unreadCount++;
        this._showToast(notification);
        this.requestUpdate();
        this._emitNotificationEvents(notification);
    }

    _emitNotificationEvents(notification) {
        this.dispatchEvent(
            new CustomEvent('notification-received', {
                detail: notification,
                bubbles: true,
                composed: true,
            })
        );
        window.dispatchEvent(
            new CustomEvent('platform-notification-received', {
                detail: notification,
            })
        );
    }

    _connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        
        // Определяем префикс сервиса из pathname (например /crm/, /flows/, /rag/)
        const pathname = window.location.pathname;
        const serviceMatch = pathname.match(/^\/([^\/]+)/);
        const servicePrefix = serviceMatch && !['static', 'api', 'ws'].includes(serviceMatch[1]) 
            ? `/${serviceMatch[1]}` 
            : '';
        
        const wsUrl = `${protocol}//${window.location.host}${servicePrefix}/ws/notifications`;
        console.log('[Notifications] Connecting to:', wsUrl);

        this._ws = new WebSocket(wsUrl);

        this._ws.onopen = () => {
            console.log('[Notifications] WebSocket подключен');
            this.isConnected = true;
            this._reconnectAttempts = 0;
            this._startHeartbeat();
        };

        this._ws.onmessage = (event) => {
            if (event.data === 'pong') return;

            try {
                const notification = JSON.parse(event.data);
                this._handleNotification(notification);
            } catch (e) {
                console.error('[Notifications] Ошибка парсинга:', e);
            }
        };

        this._ws.onerror = (error) => {
            console.error('[Notifications] Ошибка WebSocket:', error);
        };

        this._ws.onclose = () => {
            console.log('[Notifications] WebSocket отключен');
            this.isConnected = false;
            this._stopHeartbeat();
            this._reconnect();
        };
    }

    _disconnect() {
        if (this._ws) {
            this._ws.close();
            this._ws = null;
        }
        this._stopHeartbeat();
    }

    _reconnect() {
        if (this._reconnectAttempts >= this._maxReconnectAttempts) {
            console.error('[Notifications] Достигнут лимит попыток переподключения');
            return;
        }

        const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
        this._reconnectAttempts++;

        console.log(`[Notifications] Переподключение через ${delay}ms (попытка ${this._reconnectAttempts})`);
        setTimeout(() => this._connect(), delay);
    }

    _startHeartbeat() {
        this._heartbeatInterval = setInterval(() => {
            if (this._ws?.readyState === WebSocket.OPEN) {
                this._ws.send('ping');
            }
        }, 30000);
    }

    _stopHeartbeat() {
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
            this._heartbeatInterval = null;
        }
    }

    _requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    _handleNotification(notification) {
        this.notifications = [notification, ...this.notifications].slice(0, 50);
        this.unreadCount++;

        this._showToast(notification);

        if (Notification.permission === 'granted') {
            new Notification(notification.title, {
                body: notification.message,
                icon: '/assets/icon-192.png',
                tag: notification.type,
                data: notification.data
            });
        }

        this._emitNotificationEvents(notification);
    }

    _showToast(notification) {
        const toast = document.createElement('glass-toast');
        toast.message = `${notification.title}: ${notification.message}`;
        toast.type = (notification.priority === 'urgent' || notification.priority === 'high') ? 'warning' : 'info';
        toast.duration = 5000;
        document.body.appendChild(toast);
    }

    _togglePanel() {
        if (this.showPanel) {
            this.showPanel = false;
            this._panelRect = null;
            this._detachPanelGlobalListeners();
            return;
        }
        const btn = this.shadowRoot?.querySelector('.notification-button');
        if (btn) {
            this._panelRect = this._computePanelRect(btn);
        }
        this.showPanel = true;
        this._attachPanelGlobalListeners();
    }

    _markAsRead(index) {
        if (this.notifications[index] && !this.notifications[index].read) {
            this.notifications[index].read = true;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.requestUpdate();
        }
    }

    _clearAll() {
        this.notifications = [];
        this.unreadCount = 0;
        this.showPanel = false;
        this._panelRect = null;
        this._detachPanelGlobalListeners();
    }

    _handleNotificationClick(notification, index) {
        this._markAsRead(index);
        if (notification.action_url) {
            window.location.href = notification.action_url;
        }
    }

    render() {
        return html`
            <div class="notification-container">
                <button 
                    class="notification-button" 
                    @click=${this._togglePanel}
                    title="Уведомления"
                >
                    <platform-icon name="bell" size="20"></platform-icon>
                    <span class="status ${this.isConnected ? 'connected' : 'disconnected'}"></span>
                    ${this.unreadCount > 0 ? html`
                        <span class="badge">${this.unreadCount}</span>
                    ` : ''}
                </button>

                ${this.showPanel && this._panelRect ? html`
                    <div
                        class="notification-panel"
                        style="left: ${this._panelRect.left}px; bottom: ${this._panelRect.bottom}px; width: ${this._panelRect.width}px;"
                    >
                        <div class="panel-header">
                            <h3>Уведомления</h3>
                            ${this.notifications.length > 0 ? html`
                                <button @click=${this._clearAll} class="clear-btn">Очистить</button>
                            ` : ''}
                        </div>
                        
                        <div class="panel-body">
                            ${this.notifications.length === 0 ? html`
                                <div class="empty-state">
                                    <p>Нет уведомлений</p>
                                </div>
                            ` : this.notifications.map((notif, index) => html`
                                <div 
                                    class="notification-item ${notif.read ? 'read' : 'unread'}"
                                    @click=${() => this._handleNotificationClick(notif, index)}
                                >
                                    <div class="notif-header">
                                        <strong>${notif.title}</strong>
                                        <span class="service-badge">${notif.service}</span>
                                    </div>
                                    <p>${notif.message}</p>
                                    <span class="timestamp">
                                        ${new Date(notif.created_at).toLocaleString('ru')}
                                    </span>
                                </div>
                            `)}
                        </div>
                    </div>
                ` : ''}
            </div>

        `;
    }

    static styles = css`
        :host {
            display: inline-block;
            position: relative;
        }

        .notification-container {
            position: relative;
        }

        .notification-button {
            position: relative;
            background: transparent;
            border: none;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            transition: background 0.2s;
        }

        .notification-button:hover {
            background: var(--hover-color);
        }

        platform-icon {
            color: var(--text-secondary);
        }

        .status {
            position: absolute;
            bottom: 8px;
            right: 8px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--error-color);
        }

        .status.connected {
            background: var(--success-color);
        }

        .badge {
            position: absolute;
            top: 4px;
            right: 4px;
            background: var(--error-color);
            color: white;
            border-radius: 10px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: bold;
            min-width: 18px;
            text-align: center;
        }

        .notification-panel {
            position: fixed;
            max-height: min(600px, 70vh);
            background: var(--bg-tertiary, #1e2a47);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: var(--z-notification-panel, 30000);
            display: flex;
            flex-direction: column;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
        }

        .panel-header h3 {
            margin: 0;
            font-size: 16px;
        }

        .clear-btn {
            background: transparent;
            border: 1px solid var(--border-color);
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }

        .clear-btn:hover {
            background: var(--hover-color);
        }

        .panel-body {
            overflow-y: auto;
            max-height: 500px;
        }

        .empty-state {
            padding: 40px 20px;
            text-align: center;
            color: var(--text-secondary);
        }

        .notification-item {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
            transition: background 0.2s;
        }

        .notification-item:hover {
            background: var(--hover-color);
        }

        .notification-item.unread {
            background: var(--surface-elevated);
        }

        .notif-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
        }

        .notif-header strong {
            font-size: 14px;
        }

        .service-badge {
            font-size: 10px;
            padding: 2px 6px;
            background: var(--primary-color);
            color: white;
            border-radius: 4px;
            text-transform: uppercase;
        }

        .notification-item p {
            margin: 4px 0;
            font-size: 13px;
            color: var(--text-secondary);
        }

        .timestamp {
            font-size: 11px;
            color: var(--text-tertiary);
        }
    `;
}

customElements.define('platform-notification-manager', PlatformNotificationManager);


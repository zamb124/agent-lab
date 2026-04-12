/**
 * Рабочее место оператора: канбан по статусам и панель диалога.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';

const STATUSES = ['open', 'claimed', 'user_dialog', 'awaiting_agent', 'completed', 'cancelled'];

export class OperatorWorkbenchPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                min-width: 0;
                height: 100%;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                overflow: hidden;
            }
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .header-start {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }
            .header-icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 38px;
                height: 38px;
                padding: 0;
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                cursor: pointer;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast),
                    box-shadow var(--duration-fast),
                    transform var(--duration-fast);
            }
            .header-icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .header-icon-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .back-to-flows {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                text-decoration: none;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .back-to-flows:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .header-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                min-width: 0;
                flex: 1;
            }
            .body {
                display: flex;
                flex-direction: row-reverse;
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            .kanban {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                gap: var(--space-3);
                padding: var(--space-3);
                overflow-x: auto;
                transition: flex-basis 0.28s var(--easing-default);
            }
            .body.has-selection .kanban {
                flex: 0 0 33.333%;
                max-width: 33.333%;
            }
            .column {
                min-width: 200px;
                max-width: 240px;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .column-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
            }
            .card {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
                cursor: pointer;
                font-size: var(--text-sm);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                text-align: left;
            }
            .card.selected {
                border-color: var(--accent);
                box-shadow: 0 0 0 2px var(--accent-glow);
            }
            .card-headline {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.35;
            }
            .card-tech {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
                line-height: 1.3;
            }
            .card-handoff-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            .card-handoff-preview {
                font-size: var(--text-xs);
                font-weight: var(--font-normal);
                color: var(--text-tertiary);
                line-height: 1.45;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            .detail {
                flex: 0 0 clamp(260px, 30vw, 400px);
                max-width: min(400px, 100%);
                border-left: 1px solid var(--border-subtle);
                display: flex;
                flex-direction: column;
                min-height: 0;
                min-width: 0;
                background: var(--glass-tint-subtle);
                box-shadow: -8px 0 24px rgba(0, 0, 0, 0.06);
                transition:
                    flex-basis 0.28s var(--easing-default),
                    max-width 0.28s var(--easing-default),
                    box-shadow 0.28s var(--easing-default);
            }
            :host-context([data-theme='dark']) .detail {
                box-shadow: -8px 0 32px rgba(0, 0, 0, 0.35);
            }
            .body.has-selection .detail {
                flex: 0 0 66.666%;
                max-width: 66.666%;
                box-shadow: -12px 0 40px rgba(0, 0, 0, 0.08);
            }
            :host-context([data-theme='dark']) .body.has-selection .detail {
                box-shadow: -12px 0 48px rgba(0, 0, 0, 0.45);
            }

            /* --- detail toolbar --- */
            .detail-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
                background: var(--glass-solid-subtle);
                position: relative;
            }
            .detail-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1;
            }
            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .toolbar-icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                padding: 0;
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid transparent;
                cursor: pointer;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast);
            }
            .toolbar-icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .toolbar-icon-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .toolbar-icon-btn--active {
                color: var(--accent);
                background: var(--glass-tint-medium);
            }

            /* --- task data popover --- */
            .task-data-popover {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                z-index: var(--z-dropdown, 1000);
                max-height: 60vh;
                overflow-y: auto;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-subtle);
                border-top: none;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
                padding: var(--space-3);
            }
            :host-context([data-theme='dark']) .task-data-popover {
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            }
            .task-data-mono {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                white-space: pre-wrap;
                word-break: break-word;
                color: var(--text-secondary);
                line-height: 1.5;
            }

            /* --- question block --- */
            .task-question {
                padding: var(--space-3) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                line-height: 1.5;
                white-space: pre-wrap;
                word-break: break-word;
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
                background: var(--glass-tint-subtle);
            }

            /* --- detail inner (contains dialog + composer) --- */
            .detail-inner {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }
            .detail-inner--empty {
                align-items: center;
                justify-content: center;
                overflow: auto;
            }
            .detail-empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
                line-height: 1.5;
            }
            .detail-loading {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 12rem;
            }

            /* --- dialog area (chat messages) --- */
            .dialog-area {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow-y: auto;
                padding: var(--space-3) var(--space-4);
            }
            .dialog-empty {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-3);
            }
            .dialog-section-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                padding: var(--space-2) 0 var(--space-1) 0;
            }
            .dialog-separator {
                border: none;
                border-top: 1px dashed var(--border-subtle);
                margin: var(--space-2) 0;
            }
            .dialog-entry {
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                line-height: 1.45;
            }
            .dialog-entry--operator {
                background: var(--accent-subtle);
                align-self: flex-end;
                max-width: 85%;
            }
            .dialog-entry--user {
                background: var(--glass-tint-medium);
                align-self: flex-start;
                max-width: 85%;
            }
            .dialog-entry--agent {
                background: var(--glass-tint-light, rgba(255,255,255,0.06));
                align-self: flex-end;
                max-width: 85%;
                border: 1px solid var(--border-subtle);
            }
            .dialog-role {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .dialog-text {
                white-space: pre-wrap;
                word-break: break-word;
            }

            /* --- composer (capsule input) --- */
            .composer {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                margin: var(--space-2) var(--space-3) var(--space-3);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                flex-shrink: 0;
                transition: border-color var(--duration-fast);
            }
            .composer:focus-within {
                border-color: var(--accent);
            }
            .composer-input {
                flex: 1;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                line-height: 1.5;
                padding: var(--space-1) 0;
                outline: none;
                resize: none;
            }
            .composer-input::placeholder {
                color: var(--text-tertiary);
            }
            .composer-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                padding: 0;
                border-radius: 50%;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                flex-shrink: 0;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast),
                    transform var(--duration-fast);
            }
            .composer-btn:hover:not(:disabled) {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            .composer-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .composer-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }
            .composer-btn--send {
                background: var(--accent);
                color: var(--text-primary);
            }
            .composer-btn--send:hover:not(:disabled) {
                background: var(--accent-hover);
                transform: scale(1.05);
            }
            .composer-btn--complete {
                background: var(--success);
                color: var(--text-primary);
            }
            .composer-btn--complete:hover:not(:disabled) {
                filter: brightness(1.15);
                transform: scale(1.05);
            }

            /* --- pending files strip --- */
            .pending-files {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3) 0;
                margin: 0 var(--space-3);
            }
            .pending-file {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                max-width: 200px;
            }
            .pending-file-name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }
            .pending-file-remove {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 16px;
                height: 16px;
                padding: 0;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            .pending-file-remove:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }
            /* --- file card in dialog --- */
            .dialog-file-card {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                margin-top: var(--space-1);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-xs);
                color: var(--accent);
                text-decoration: none;
                max-width: 100%;
                cursor: pointer;
            }
            .dialog-file-card:hover {
                background: var(--glass-solid-medium);
            }
            .dialog-file-card platform-icon {
                flex-shrink: 0;
            }
            .dialog-file-card-name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }

            /* --- claim area --- */
            .claim-area {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-3) var(--space-4);
                flex-shrink: 0;
            }

            /* --- queues panel --- */
            .queues-panel {
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            .queues-panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            .queues-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                min-height: 1.5rem;
            }
            .queue-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-xs);
            }
            .queue-chip-main {
                display: inline-flex;
                align-items: baseline;
                gap: var(--space-2);
                min-width: 0;
            }
            .queue-chip-slug {
                font-family: var(--font-mono);
                color: var(--accent);
            }
            .queue-chip-join {
                flex-shrink: 0;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border-radius: var(--radius-sm);
                color: var(--accent);
                background: transparent;
                border: 1px solid var(--accent);
                cursor: pointer;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast);
            }
            .queue-chip-join:hover {
                background: var(--accent-glow);
                color: var(--text-primary);
            }
            .queue-chip-join:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .queue-chip-leave {
                flex-shrink: 0;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid var(--border-subtle);
                cursor: pointer;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast),
                    border-color var(--duration-fast);
            }
            .queue-chip-leave:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                border-color: var(--glass-border-medium);
            }
            .queue-chip-leave:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .queues-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .queues-form {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-end;
                gap: var(--space-2);
            }
            .queues-form glass-input {
                flex: 1;
                min-width: 140px;
            }
            @media (max-width: 768px) {
                .body.has-selection {
                    flex-direction: column-reverse;
                }
                .body.has-selection .kanban {
                    flex: 0 0 auto;
                    max-width: none;
                    width: 100%;
                    max-height: 36vh;
                    overflow-y: auto;
                    overflow-x: auto;
                }
                .body.has-selection .detail {
                    flex: 1 1 auto;
                    max-width: none;
                    width: 100%;
                    min-height: 0;
                    border-left: none;
                    border-top: 1px solid var(--border-subtle);
                    box-shadow: none;
                }
            }
        `,
    ];

    static properties = {
        loading: { type: Boolean },
        tasks: { type: Array },
        selectedId: { type: String, attribute: false },
        detail: { type: Object, attribute: false },
        detailLoading: { type: Boolean, attribute: false },
        composerDraft: { type: String, attribute: false },
        _taskDataOpen: { state: true },
        _pendingFiles: { state: true },
        _uploadingFiles: { state: true },
        queues: { type: Array },
        newQueueName: { type: String, attribute: false },
        newQueueSlug: { type: String, attribute: false },
        queuesLoading: { type: Boolean },
    };

    constructor() {
        super();
        this.loading = false;
        this.tasks = [];
        this.selectedId = '';
        this.detail = null;
        this.detailLoading = false;
        this.composerDraft = '';
        this._taskDataOpen = false;
        this._pendingFiles = [];
        this._uploadingFiles = false;
        this.queues = [];
        this.newQueueName = '';
        this.newQueueSlug = '';
        this.queuesLoading = false;
        this._operatorWs = null;
        this._operatorWsHeartbeat = null;
        this._operatorWsReconnectAttempts = 0;
        this._operatorWsIntentionalClose = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._onThemeChange = () => this.requestUpdate();
        window.addEventListener(AppEvents.THEME_CHANGE, this._onThemeChange);
        this._operatorWsIntentionalClose = false;
        this._connectOperatorTasksWs();
        void this._loadQueues();
        void this._loadTasks();
    }

    disconnectedCallback() {
        this._operatorWsIntentionalClose = true;
        this._disconnectOperatorTasksWs();
        window.removeEventListener(AppEvents.THEME_CHANGE, this._onThemeChange);
        super.disconnectedCallback();
    }

    _connectOperatorTasksWs() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const pathname = window.location.pathname;
        const serviceMatch = pathname.match(/^\/([^/]+)/);
        const servicePrefix =
            serviceMatch && !['static', 'api', 'ws'].includes(serviceMatch[1])
                ? `/${serviceMatch[1]}`
                : '';
        const wsUrl = `${protocol}//${window.location.host}${servicePrefix}/ws/notifications`;

        this._disconnectOperatorTasksWs();
        this._operatorWsIntentionalClose = false;

        const ws = new WebSocket(wsUrl);
        this._operatorWs = ws;

        ws.onopen = () => {
            this._operatorWsReconnectAttempts = 0;
            this._stopOperatorWsHeartbeat();
            this._operatorWsHeartbeat = setInterval(() => {
                if (this._operatorWs?.readyState === WebSocket.OPEN) {
                    this._operatorWs.send('ping');
                }
            }, 30000);
        };

        ws.onmessage = (event) => {
            this._onOperatorTasksWsMessage(event);
        };

        ws.onerror = (err) => {
            console.error('[OperatorWorkbench] WebSocket error', err);
        };

        ws.onclose = () => {
            this._stopOperatorWsHeartbeat();
            this._operatorWs = null;
            if (!this._operatorWsIntentionalClose && this.isConnected) {
                this._scheduleOperatorTasksWsReconnect();
            }
        };
    }

    _disconnectOperatorTasksWs() {
        this._stopOperatorWsHeartbeat();
        const ws = this._operatorWs;
        if (ws) {
            this._operatorWs = null;
            ws.onclose = null;
            ws.close();
        }
    }

    _stopOperatorWsHeartbeat() {
        if (this._operatorWsHeartbeat) {
            clearInterval(this._operatorWsHeartbeat);
            this._operatorWsHeartbeat = null;
        }
    }

    _scheduleOperatorTasksWsReconnect() {
        if (this._operatorWsReconnectAttempts >= 8) {
            return;
        }
        this._operatorWsReconnectAttempts += 1;
        const delay = Math.min(1000 * 2 ** (this._operatorWsReconnectAttempts - 1), 30000);
        setTimeout(() => {
            if (!this.isConnected || this._operatorWsIntentionalClose) {
                return;
            }
            this._connectOperatorTasksWs();
        }, delay);
    }

    _onOperatorTasksWsMessage(event) {
        if (event.data === 'pong') {
            return;
        }
        let notification;
        try {
            notification = JSON.parse(event.data);
        } catch {
            return;
        }
        if (notification?.type !== 'flows_operator_tasks_updated') {
            return;
        }
        void this._refreshOperatorTasksFromPush();
    }

    async _refreshOperatorTasksFromPush() {
        const sid = this.selectedId;
        if (!this.a2a) {
            return;
        }
        try {
            const res = await this.a2a.listOperatorTasks({ limit: 200, offset: 0 });
            this.tasks = res.items || [];
        } catch (err) {
            console.error('[OperatorWorkbench] Failed to refresh tasks', err);
            return;
        }
        if (!sid) {
            this.requestUpdate();
            return;
        }
        if (!this.tasks.some((t) => t.id === sid)) {
            this._closeTaskDetail();
            this.requestUpdate();
            return;
        }
        try {
            this.detail = await this.a2a.getOperatorTask(sid);
        } catch (err) {
            console.error('[OperatorWorkbench] Failed to refresh task detail', err);
            this._closeTaskDetail();
        }
        this.requestUpdate();
    }

    _toggleWorkbenchTheme() {
        this.theme?.toggle();
    }

    _closeTaskDetail() {
        this.selectedId = '';
        this.detail = null;
        this.detailLoading = false;
        this.composerDraft = '';
        this._taskDataOpen = false;
        this._pendingFiles = [];
        this._uploadingFiles = false;
    }

    get a2a() {
        return this.services?.a2a;
    }

    async _loadQueues() {
        if (!this.a2a) return;
        this.queuesLoading = true;
        try {
            const page = await this.a2a.listOperatorQueues();
            this.queues = page?.items ?? [];
        } catch (e) {
            this.error(e?.message || String(e));
            this.queues = [];
        } finally {
            this.queuesLoading = false;
        }
    }

    async _createQueue() {
        if (!this.a2a) return;
        const name = String(this.newQueueName || '').trim();
        const slug = String(this.newQueueSlug || '').trim();
        if (!name) {
            this.error(this.i18n.t('operator.err_queue_name_required'));
            return;
        }
        if (!slug) {
            this.error(this.i18n.t('operator.err_queue_slug_required'));
            return;
        }
        try {
            await this.a2a.createOperatorQueue({ name, slug });
            this.newQueueName = '';
            this.newQueueSlug = '';
            await this._loadQueues();
            await this._loadTasks();
            this.success(this.i18n.t('operator.msg_queue_created'));
        } catch (e) {
            this.error(e?.message || String(e));
        }
    }

    async _joinOperatorQueue(queueId) {
        if (!this.a2a || !queueId) return;
        const uid = this.auth?.user?.id;
        if (!uid) {
            this.error(this.i18n.t('operator.err_join_queue_auth'));
            return;
        }
        try {
            await this.a2a.addOperatorQueueMember(queueId, { user_id: String(uid), role: 'agent' });
            await this._loadQueues();
            await this._loadTasks();
            this.success(this.i18n.t('operator.msg_joined_queue'));
        } catch (e) {
            this.error(e?.message || String(e));
        }
    }

    async _leaveOperatorQueue(queueId) {
        if (!this.a2a || !queueId) return;
        const uid = this.auth?.user?.id;
        if (!uid) {
            this.error(this.i18n.t('operator.err_leave_queue_auth'));
            return;
        }
        const previousSelectedId = this.selectedId;
        try {
            await this.a2a.removeOperatorQueueMember(queueId, String(uid));
            await this._loadQueues();
            await this._loadTasks();
            if (
                previousSelectedId &&
                !this.tasks.some((t) => t.id === previousSelectedId)
            ) {
                this._closeTaskDetail();
            }
            this.success(this.i18n.t('operator.msg_left_queue'));
        } catch (e) {
            this.error(e?.message || String(e));
        }
    }

    async _loadTasks() {
        if (!this.a2a) return;
        this.loading = true;
        try {
            const res = await this.a2a.listOperatorTasks({ limit: 200, offset: 0 });
            this.tasks = res.items || [];
        } catch (e) {
            this.error(e?.message || String(e));
            this.tasks = [];
        } finally {
            this.loading = false;
        }
    }

    async _selectTask(taskId) {
        this.selectedId = taskId;
        this.detail = null;
        if (!this.a2a || !taskId) {
            this.detailLoading = false;
            return;
        }
        this.detailLoading = true;
        try {
            this.detail = await this.a2a.getOperatorTask(taskId);
        } catch (e) {
            this.error(e?.message || String(e));
            this.selectedId = '';
        } finally {
            this.detailLoading = false;
        }
    }

    async _claim() {
        if (!this.a2a || !this.selectedId) return;
        try {
            await this.a2a.claimOperatorTask(this.selectedId);
            await this._loadTasks();
            await this._selectTask(this.selectedId);
            this.success(this.i18n.t('operator.msg_claimed'));
        } catch (e) {
            this.error(e?.message || String(e));
        }
    }

    _onAttachClick() {
        const input = this.renderRoot?.querySelector('#operator-file-input');
        if (input) input.click();
    }

    _onFilesSelected(e) {
        const files = Array.from(e.target.files || []);
        if (!files.length) return;
        this._pendingFiles = [...this._pendingFiles, ...files];
        e.target.value = '';
    }

    _removePendingFile(index) {
        this._pendingFiles = this._pendingFiles.filter((_, i) => i !== index);
    }

    async _uploadPendingFiles() {
        if (!this._pendingFiles.length || !this.a2a) return [];
        this._uploadingFiles = true;
        const ids = [];
        for (const file of this._pendingFiles) {
            const resp = await this.a2a.uploadFile(file);
            if (!resp?.file_id) {
                throw new Error(this.i18n.t('operator.file_upload_failed'));
            }
            ids.push(resp.file_id);
        }
        this._uploadingFiles = false;
        return ids;
    }

    async _composerSend() {
        const text = this.composerDraft.trim();
        if (!this.a2a || !this.selectedId || (!text && !this._pendingFiles.length)) return;
        const mode = this._detailHandoffMode();
        if (mode === 'takeover') {
            try {
                const fileIds = await this._uploadPendingFiles();
                await this.a2a.postOperatorTaskMessage(this.selectedId, text || ' ', fileIds);
                this.composerDraft = '';
                this._pendingFiles = [];
                this.success(this.i18n.t('operator.msg_sent'));
            } catch (e) {
                this._uploadingFiles = false;
                this.error(e?.message || String(e));
            }
        } else {
            await this._composerComplete();
        }
    }

    async _composerComplete() {
        const text = this.composerDraft.trim();
        if (!this.a2a || !this.selectedId || !text) return;
        try {
            const fileIds = await this._uploadPendingFiles();
            await this.a2a.completeOperatorTask(this.selectedId, text, fileIds);
            this.composerDraft = '';
            this._pendingFiles = [];
            await this._loadTasks();
            this._closeTaskDetail();
            this.success(this.i18n.t('operator.msg_completed'));
        } catch (e) {
            this._uploadingFiles = false;
            this.error(e?.message || String(e));
        }
    }

    _toggleTaskData() {
        this._taskDataOpen = !this._taskDataOpen;
    }

    _tasksByStatus(st) {
        return this.tasks.filter((t) => t.status === st);
    }

    _taskCardHeadline(t) {
        const flow = t.flow_display_name || t.flow_id || '';
        const skill = t.skill_display_name || t.skill_id || '';
        if (!flow && !skill) return '';
        return `${flow} [${skill}]`;
    }

    _taskCardHandoffTitle(t) {
        const raw = t.handoff_title;
        if (raw != null && String(raw).trim()) {
            return String(raw).trim();
        }
        return this.i18n.t('operator.card_no_title');
    }

    _selectedTaskSummary() {
        const task = this.detail?.task;
        if (!task) return '';
        const title =
            task.handoff_title != null && String(task.handoff_title).trim()
                ? String(task.handoff_title).trim()
                : this.i18n.t('operator.card_no_title');
        const head = this._taskCardHeadline(task);
        return head ? `${title} — ${head}` : title;
    }

    _detailHandoffMode() {
        return this.detail?.task?.handoff_mode || 'single_reply';
    }

    _extractMessageText(msg) {
        if (!msg || !msg.parts) return '';
        return msg.parts
            .filter((p) => p.kind === 'text' && p.text)
            .map((p) => p.text)
            .join('\n');
    }

    _chatHistoryEntries() {
        const raw = this.detail?.dialog_messages || [];
        const entries = [];
        for (const msg of raw) {
            const role = msg.role;
            if (role !== 'user' && role !== 'agent') continue;
            const md = msg.metadata || {};
            if (md.tool_calls || md.tool_call_id || md.system) continue;
            const text = this._extractMessageText(msg);
            if (!text.trim()) continue;
            entries.push({ role, text });
        }
        return entries;
    }

    _roleLabelForHistory(role) {
        if (role === 'user') return this.i18n.t('operator.role_user');
        return this.i18n.t('operator.role_agent');
    }

    _renderDialogArea() {
        const history = this._chatHistoryEntries();
        const log = this.detail?.dialog_log || [];
        const hasHistory = history.length > 0;
        const hasLog = log.length > 0;

        if (!hasHistory && !hasLog) {
            return html`
                <div class="dialog-area">
                    <div class="dialog-empty">${this.i18n.t('operator.takeover_no_messages')}</div>
                </div>
            `;
        }

        return html`
            <div class="dialog-area">
                ${hasHistory
                    ? html`
                          <div class="dialog-section-label">${this.i18n.t('operator.section_chat_history')}</div>
                          ${history.map(
                              (e) => html`
                                  <div class="dialog-entry dialog-entry--${e.role === 'user' ? 'user' : 'agent'}">
                                      <span class="dialog-role">${this._roleLabelForHistory(e.role)}</span>
                                      <span class="dialog-text">${e.text}</span>
                                  </div>
                              `,
                          )}
                      `
                    : ''}
                ${hasHistory && hasLog ? html`<hr class="dialog-separator" />` : ''}
                ${hasLog
                    ? html`
                          <div class="dialog-section-label">${this.i18n.t('operator.section_operator_dialog')}</div>
                          ${log.map(
                              (entry) => html`
                                  <div class="dialog-entry dialog-entry--${entry.role}">
                                      <span class="dialog-role">
                                          ${entry.role === 'operator'
                                              ? this.i18n.t('operator.role_operator')
                                              : this.i18n.t('operator.role_user')}
                                      </span>
                                      <span class="dialog-text">${entry.text}</span>
                                      ${(entry.file_ids || []).map(
                                          (fid) => html`
                                              <a
                                                  class="dialog-file-card"
                                                  href="/flows/api/v1/files/download/${fid}"
                                                  target="_blank"
                                                  rel="noopener"
                                              >
                                                  <platform-icon name="file" size="14"></platform-icon>
                                                  <span class="dialog-file-card-name">${this.i18n.t('operator.download_file')}</span>
                                              </a>
                                          `,
                                      )}
                                  </div>
                              `,
                          )}
                      `
                    : ''}
            </div>
        `;
    }

    _renderComposer() {
        const status = this.detail?.task?.status;
        if (status === 'open') {
            return html`
                <div class="claim-area">
                    <glass-button @click=${() => void this._claim()}>
                        ${this.i18n.t('operator.btn_claim')}
                    </glass-button>
                </div>
            `;
        }

        const mode = this._detailHandoffMode();
        const sendTooltip = mode === 'takeover'
            ? this.i18n.t('operator.tooltip_reply')
            : this.i18n.t('operator.tooltip_reply');
        const placeholder = mode === 'takeover'
            ? this.i18n.t('operator.placeholder_composer')
            : this.i18n.t('operator.placeholder_single_reply');

        const hasDraft = this.composerDraft.trim() || this._pendingFiles.length > 0;

        return html`
            ${this._pendingFiles.length > 0
                ? html`
                      <div class="pending-files">
                          ${this._pendingFiles.map(
                              (f, i) => html`
                                  <span class="pending-file">
                                      <platform-icon name="file" size="12"></platform-icon>
                                      <span class="pending-file-name">${f.name}</span>
                                      <button
                                          type="button"
                                          class="pending-file-remove"
                                          @click=${() => this._removePendingFile(i)}
                                      >
                                          <platform-icon name="close" size="10"></platform-icon>
                                      </button>
                                  </span>
                              `,
                          )}
                      </div>
                  `
                : ''}
            <input
                type="file"
                id="operator-file-input"
                multiple
                hidden
                @change=${(e) => this._onFilesSelected(e)}
            />
            <div class="composer">
                <button
                    type="button"
                    class="composer-btn"
                    title=${this.i18n.t('operator.tooltip_attach_file')}
                    aria-label=${this.i18n.t('operator.tooltip_attach_file')}
                    ?disabled=${this._uploadingFiles}
                    @click=${() => this._onAttachClick()}
                >
                    <platform-icon name="paperclip" size="18"></platform-icon>
                </button>
                <input
                    type="text"
                    class="composer-input"
                    placeholder=${placeholder}
                    .value=${this.composerDraft}
                    @input=${(e) => { this.composerDraft = e.target.value; }}
                    @keydown=${(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            void this._composerSend();
                        }
                    }}
                />
                <button
                    type="button"
                    class="composer-btn composer-btn--send"
                    title=${sendTooltip}
                    aria-label=${sendTooltip}
                    ?disabled=${!hasDraft || this._uploadingFiles}
                    @click=${() => void this._composerSend()}
                >
                    <platform-icon name="send" size="18"></platform-icon>
                </button>
                ${mode === 'takeover'
                    ? html`
                          <button
                              type="button"
                              class="composer-btn composer-btn--complete"
                              title=${this.i18n.t('operator.tooltip_reply_and_close')}
                              aria-label=${this.i18n.t('operator.tooltip_reply_and_close')}
                              ?disabled=${!this.composerDraft.trim() || this._uploadingFiles}
                              @click=${() => void this._composerComplete()}
                          >
                              <platform-icon name="check" size="18"></platform-icon>
                          </button>
                      `
                    : ''}
            </div>
        `;
    }

    render() {
        const hasSelection = Boolean(this.selectedId);
        const themeBtnTitle = this.theme?.isDark
            ? this.i18n.t('operator.theme_to_light')
            : this.i18n.t('operator.theme_to_dark');
        const themeIcon = this.theme?.isDark ? 'sun' : 'moon';

        return html`
            <div class="header">
                <div class="header-start">
                    <a class="back-to-flows" href="/flows/example_react">
                        <platform-icon name="arrow-left" size="16"></platform-icon>
                        <span>${this.i18n.t('flows_sidebar.back_to_flows')}</span>
                    </a>
                    <button
                        type="button"
                        class="header-icon-btn"
                        title=${themeBtnTitle}
                        aria-label=${themeBtnTitle}
                        @click=${() => this._toggleWorkbenchTheme()}
                    >
                        <platform-icon name=${themeIcon} size="18"></platform-icon>
                    </button>
                </div>
                <span class="header-title">${this.i18n.t('operator.page_title')}</span>
            </div>
            <div class="queues-panel">
                <div class="queues-panel-title">${this.i18n.t('operator.queues_title')}</div>
                <div class="queues-list">
                    ${this.queuesLoading
                        ? html`<glass-spinner></glass-spinner>`
                        : this.queues.length === 0
                          ? html`<span class="queues-empty">${this.i18n.t('operator.queues_empty')}</span>`
                          : this.queues.map(
                                (q) => html`
                                    <span class="queue-chip">
                                        <span class="queue-chip-main">
                                            <span>${q.name}</span>
                                            <span class="queue-chip-slug">${q.slug}</span>
                                        </span>
                                        ${q.i_am_member
                                            ? html`
                                                  <button
                                                      type="button"
                                                      class="queue-chip-leave"
                                                      @click=${() => void this._leaveOperatorQueue(q.id)}
                                                  >
                                                      ${this.i18n.t('operator.btn_leave_queue')}
                                                  </button>
                                              `
                                            : html`
                                                  <button
                                                      type="button"
                                                      class="queue-chip-join"
                                                      @click=${() => void this._joinOperatorQueue(q.id)}
                                                  >
                                                      ${this.i18n.t('operator.btn_join_queue')}
                                                  </button>
                                              `}
                                    </span>
                                `,
                            )}
                </div>
                <div class="queues-form">
                    <glass-input
                        .value=${this.newQueueName}
                        placeholder=${this.i18n.t('operator.queue_name_placeholder')}
                        @input=${(e) => {
                            this.newQueueName = e.detail?.value ?? e.target.value;
                        }}
                    ></glass-input>
                    <glass-input
                        .value=${this.newQueueSlug}
                        placeholder=${this.i18n.t('operator.queue_slug_placeholder')}
                        @input=${(e) => {
                            this.newQueueSlug = e.detail?.value ?? e.target.value;
                        }}
                    ></glass-input>
                    <glass-button @click=${() => void this._createQueue()}>
                        ${this.i18n.t('operator.queue_create')}
                    </glass-button>
                </div>
            </div>
            <div class="body ${hasSelection ? 'has-selection' : ''}">
                <div class="detail">
                    ${hasSelection
                        ? html`
                              <div class="detail-toolbar">
                                  <span class="detail-title">
                                      ${this.detailLoading
                                          ? this.i18n.t('operator.detail_loading')
                                          : this._selectedTaskSummary()}
                                  </span>
                                  <div class="toolbar-actions">
                                      ${this.detail
                                          ? html`
                                                <button
                                                    type="button"
                                                    class="toolbar-icon-btn ${this._taskDataOpen ? 'toolbar-icon-btn--active' : ''}"
                                                    title=${this._taskDataOpen
                                                        ? this.i18n.t('operator.tooltip_hide_task_data')
                                                        : this.i18n.t('operator.tooltip_show_task_data')}
                                                    aria-label=${this.i18n.t('operator.task_payload_label')}
                                                    @click=${() => this._toggleTaskData()}
                                                >
                                                    <platform-icon name="info" size="16"></platform-icon>
                                                </button>
                                            `
                                          : ''}
                                      <button
                                          type="button"
                                          class="toolbar-icon-btn"
                                          title=${this.i18n.t('operator.btn_close_panel')}
                                          aria-label=${this.i18n.t('operator.btn_close_panel')}
                                          @click=${() => this._closeTaskDetail()}
                                      >
                                          <platform-icon name="close" size="16"></platform-icon>
                                      </button>
                                  </div>
                                  ${this._taskDataOpen && this.detail
                                      ? html`
                                            <div class="task-data-popover">
                                                <div class="task-data-mono">
                                                    ${JSON.stringify(this.detail.task, null, 2)}
                                                </div>
                                            </div>
                                        `
                                      : ''}
                              </div>
                              ${this.detailLoading
                                  ? html`<div class="detail-loading"><glass-spinner></glass-spinner></div>`
                                  : this.detail
                                    ? html`
                                          ${this.detail.task?.handoff_message_preview
                                              ? html`<div class="task-question">${this.detail.task.handoff_message_preview}</div>`
                                              : ''}
                                          <div class="detail-inner">
                                              ${this._renderDialogArea()}
                                              ${this._renderComposer()}
                                          </div>
                                      `
                                    : html`
                                          <div class="detail-inner detail-inner--empty">
                                              <div class="detail-empty-hint">
                                                  ${this.i18n.t('operator.detail_unavailable')}
                                              </div>
                                          </div>
                                      `}
                          `
                        : html`
                              <div class="detail-inner detail-inner--empty">
                                  <div class="detail-empty-hint">${this.i18n.t('operator.pick_task')}</div>
                              </div>
                          `}
                </div>
                <div class="kanban">
                    ${this.loading
                        ? html`<glass-spinner></glass-spinner>`
                        : STATUSES.map(
                              (st) => html`
                                  <div class="column">
                                      <div class="column-title">${st}</div>
                                      ${this._tasksByStatus(st).map(
                                          (t) => html`
                                              <div
                                                  class="card ${this.selectedId === t.id ? 'selected' : ''}"
                                                  @click=${() => this._selectTask(t.id)}
                                              >
                                                  <div class="card-headline">
                                                      ${this._taskCardHeadline(t)}
                                                  </div>
                                                  <div class="card-tech">
                                                      ${t.flow_id} / ${t.skill_id}
                                                  </div>
                                                  <div class="card-handoff-title">
                                                      ${this._taskCardHandoffTitle(t)}
                                                  </div>
                                                  ${t.handoff_message_preview
                                                      ? html`<div class="card-handoff-preview">
                                                            ${t.handoff_message_preview}
                                                        </div>`
                                                      : null}
                                              </div>
                                          `,
                                      )}
                                  </div>
                              `,
                          )}
                </div>
            </div>
        `;
    }
}

customElements.define('operator-workbench-page', OperatorWorkbenchPage);

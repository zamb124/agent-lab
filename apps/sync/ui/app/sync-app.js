/**
 * SyncApp — главное приложение Sync Chat
 * Наследует PlatformApp, подключает единый платформенный auth.
 */
import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncAPIService } from '../services/sync-api.service.js';
import { SyncWsService } from '../services/sync-ws.service.js';
import { SyncStore } from '../store/sync.store.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/layout/platform-island.js';

export class SyncApp extends PlatformApp {
    static properties = {
        _chat: { state: true },
        _ui: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: 100vw;
                height: 100vh;
                overflow: hidden;
                background: var(--bg-gradient);
            }

            .sidebar {
                height: 100vh;
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }

            .main {
                flex: 1;
                height: 100vh;
                overflow: hidden;
                display: flex;
                padding: var(--space-4);
            }

            platform-island {
                flex: 1;
                min-height: calc(100vh - 2rem);
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            @media (max-width: 767px) {
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }

                .main {
                    padding: 0;
                }
            }
        `
    ];

    constructor() {
        super();
        this._chat = SyncStore.state.chat;
        this._ui = SyncStore.state.ui;
        this._ws = null;
        this._unsubscribe = null;
    }

    setupStore() {
        return SyncStore;
    }

    getBaseUrl() {
        return '/sync';
    }

    async initServices() {
        await super.initServices();
        await ServiceRegistry.registerCore('/sync');
        ServiceRegistry.register('syncApi', new SyncAPIService('/sync/api/v1'));

        this._unsubscribe = SyncStore.subscribe((state) => {
            this._chat = state.chat;
            this._ui = state.ui;
        });
    }

    async checkAuth() {
        const auth = ServiceRegistry.auth;
        const isAuthenticated = await auth.validateToken();
        if (!isAuthenticated) {
            this.redirectToAuth();
            return false;
        }
        return true;
    }

    async connectedCallback() {
        await super.connectedCallback();

        if (!this._isAuthenticated) return;

        const syncApi = ServiceRegistry.get('syncApi');

        await Promise.all([
            SyncStore.loadSpaces(syncApi),
            SyncStore.loadChannels(syncApi),
        ]);

        await this._restoreLastSelection();
        this._connectWs();
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
        this._ws?.close();
        this._ws = null;
    }

    async _restoreLastSelection() {
        const { selectedChannelId } = SyncStore.state.chat;
        if (!selectedChannelId) return;

        const channel = SyncStore.state.channels.list.find(c => c.id === selectedChannelId);
        if (!channel) {
            SyncStore.selectChannel(null, null);
            return;
        }

        const syncApi = ServiceRegistry.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
    }

    _connectWs() {
        if (this._ws) return;

        const ws = new SyncWsService();
        this._ws = ws;
        ServiceRegistry.register('syncWs', ws);

        ws.onOpen(() => {
            SyncStore.setWsState('open');
        });

        ws.onClose(() => {
            SyncStore.setWsState('closed');
        });

        ws.onError(() => {
            SyncStore.setWsState('closed');
            SyncStore.failAllPending();
        });

        ws.onMessage((data) => {
            let msg;
            try { msg = JSON.parse(data); } catch { return; }

            if (!msg || typeof msg !== 'object') return;

            if (typeof msg.ok === 'boolean' && typeof msg.id === 'string') {
                if (msg.ok && msg.result) {
                    SyncStore.resolvePending(msg.id, msg.result);
                } else {
                    SyncStore.failPending(msg.id);
                }
                return;
            }

            if (msg.type === 'message.created' && msg.payload) {
                const { selectedChannelId } = SyncStore.state.chat;
                if (selectedChannelId && msg.payload.channel_id === selectedChannelId) {
                    SyncStore.upsertMessage(msg.payload);
                }
            }
        });

        ws.connect();
    }

    render() {
        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }
        if (!this._isAuthenticated) {
            return html`<app-loader></app-loader>`;
        }

        return html`
            <div class="sidebar">
                <sync-sidebar></sync-sidebar>
            </div>

            <div class="main">
                <platform-island>
                    <chat-view></chat-view>
                </platform-island>
            </div>

            <create-space-modal></create-space-modal>
            <create-channel-modal></create-channel-modal>
        `;
    }
}

customElements.define('sync-app', SyncApp);

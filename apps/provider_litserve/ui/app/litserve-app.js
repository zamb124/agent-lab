import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { LitserveModelsService } from '../services/litserve-models.service.js';
import { LitserveStore } from '../store/litserve.store.js';
import '@platform/lib/components/layout/platform-island.js';

export class LitserveApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _currentView: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }

            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }

            .main {
                flex: 1;
                height: var(--app-vh, 100vh);
                overflow-y: auto;
                display: flex;
                padding: var(--space-4);
            }

            platform-island {
                flex: 1;
                min-height: calc(var(--app-vh, 100vh) - 2rem);
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
        `,
    ];

    setupStore() {
        return LitserveStore;
    }

    getBaseUrl() {
        return '/litserve';
    }

    async initServices() {
        await super.initServices();
        this.services.register('litserveModels', new LitserveModelsService('/litserve/api'));
        this._unsubscribe = LitserveStore.subscribe((state) => {
            this._currentView = state.ui.currentView;
        });
        this._currentView = LitserveStore.state.ui.currentView;
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    async checkAuth() {
        const ok = await this.auth.validateToken();
        return !!ok;
    }

    _renderContent() {
        if (this._currentView === 'models') {
            return html`<litserve-models-page></litserve-models-page>`;
        }
        return html`<litserve-models-page></litserve-models-page>`;
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }

        return html`
            <div class="sidebar">
                <litserve-sidebar></litserve-sidebar>
            </div>
            <div class="main">
                <platform-island>
                    ${this._renderContent()}
                </platform-island>
            </div>
        `;
    }
}

customElements.define('litserve-app', LitserveApp);

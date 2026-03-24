/**
 * RagApp - Главное приложение RAG Service
 */
import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { RAGAPIService } from '../services/rag-api.service.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/platform-island.js';

export class RagApp extends PlatformApp {
    static properties = {
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
        `
    ];

    setupStore() {
        return RagStore;
    }

    getBaseUrl() {
        return '/rag';
    }

    async initServices() {
        await super.initServices();
        
        await ServiceRegistry.registerCore('/rag');
        ServiceRegistry.register('ragApi', new RAGAPIService('/rag/api/v1'));
        
        this._unsubscribe = RagStore.subscribe((state) => {
            this._currentView = state.ui.currentView;
        });
        this._currentView = RagStore.state.ui.currentView || 'namespaces';
    }
    
    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    async checkAuth() {
        return true;
    }

    _renderContent() {
        const currentView = this._currentView || 'namespaces';

        switch (currentView) {
            case 'namespaces':
                return html`<namespace-list></namespace-list>`;
            case 'documents':
                return html`<namespace-detail></namespace-detail>`;
            case 'search':
                return html`<search-view></search-view>`;
            case 'settings':
                return html`<settings-view></settings-view>`;
            default:
                return html`<namespace-list></namespace-list>`;
        }
    }

    render() {
        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }

        return html`
            <div class="sidebar">
                <rag-sidebar></rag-sidebar>
            </div>

            <div class="main">
                <platform-island>
                    ${this._renderContent()}
                </platform-island>
            </div>
        `;
    }
}

customElements.define('rag-app', RagApp);

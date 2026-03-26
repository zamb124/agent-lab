/**
 * CRM App - Главное приложение CRM ("Умная Записная Книжка")
 * Адаптивный layout: Desktop (split view) -> Mobile (fullscreen)
 * 3-колоночный layout при наличии AI suggestions
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { CRMAPIService } from '../services/crm-api.service.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/notes-list.js';
import '../components/ai-suggestions-panel.js';
import '../pages/entities-page.js';
import '../modals/entity-modal.js';
import '../modals/share-modal.js';
import '../modals/access-request-modal.js';
import '../modals/namespace-modal.js';
import '../components/crm-sidebar.js';
import '@platform/lib/components/platform-icon.js';

export class CRMApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _isMobile: { state: true },
        _currentNoteId: { state: true },
        _hasSuggestions: { state: true },
        _currentView: { state: true },
        _showNamespaceModal: { state: true },
        _activeMobilePanel: { state: true },
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
                display: flex;
                padding: var(--space-4);
                gap: var(--space-4);
                overflow: hidden;
            }
            
            notes-list {
                width: 320px;
                height: 100%;
                flex-shrink: 0;
            }
            
            notes-list[collapsed] {
                width: 48px;
                flex: 0 0 48px;
            }
            
            note-editor {
                flex: 1;
                height: 100%;
                min-width: 0;
            }
            
            .fullscreen {
                width: 100%;
                height: 100%;
            }
            
            ai-suggestions-panel {
                width: 380px;
                height: 100%;
                flex-shrink: 0;
                overflow-y: auto;
            }
            
            ai-suggestions-panel.hidden {
                display: none;
            }
            
            @media (min-width: 768px) and (max-width: 1023px) {
                notes-list {
                    width: 240px;
                }
                notes-list[collapsed] {
                    width: 48px;
                }
            }
            
            @media (min-width: 1024px) and (max-width: 1279px) {
                .main.has-suggestions notes-list {
                    width: 260px;
                }
                .main.has-suggestions notes-list[collapsed] {
                    width: 48px;
                }
            }
            
            @media (max-width: 767px) {
                .main {
                    padding: 0;
                    flex-direction: column;
                }
                
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }
                
                .mobile-panels-container {
                    display: flex;
                    flex-direction: column;
                    width: 100%;
                    height: 100%;
                    overflow: hidden;
                }
                
                .mobile-tabs {
                    display: flex;
                    padding: max(var(--space-2), env(safe-area-inset-top, 0px)) var(--space-2) var(--space-2);
                    gap: var(--space-2);
                    background: var(--glass-solid-subtle);
                    border-bottom: 1px solid var(--glass-border-subtle);
                    flex-shrink: 0;
                    overflow-x: auto;
                }
                
                .menu-btn {
                    width: 32px;
                    height: 32px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-md);
                    background: var(--glass-solid-subtle);
                    border: 1px solid var(--glass-border-subtle);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                }
                
                .menu-btn:hover {
                    background: var(--glass-solid-medium);
                }
                
                .mobile-tab {
                    display: flex;
                    align-items: center;
                    gap: var(--space-2);
                    padding: var(--space-2) var(--space-3);
                    border-radius: var(--radius-md);
                    background: transparent;
                    border: 1px solid transparent;
                    color: var(--text-secondary);
                    font-size: var(--text-sm);
                    font-weight: 500;
                    cursor: pointer;
                    white-space: nowrap;
                    transition: all var(--duration-fast);
                }
                
                .mobile-tab:hover {
                    background: var(--glass-solid-medium);
                    color: var(--text-primary);
                }
                
                .mobile-tab.active {
                    background: var(--glass-solid-strong);
                    border-color: var(--glass-border-medium);
                    color: var(--text-primary);
                }
                
                .mobile-panel {
                    flex: 1;
                    min-height: 0;
                    overflow: hidden;
                }
                
                .mobile-panel > * {
                    width: 100%;
                    height: 100%;
                }
            }
            
            @media (min-width: 768px) {
                .fullscreen {
                    display: none;
                }
            }
            
            .placeholder-view {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
                text-align: center;
                color: var(--text-secondary);
            }
            
            .placeholder-view .placeholder-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-xl);
                margin-bottom: var(--space-4);
                color: var(--text-tertiary);
            }
            
            .placeholder-view h2 {
                margin: 0 0 var(--space-2) 0;
                font-size: var(--text-xl);
                font-weight: 600;
                color: var(--text-primary);
            }
            
            .placeholder-view p {
                margin: 0;
                font-size: var(--text-base);
                color: var(--text-tertiary);
            }
        `
    ];

    constructor() {
        super();
        this._isMobile = false;
        this._currentNoteId = null;
        this._hasSuggestions = false;
        this._currentView = 'notes';
        this._showNamespaceModal = false;
        this._activeMobilePanel = 'notes';
        this._resizeObserver = null;
    }

    setupStore() {
        return CRMStore;
    }

    getBaseUrl() {
        return '/crm';
    }

    async initServices() {
        await super.initServices();
        
        await this.services.registerCore('/crm');
        this.services.register('crmApi', new CRMAPIService('/crm/api/v1'));
        
        CRMStore.initFromUrl();
        CRMStore.setupPopstateListener();
        
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._currentNoteId = state.entities.currentNoteId;
            this._isMobile = state.ui.isMobile;
            this._hasSuggestions = (state.ai.suggestions || []).length > 0;
            this._currentView = state.ui.currentView;
        });
        
        this._checkMobile();
        this._setupResizeObserver();
    }
    
    async firstUpdated() {
        await super.firstUpdated();
        
        const crmApi = this.services.get('crmApi');
        await Promise.all([
            CRMStore.loadNotes(crmApi),
            CRMStore.loadEntityTypes(crmApi),
            CRMStore.loadRelationshipTypes(crmApi),
            CRMStore.loadNamespaces(crmApi),
        ]);
    }
    
    _checkMobile() {
        const isMobile = window.innerWidth < 768;
        CRMStore.setMobile(isMobile);
    }
    
    _setupResizeObserver() {
        this._resizeObserver = new ResizeObserver(() => {
            this._checkMobile();
        });
        this._resizeObserver.observe(document.body);
    }
    
    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
        this._resizeObserver?.disconnect();
    }

    async checkAuth() {
        return true;
    }

    _renderContent() {
        const isMobile = this._isMobile;
        
        if (this._currentView === 'notes') {
            if (isMobile) {
                return this._renderMobileNotesView();
            }
            
            return html`
                <notes-list></notes-list>
                <note-editor></note-editor>
                <ai-suggestions-panel class="${this._hasSuggestions ? '' : 'hidden'}"></ai-suggestions-panel>
            `;
        }
        
        if (this._currentView === 'entities') {
            return html`<entities-page></entities-page>`;
        }
        
        return this._renderPlaceholder(this._currentView);
    }

    _renderMobileNotesView() {
        const panels = [
            { id: 'notes', label: 'Заметки', icon: 'file' },
            { id: 'editor', label: 'Редактор', icon: 'edit' },
        ];
        
        if (this._hasSuggestions) {
            panels.push({ id: 'ai', label: 'AI', icon: 'ai' });
        }
        
        return html`
            <div class="mobile-panels-container">
                <div class="mobile-tabs">
                    <button class="menu-btn" @click=${this._openSidebar} title="Открыть меню">
                        <platform-icon name="menu" size="18"></platform-icon>
                    </button>
                    ${panels.map(panel => html`
                        <button 
                            class="mobile-tab ${this._activeMobilePanel === panel.id ? 'active' : ''}"
                            @click=${() => this._setMobilePanel(panel.id)}
                        >
                            <platform-icon name="${panel.icon}" size="16"></platform-icon>
                            ${panel.label}
                        </button>
                    `)}
                </div>
                <div class="mobile-panel">
                    ${this._renderMobilePanel()}
                </div>
            </div>
        `;
    }

    _renderMobilePanel() {
        switch (this._activeMobilePanel) {
            case 'notes':
                return html`<notes-list @note-selected=${this._onNoteSelected}></notes-list>`;
            case 'editor':
                return html`<note-editor></note-editor>`;
            case 'ai':
                return html`<ai-suggestions-panel></ai-suggestions-panel>`;
            default:
                return html`<notes-list @note-selected=${this._onNoteSelected}></notes-list>`;
        }
    }

    _onNoteSelected() {
        this._activeMobilePanel = 'editor';
    }

    _setMobilePanel(panelId) {
        this._activeMobilePanel = panelId;
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }
    
    _renderPlaceholder(view) {
        const viewNames = {
            graph: 'Граф связей',
            tasks: 'Задачи',
            calendar: 'Календарь',
        };
        
        const viewName = viewNames[view] || view;
        
        return html`
            <div class="placeholder-view">
                <div class="placeholder-icon">
                    <platform-icon name="${this._getViewIcon(view)}" size="48"></platform-icon>
                </div>
                <h2>${viewName}</h2>
                <p>Раздел в разработке</p>
            </div>
        `;
    }
    
    _getViewIcon(view) {
        const icons = {
            graph: 'network',
            tasks: 'checklist',
            calendar: 'calendar',
        };
        return icons[view] || 'folder';
    }

    _openNamespaceModal() {
        this._showNamespaceModal = true;
    }

    _closeNamespaceModal() {
        this._showNamespaceModal = false;
    }
    
    async _onNamespaceChanged() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntities(crmApi);
        await CRMStore.loadNotes(crmApi);
    }

    async _onNamespaceSaved(e) {
        this._showNamespaceModal = false;
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntities(crmApi);
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }

        const mainClass = this._hasSuggestions ? 'main has-suggestions' : 'main';

        return html`
            <div class="sidebar">
                <crm-sidebar
                    @open-namespace-modal=${this._openNamespaceModal}
                    @namespace-changed=${this._onNamespaceChanged}
                ></crm-sidebar>
            </div>
            <div class="${mainClass}">
                ${this._renderContent()}
            </div>
            
            ${this._showNamespaceModal ? html`
                <namespace-modal
                    .open=${true}
                    @close=${this._closeNamespaceModal}
                    @saved=${this._onNamespaceSaved}
                ></namespace-modal>
            ` : ''}
        `;
    }
}

customElements.define('crm-app', CRMApp);

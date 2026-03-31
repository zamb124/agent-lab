/**
 * CRM App - Главное приложение CRM
 * Desktop: sidebar + main content
 * Mobile: slide-out sidebar + compact header (menu + title + action) + content
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { CRMAPIService } from '../services/crm-api.service.js';
import { CRMStore } from '../store/crm.store.js';
import '../pages/daily-notes-page.js';
import '../pages/entities-page.js';
import '../pages/graph-page.js';
import '../pages/tasks-page.js';
import '../pages/settings-hub-page.js';
import '../pages/templates-page.js';
import '../pages/spaces-page.js';
import '../modals/entity-modal.js';
import '../modals/note-view-modal.js';
import '../modals/ai-analysis-modal.js';
import '../modals/share-modal.js';
import '../modals/access-request-modal.js';
import '../modals/namespace-modal.js';
import '../components/crm-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/layout/platform-island.js';

const VIEW_CONFIG = {
    notes: { title: 'Ежедневник', actionIcon: 'plus', actionTitle: 'Добавить заметку', searchable: true },
    entities: { title: 'Сущности', actionIcon: 'plus', actionTitle: 'Создать сущность', searchable: true },
    graph: { title: 'Граф связей', actionIcon: null },
    tasks: { title: 'Задачи', actionIcon: 'plus', actionTitle: 'Создать задачу', extraIcon: 'refresh', extraTitle: 'Обновить' },
    calendar: { title: 'Календарь', actionIcon: null },
    settings: { title: 'Настройки', actionIcon: null },
    templates: { title: 'Шаблоны', actionIcon: null },
    spaces: { title: 'Пространства', actionIcon: null },
};

export class CRMApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _isMobile: { state: true },
        _currentView: { state: true },
        _showNamespaceModal: { state: true },
        _showAiModal: { state: true },
        _mobileSearchOpen: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                flex-direction: row;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
                --accent: var(--crm-button-primary-bg);
                --accent-hover: var(--crm-button-primary-hover);
                --accent-active: var(--crm-button-primary-hover);
                --accent-subtle: rgba(153, 166, 249, 0.18);
                --accent-glow: 0 0 24px rgba(153, 166, 249, 0.35);
                --accent-gradient: linear-gradient(135deg, #99A6F9 0%, #8794F0 100%);
                --border-focus: var(--crm-button-primary-bg);
                --focus-ring: 0 0 0 3px rgba(153, 166, 249, 0.4);
                --btn-primary-bg: var(--crm-button-primary-bg);
                --btn-primary-hover-bg: var(--crm-button-primary-hover);
                --btn-primary-text: var(--crm-button-primary-text);
                --btn-primary-shadow: 0 4px 12px rgba(153, 166, 249, 0.35);
                --btn-primary-hover-shadow: 0 6px 20px rgba(153, 166, 249, 0.45);
                --btn-secondary-bg: var(--crm-button-secondary-bg);
                --btn-secondary-border: var(--crm-button-secondary-bg);
                --btn-secondary-text: var(--crm-button-secondary-text);
                --btn-secondary-hover-bg: var(--crm-button-secondary-hover);
                --btn-secondary-hover-border: var(--crm-button-secondary-hover);
                --btn-secondary-hover-text: var(--crm-button-secondary-text);
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
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }

            platform-island {
                flex: 1;
                min-height: 0;
            }

            .mobile-app-header {
                display: none;
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
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
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

            @media (max-width: 767px) {
                .main {
                    padding: 0;
                }

                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }

                .mobile-app-header {
                    display: flex;
                    align-items: center;
                    gap: var(--space-2);
                    padding: max(var(--space-2), env(safe-area-inset-top, 0px)) var(--space-3) var(--space-2);
                    background: var(--crm-surface-muted);
                    border-bottom: 1px solid var(--crm-stroke);
                    flex-shrink: 0;
                }

                .mobile-menu-btn {
                    width: 36px;
                    height: 36px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-md);
                    background: transparent;
                    border: 1px solid var(--crm-stroke);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                }

                .mobile-menu-btn:hover {
                    background: var(--crm-surface);
                }

                .mobile-header-title {
                    flex: 1;
                    font-size: var(--text-lg);
                    font-weight: 700;
                    color: var(--text-primary);
                    min-width: 0;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }

                .mobile-action-btn {
                    width: 36px;
                    height: 36px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-md);
                    background: var(--crm-daily-notes-cta-bg);
                    border: none;
                    color: var(--text-inverse);
                    cursor: pointer;
                    flex-shrink: 0;
                    transition: background var(--duration-fast);
                }

                .mobile-action-btn:hover {
                    background: var(--crm-daily-notes-cta-hover);
                }

                .mobile-search-row {
                    display: flex;
                    align-items: center;
                    gap: var(--space-2);
                    padding: 0 var(--space-3) var(--space-2);
                    background: var(--crm-surface-muted);
                    animation: search-slide-down 0.15s ease-out;
                }

                @keyframes search-slide-down {
                    from { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; }
                    to { opacity: 1; max-height: 50px; }
                }

                .mobile-search-input {
                    flex: 1;
                    min-width: 0;
                    height: 36px;
                    border: 1px solid var(--crm-stroke);
                    border-radius: var(--radius-full);
                    background: var(--crm-surface);
                    color: var(--text-primary);
                    font-size: var(--text-sm);
                    padding: 0 var(--space-3) 0 var(--space-8);
                    outline: none;
                }

                .mobile-search-input:focus {
                    border-color: var(--accent);
                }

                .mobile-search-icon {
                    position: absolute;
                    left: var(--space-5);
                    pointer-events: none;
                    color: var(--text-tertiary);
                }

                .mobile-search-wrapper {
                    position: relative;
                    flex: 1;
                    display: flex;
                    align-items: center;
                }

                .mobile-search-close {
                    width: 28px;
                    height: 28px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border: none;
                    border-radius: var(--radius-md);
                    background: transparent;
                    color: var(--text-tertiary);
                    cursor: pointer;
                    flex-shrink: 0;
                }

                .mobile-search-close:hover {
                    color: var(--text-primary);
                }

                platform-island {
                    min-height: 0;
                }
            }
        `
    ];

    constructor() {
        super();
        this._isMobile = false;
        this._currentView = 'notes';
        this._showNamespaceModal = false;
        this._showAiModal = false;
        this._mobileSearchOpen = false;
        this._resizeObserver = null;
        this._searchDebounce = null;
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
            this._isMobile = state.ui.isMobile;
            if (this._currentView !== state.ui.currentView) {
                this._mobileSearchOpen = false;
            }
            this._currentView = state.ui.currentView;
        });

        this._checkMobile();
        this._setupResizeObserver();
    }

    async firstUpdated() {
        await super.firstUpdated();

        const crmApi = this.services.get('crmApi');
        await CRMStore.loadNamespaces(crmApi);
        const currentNamespace = CRMStore.state.namespaces.current;
        const namespaceName = typeof currentNamespace === 'string'
            ? currentNamespace
            : (currentNamespace && typeof currentNamespace.name === 'string' ? currentNamespace.name : null);
        const { from, to } = CRMStore.getDailyNotesRange();
        await Promise.all([
            CRMStore.loadNotes(crmApi, {
                dateFrom: from,
                dateTo: to,
                limit: 300,
            }),
            CRMStore.loadEntityTypes(crmApi, namespaceName),
            CRMStore.loadRelationshipTypes(crmApi),
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

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    _toggleMobileSearch() {
        this._mobileSearchOpen = !this._mobileSearchOpen;
        if (!this._mobileSearchOpen) {
            this._dispatchSearchQuery('');
        }
    }

    _onMobileSearchInput(event) {
        const query = event.target.value;
        if (this._searchDebounce) {
            clearTimeout(this._searchDebounce);
        }
        this._searchDebounce = setTimeout(() => {
            this._searchDebounce = null;
            this._dispatchSearchQuery(query);
        }, 300);
    }

    _dispatchSearchQuery(query) {
        if (this._currentView === 'entities') {
            CRMStore.setEntityFilters({ search: query });
            const crmApi = this.services.get('crmApi');
            CRMStore.loadEntities(crmApi);
        }
        if (this._currentView === 'notes') {
            window.dispatchEvent(new CustomEvent('crm-mobile-search', {
                detail: { query },
                bubbles: true,
                composed: true,
            }));
        }
    }

    _onMobileAction() {
        if (this._currentView === 'notes') {
            this._createNote();
        } else if (this._currentView === 'entities') {
            this._createEntity();
        } else if (this._currentView === 'tasks') {
            this._dispatchPageEvent('tasks-create');
        }
    }

    _onMobileExtra() {
        if (this._currentView === 'tasks') {
            this._dispatchPageEvent('tasks-refresh');
        }
    }

    _dispatchPageEvent(eventName) {
        const island = this.renderRoot?.querySelector('platform-island');
        if (island) {
            island.dispatchEvent(new CustomEvent(eventName, { bubbles: true, composed: true }));
        }
    }

    _createNote() {
        const focusDate = CRMStore.getDailyNotesFocusDate();
        const draftNote = {
            entity_id: `draft-${Date.now()}`,
            entity_type: 'note',
            entity_subtype: null,
            name: '',
            description: '',
            note_date: focusDate,
            attributes: {},
        };
        const modal = document.createElement('note-view-modal');
        modal.note = draftNote;
        modal.startInEditMode = true;
        modal.draftMode = true;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _createEntity() {
        const modal = document.createElement('entity-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _renderContent() {
        if (this._currentView === 'notes') {
            return html`<daily-notes-page @analysis-ready=${this._openAiModal}></daily-notes-page>`;
        }

        if (this._currentView === 'entities') {
            return html`<entities-page></entities-page>`;
        }

        if (this._currentView === 'graph') {
            return html`<graph-page></graph-page>`;
        }

        if (this._currentView === 'tasks') {
            return html`<tasks-page></tasks-page>`;
        }

        if (this._currentView === 'settings') {
            return html`<settings-hub-page></settings-hub-page>`;
        }

        if (this._currentView === 'templates') {
            return html`<templates-page></templates-page>`;
        }

        if (this._currentView === 'spaces') {
            return html`<spaces-page></spaces-page>`;
        }

        return this._renderPlaceholder(this._currentView);
    }

    _renderPlaceholder(view) {
        const cfg = VIEW_CONFIG[view];
        const viewName = cfg?.title || view;
        const icons = {
            graph: 'network',
            tasks: 'checklist',
            templates: 'settings',
            spaces: 'folder',
        };

        return html`
            <div class="placeholder-view">
                <div class="placeholder-icon">
                    <platform-icon name="${icons[view] || 'folder'}" size="48"></platform-icon>
                </div>
                <h2>${viewName}</h2>
                <p>Раздел в разработке</p>
            </div>
        `;
    }

    _openNamespaceModal() {
        this._showNamespaceModal = true;
    }

    _closeNamespaceModal() {
        this._showNamespaceModal = false;
    }

    _openAiModal() {
        this._showAiModal = true;
    }

    _closeAiModal() {
        this._showAiModal = false;
    }

    async _onNamespaceChanged() {
        const crmApi = this.services.get('crmApi');
        const currentNamespace = CRMStore.state.namespaces.current;
        const namespaceName = typeof currentNamespace === 'string'
            ? currentNamespace
            : (currentNamespace && typeof currentNamespace.name === 'string' ? currentNamespace.name : null);
        const { from, to } = CRMStore.getDailyNotesRange();
        await CRMStore.loadEntityTypes(crmApi, namespaceName);
        await CRMStore.loadEntities(crmApi);
        await CRMStore.loadNotes(crmApi, {
            dateFrom: from,
            dateTo: to,
            limit: 300,
        });
    }

    async _onNamespaceSaved() {
        this._showNamespaceModal = false;
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadNamespaces(crmApi);
        const currentNamespace = CRMStore.state.namespaces.current;
        const namespaceName = typeof currentNamespace === 'string'
            ? currentNamespace
            : (currentNamespace && typeof currentNamespace.name === 'string' ? currentNamespace.name : null);
        const { from, to } = CRMStore.getDailyNotesRange();
        await CRMStore.loadEntityTypes(crmApi, namespaceName);
        await CRMStore.loadEntities(crmApi);
        await CRMStore.loadNotes(crmApi, {
            dateFrom: from,
            dateTo: to,
            limit: 300,
        });
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }

        const viewCfg = VIEW_CONFIG[this._currentView] || { title: this._currentView, actionIcon: null };

        return html`
            <div class="sidebar">
                <crm-sidebar
                    @open-namespace-modal=${this._openNamespaceModal}
                    @namespace-changed=${this._onNamespaceChanged}
                ></crm-sidebar>
            </div>
            <div class="main">
                ${this._isMobile ? html`
                    <div class="mobile-app-header">
                        <button class="mobile-menu-btn" type="button" @click=${this._openSidebar} title="Меню">
                            <platform-icon name="menu" size="18"></platform-icon>
                        </button>
                        <span class="mobile-header-title">${viewCfg.title}</span>
                        ${viewCfg.searchable ? html`
                            <button class="mobile-menu-btn" type="button" @click=${this._toggleMobileSearch} title="Поиск">
                                <platform-icon name="search" size="16"></platform-icon>
                            </button>
                        ` : ''}
                        ${viewCfg.extraIcon ? html`
                            <button class="mobile-menu-btn" type="button" @click=${this._onMobileExtra} title="${viewCfg.extraTitle || ''}">
                                <platform-icon name="${viewCfg.extraIcon}" size="16"></platform-icon>
                            </button>
                        ` : ''}
                        ${viewCfg.actionIcon ? html`
                            <button class="mobile-action-btn" type="button" @click=${this._onMobileAction} title="${viewCfg.actionTitle || ''}">
                                <platform-icon name="${viewCfg.actionIcon}" size="18"></platform-icon>
                            </button>
                        ` : ''}
                    </div>
                    ${this._mobileSearchOpen ? html`
                        <div class="mobile-search-row">
                            <div class="mobile-search-wrapper">
                                <platform-icon class="mobile-search-icon" name="ai" size="14" colored></platform-icon>
                                <input
                                    class="mobile-search-input"
                                    type="text"
                                    placeholder="Поиск..."
                                    autofocus
                                    @input=${this._onMobileSearchInput}
                                />
                            </div>
                            <button class="mobile-search-close" type="button" @click=${this._toggleMobileSearch}>
                                <platform-icon name="close" size="14"></platform-icon>
                            </button>
                        </div>
                    ` : ''}
                ` : ''}
                <platform-island padding=${this._isMobile ? 'none' : 'md'} ?safe-bottom=${this._isMobile}>
                    ${this._renderContent()}
                </platform-island>
            </div>

            ${this._showNamespaceModal ? html`
                <namespace-modal
                    .open=${true}
                    @modal-closed=${this._closeNamespaceModal}
                    @saved=${this._onNamespaceSaved}
                ></namespace-modal>
            ` : ''}

            ${this._showAiModal ? html`
                <ai-analysis-modal
                    .open=${true}
                    @modal-closed=${this._closeAiModal}
                    @saved=${this._closeAiModal}
                ></ai-analysis-modal>
            ` : ''}
        `;
    }
}

customElements.define('crm-app', CRMApp);

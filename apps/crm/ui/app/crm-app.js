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
import '../pages/namespace-imports-page.js';
import '../modals/entity-modal.js';
import '../modals/note-view-modal.js';
import '../modals/ai-analysis-modal.js';
import '../modals/share-modal.js';
import '../modals/access-request-modal.js';
import '../modals/namespace-modal.js';
import '../components/crm-sidebar.js';
import '../components/crm-mobile-app-header.js';
import '@platform/lib/embed-chat/platform-embed-chat-drawer.js';
import {
    flowsEmbedShouldSendCredentials,
    resolveCrmLaraFlowsBaseUrl,
    resolveFlowsEmbedAuthHeaders,
} from '../utils/crm-lara-flows-base.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/layout/platform-island.js';

export class CRMApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _isMobile: { state: true },
        _currentView: { state: true },
        _showNamespaceModal: { state: true },
        _showAiModal: { state: true },
        _mobileSearchOpen: { state: true },
        _mobileSearchInputValue: { state: true },
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
                min-width: 0;
                height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }

            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }

            .mobile-shell-header-wrap {
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

                .mobile-shell-header-wrap {
                    display: block;
                    flex-shrink: 0;
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
        this._mobileSearchInputValue = '';
        this._resizeObserver = null;
        this._searchDebounce = null;
        /** @type {{ key: string, at: number, data: object } | null} */
        this._laraSummaryCache = null;
    }

    _laraEmbedGetAuthToken = async () => {
        const headers = await resolveFlowsEmbedAuthHeaders();
        const ns = CRMStore._getCurrentNamespaceName();
        if (ns && ns !== 'default') {
            headers['X-Platform-Namespace'] = ns;
        }
        return headers;
    };

    _laraSummaryFlattenForVariables(data) {
        if (!data || typeof data !== 'object') {
            return {};
        }
        const json = JSON.stringify(data);
        return {
            crm_lara_summary: data,
            crm_lara_summary_json: json,
            crm_knowledge_imports_awaiting_review: data.knowledge_imports_awaiting_review,
            crm_knowledge_imports_in_progress: data.knowledge_imports_in_progress,
            crm_notes_analysis_draft_not_applied: data.notes_with_analysis_draft_not_applied,
        };
    }

    _laraEmbedExtraMetadataVariables = async () => {
        const crmApi = this.services?.get('crmApi');
        if (!crmApi || typeof crmApi.getLaraWorkspaceSummary !== 'function') {
            return {};
        }
        const ns = CRMStore._getCurrentNamespaceName();
        const now = Date.now();
        const ttlMs = 45000;
        if (
            this._laraSummaryCache &&
            this._laraSummaryCache.key === ns &&
            now - this._laraSummaryCache.at < ttlMs
        ) {
            return this._laraSummaryFlattenForVariables(this._laraSummaryCache.data);
        }
        try {
            const data = await crmApi.getLaraWorkspaceSummary(ns);
            this._laraSummaryCache = { key: ns, at: now, data };
            return this._laraSummaryFlattenForVariables(data);
        } catch (err) {
            console.warn('getLaraWorkspaceSummary failed', err);
            return {};
        }
    };

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
        const ok = await this.auth.validateToken();
        return !!ok;
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    _hydrateMobileSearchInputFromView() {
        if (this._currentView === 'entities') {
            this._mobileSearchInputValue = CRMStore.state.entities.filters.search || '';
            return;
        }
        if (this._currentView === 'notes') {
            this._mobileSearchInputValue = CRMStore.state.ui.notesPageSearchQuery || '';
            return;
        }
        if (this._currentView === 'tasks') {
            this._mobileSearchInputValue = CRMStore.state.ui.tasksListSearchQuery || '';
        }
    }

    _toggleMobileSearch() {
        if (this._mobileSearchOpen) {
            this._closeMobileSearch();
            return;
        }
        this._hydrateMobileSearchInputFromView();
        this._mobileSearchOpen = true;
    }

    _closeMobileSearch() {
        if (!this._mobileSearchOpen) {
            return;
        }
        this._mobileSearchOpen = false;
        this._dispatchSearchQuery('');
        this._mobileSearchInputValue = '';
    }

    _onHeaderSearchInput(event) {
        const raw = event.detail?.value;
        const query = typeof raw === 'string' ? raw : '';
        this._mobileSearchInputValue = query;
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
            CRMStore.setNotesPageSearchQuery(query);
            window.dispatchEvent(new CustomEvent('crm-mobile-search', {
                detail: { query },
                bubbles: true,
                composed: true,
            }));
        }
        if (this._currentView === 'tasks') {
            CRMStore.setTasksListSearchQuery(query);
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

    _onMobileAssistant() {
        window.dispatchEvent(new CustomEvent('humanitec-embed-chat-toggle', { bubbles: true }));
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

        if (this._currentView === 'namespace_imports') {
            return html`<namespace-imports-page></namespace-imports-page>`;
        }

        return this._renderPlaceholder(this._currentView);
    }

    _getViewConfig() {
        const v = (id) => this.i18n.t(`app_shell.views.${id}`);
        return {
            notes: {
                title: v('notes.title'),
                actionIcon: 'plus',
                actionTitle: v('notes.action_title'),
                searchable: true,
            },
            entities: {
                title: v('entities.title'),
                actionIcon: 'plus',
                actionTitle: v('entities.action_title'),
                searchable: true,
            },
            graph: { title: v('graph.title'), actionIcon: null },
            tasks: {
                title: v('tasks.title'),
                actionIcon: 'plus',
                actionTitle: v('tasks.action_title'),
                extraIcon: 'refresh',
                extraTitle: v('tasks.extra_title'),
                searchable: true,
            },
            calendar: { title: v('calendar.title'), actionIcon: null },
            settings: { title: v('settings.title'), actionIcon: null },
            templates: { title: v('templates.title'), actionIcon: null },
            spaces: { title: v('spaces.title'), actionIcon: null },
            namespace_imports: { title: v('namespace_imports.title'), actionIcon: null },
        };
    }

    _renderPlaceholder(view) {
        const cfg = this._getViewConfig()[view];
        const viewName = cfg?.title || view;
        const icons = {
            graph: 'network',
            tasks: 'checklist',
            templates: 'settings',
            spaces: 'folder',
            namespace_imports: 'database',
        };

        return html`
            <div class="placeholder-view">
                <div class="placeholder-icon">
                    <platform-icon name="${icons[view] || 'folder'}" size="48"></platform-icon>
                </div>
                <h2>${viewName}</h2>
                <p>${this.i18n.t('app_shell.under_development')}</p>
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
        CRMStore.clearKnowledgeImportReview();
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

        if (!this.services.isInitialized || !this.services.has('i18n')) {
            return html`<app-loader></app-loader>`;
        }

        const viewCfg = this._getViewConfig()[this._currentView] || { title: this._currentView, actionIcon: null };

        return html`
            <div class="sidebar">
                <crm-sidebar
                    @open-namespace-modal=${this._openNamespaceModal}
                    @namespace-changed=${this._onNamespaceChanged}
                ></crm-sidebar>
            </div>
            <div class="main">
                ${this._isMobile ? html`
                    <div class="mobile-shell-header-wrap">
                        <crm-mobile-app-header
                            .headerTitle=${viewCfg.title}
                            ?searchable=${!!viewCfg.searchable}
                            ?searchOpen=${this._mobileSearchOpen}
                            .searchValue=${this._mobileSearchInputValue}
                            assistant-icon="sparkle"
                            .assistantTitle=${this.i18n.t('app_shell.embed_chat_toggle')}
                            .extraIcon=${viewCfg.extraIcon || ''}
                            .extraTitle=${viewCfg.extraTitle || ''}
                            .actionIcon=${viewCfg.actionIcon || ''}
                            .actionTitle=${viewCfg.actionTitle || ''}
                            @header-menu=${this._openSidebar}
                            @header-toggle-search=${this._toggleMobileSearch}
                            @header-search-input=${this._onHeaderSearchInput}
                            @header-search-close=${this._closeMobileSearch}
                            @header-assistant=${this._onMobileAssistant}
                            @header-extra=${this._onMobileExtra}
                            @header-action=${this._onMobileAction}
                        ></crm-mobile-app-header>
                    </div>
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

            <platform-embed-chat-drawer
                theme="auto"
                .assistantTitle=${this.i18n.t('app_shell.embed_assistant_name')}
                .flowsBaseUrl=${resolveCrmLaraFlowsBaseUrl()}
                flow-id="lara"
                toggle-event-name="humanitec-embed-chat-toggle"
                ?use-credentials=${flowsEmbedShouldSendCredentials(resolveCrmLaraFlowsBaseUrl())}
                .getAuthToken=${this._laraEmbedGetAuthToken}
                .getExtraMetadataVariables=${this._laraEmbedExtraMetadataVariables}
                .locale=${this.services.get('i18n').getCurrentLocale()}
            ></platform-embed-chat-drawer>
        `;
    }
}

customElements.define('crm-app', CRMApp);

/**
 * Приложение «Документы»: auth, sidebar, список /edit/:id.
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { setActivePlatformNamespaceName } from '@platform/lib/utils/platform-namespace.js';
import { OfficeAPIService } from '../services/office-api.service.js';
import { OfficeStore } from '../store/office.store.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-icon.js';
import '../features/office-sidebar.js';
import '../features/documents-list-page.js';
import '../features/document-editor-page.js';
import '../features/office-catalogs-dashboard.js';
import '../features/office-documents-shell-actions.js';
import '../modals/office-namespace-modal.js';
import { isPlausibleOfficeBindingId } from '../utils/office-binding-id.js';

export class OfficeApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _view: { state: true },
        _editBindingId: { state: true },
        _isMobileLayout: { state: true },
        _mobileSidebarOpen: { state: true },
        _showNamespaceModal: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: column !important;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
                /* Service palette: gradient aligned with documents_logo.svg (#4adede -> #787ff6). */
                --documents-title-gradient: linear-gradient(
                    105deg,
                    #3ec9d8 0%,
                    #6cb1e1 42%,
                    #737ce9 100%
                );
                --documents-selected-bg: #dff3f9;
                --documents-selected-stroke: rgba(120, 127, 246, 0.38);
                --documents-selected-text: #4659b8;
                --documents-surface-muted: #eef8fc;
                --documents-stroke: rgba(100, 170, 215, 0.45);
                --documents-link-hover: #3585c4;
                /* Primary text hue matches logo gradient tail #737ce9, darkened for contrast. */
                --text-primary: rgba(46, 58, 124, 0.94);
            }

            :host-context([data-theme="dark"]) {
                --text-primary: rgba(228, 236, 255, 0.96);
            }
            .office-shell {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            .office-mobile-bar {
                display: none;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
                padding: max(var(--space-2), var(--platform-safe-top)) var(--space-3)
                    var(--space-2);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border-bottom: 1px solid var(--glass-border-subtle);
                box-sizing: border-box;
                z-index: 40;
            }
            :host-context([data-theme="light"]) .office-mobile-bar {
                background: rgba(255, 255, 255, 0.92);
                border-bottom-color: rgba(15, 23, 42, 0.08);
            }
            .office-content-row {
                flex: 1;
                display: flex;
                flex-direction: row;
                min-height: 0;
                min-width: 0;
                position: relative;
            }
            .menu-btn,
            .office-mobile-back {
                display: flex;
                width: 36px;
                height: 36px;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-medium);
                color: var(--text-primary);
                cursor: pointer;
                flex-shrink: 0;
                transition: all var(--duration-fast) var(--easing-default);
                box-shadow: var(--glass-shadow-subtle);
            }
            .menu-btn.hidden {
                display: none;
            }
            .office-mobile-title {
                flex: 1;
                min-width: 0;
                margin: 0;
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.2;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .sidebar {
                height: 100%;
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }
            .main {
                flex: 1;
                height: 100%;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                min-width: 0;
                min-height: 0;
            }
            .main.main--bleed {
                padding: 0;
                overflow: hidden;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                width: 100%;
            }
            @media (min-width: 768px) {
                platform-island {
                    min-height: calc(var(--app-vh, 100vh) - 2rem);
                }
                .main.main--bleed platform-island {
                    min-height: var(--app-vh, 100vh);
                }
            }
            @media (max-width: 767px) {
                .office-mobile-bar {
                    display: flex;
                }
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }
                .main {
                    padding: 0;
                }
                .main.main--bleed {
                    padding: 0;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._view = 'list';
        this._editBindingId = '';
        this._isMobileLayout = false;
        this._mobileSidebarOpen = false;
        this._showNamespaceModal = false;
        this._onPopState = this._onPopState.bind(this);
        this._onNavigate = this._onNavigate.bind(this);
        this._boundMobileSidebarChange = this._onPlatformSidebarMobileChange.bind(this);
        this._boundCheckMobileLayout = this._checkMobileLayout.bind(this);
        this._resizeObserver = null;
    }

    setupStore() {
        return OfficeStore;
    }

    getBaseUrl() {
        return '/documents';
    }

    async initServices() {
        await super.initServices();
        await this.services.registerCore('/documents');
        this.services.register(
            'officeApi',
            new OfficeAPIService('/documents/api/v1', () => {
                const u = this.services.auth?.user;
                return typeof u?.company_id === 'string' ? u.company_id : '';
            }),
        );
    }

    async checkAuth() {
        const auth = this.auth;
        const ok = await auth.validateToken();
        return !!ok;
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('popstate', this._onPopState);
        window.addEventListener('navigate', this._onNavigate);
        window.addEventListener('platform-sidebar-mobile-change', this._boundMobileSidebarChange);
        this._checkMobileLayout();
        this._resizeObserver = new ResizeObserver(this._boundCheckMobileLayout);
        this._resizeObserver.observe(document.body);
        this._syncRouteFromLocation();
    }

    disconnectedCallback() {
        window.removeEventListener('popstate', this._onPopState);
        window.removeEventListener('navigate', this._onNavigate);
        window.removeEventListener('platform-sidebar-mobile-change', this._boundMobileSidebarChange);
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        super.disconnectedCallback?.();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('_view') || changedProperties.has('_editBindingId')) {
            queueMicrotask(() => {
                this.shadowRoot?.querySelector('office-sidebar')?.closeMobile();
            });
        }
    }

    _checkMobileLayout() {
        const next = window.innerWidth <= 767;
        if (next !== this._isMobileLayout) {
            this._isMobileLayout = next;
            this.requestUpdate();
        }
    }

    _onPlatformSidebarMobileChange(e) {
        const open = e.detail?.open;
        if (typeof open !== 'boolean') {
            throw new Error('platform-sidebar-mobile-change: expected detail.open boolean');
        }
        this._mobileSidebarOpen = open;
        this.requestUpdate();
    }

    _openMobileSidebar() {
        window.dispatchEvent(
            new CustomEvent('platform-sidebar-open', { bubbles: true, composed: true }),
        );
    }

    _mobileBarTitle(isEdit, isCatalogs) {
        if (isEdit) {
            return this.i18n.t('mobile.editorTitle');
        }
        if (isCatalogs) {
            return this.i18n.t('mobile.catalogsTitle');
        }
        return this.i18n.t('list.heading');
    }

    _syncRouteFromLocation() {
        const path = (window.location.pathname || '/documents').replace(/\/$/, '') || '/documents';
        const base = '/documents';
        if (!path.startsWith(base)) {
            this._view = 'list';
            this._editBindingId = '';
            return;
        }
        const rest = path.slice(base.length).replace(/^\//, '');
        if (rest.startsWith('edit/')) {
            const raw = decodeURIComponent(rest.slice(5));
            if (!isPlausibleOfficeBindingId(raw)) {
                window.history.replaceState({}, '', '/documents');
                this._view = 'list';
                this._editBindingId = '';
                return;
            }
            this._editBindingId = raw;
            this._view = 'edit';
        } else if (rest === 'catalogs') {
            this._view = 'catalogs';
            this._editBindingId = '';
        } else if (rest.startsWith('catalog/')) {
            const raw = rest.slice(8);
            const cid = decodeURIComponent(raw).trim();
            if (cid) {
                OfficeStore.setActiveCatalogId(cid);
                OfficeStore.setFilterCatalogIds([cid]);
            }
            window.history.replaceState({}, '', '/documents');
            this._view = 'list';
            this._editBindingId = '';
            queueMicrotask(() =>
                window.dispatchEvent(new CustomEvent('office-documents-list-reload', { bubbles: true })),
            );
        } else {
            this._view = 'list';
            this._editBindingId = '';
        }
    }

    _onPopState() {
        this._syncRouteFromLocation();
        this.requestUpdate();
    }

    _onNavigate(e) {
        const path = e.detail?.path;
        if (typeof path !== 'string' || path === '') {
            return;
        }
        window.history.pushState({}, '', path);
        this._syncRouteFromLocation();
        this.requestUpdate();
    }

    _openNamespaceModal() {
        this._showNamespaceModal = true;
    }

    _closeNamespaceModal() {
        this._showNamespaceModal = false;
    }

    _onOfficeNamespaceSaved(e) {
        this._showNamespaceModal = false;
        const name = e.detail?.name;
        const cid = this.services?.auth?.user?.company_id;
        if (typeof name === 'string' && name.trim() && typeof cid === 'string' && cid.trim()) {
            setActivePlatformNamespaceName(cid.trim(), name.trim());
            OfficeStore.setActiveCatalogId('');
        }
        window.dispatchEvent(new CustomEvent('office-sidebar-reload-namespaces', { bubbles: true }));
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }
        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }
        if (!this._isAuthenticated) {
            return html`<app-loader></app-loader>`;
        }
        const isEdit = this._view === 'edit' && this._editBindingId;
        const isCatalogs = this._view === 'catalogs';
        const mainContent = isEdit
            ? html`<document-editor-page .bindingId=${this._editBindingId}></document-editor-page>`
            : isCatalogs
              ? html`<office-catalogs-dashboard></office-catalogs-dashboard>`
              : html`<documents-list-page></documents-list-page>`;
        const activeView = isEdit ? 'edit' : isCatalogs ? 'catalogs' : 'list';
        const showMobileMenu = this._isMobileLayout && !this._mobileSidebarOpen;
        const openSidebarLabel = this.i18n.t('mobile.openSidebar');
        return html`
            <div class="office-shell">
                <header class="office-mobile-bar">
                    <button
                        type="button"
                        class="menu-btn ${showMobileMenu ? '' : 'hidden'}"
                        title=${openSidebarLabel}
                        aria-label=${openSidebarLabel}
                        @click=${this._openMobileSidebar}
                    >
                        <platform-icon name="menu" size="20"></platform-icon>
                    </button>
                    ${isEdit
                        ? html`
                              <button
                                  type="button"
                                  class="office-mobile-back"
                                  title=${this.i18n.t('editor.back')}
                                  aria-label=${this.i18n.t('editor.back')}
                                  @click=${() =>
                                      window.dispatchEvent(
                                          new CustomEvent('navigate', {
                                              detail: { path: '/documents' },
                                          }),
                                      )}
                              >
                                  <platform-icon name="chevron-left" size="20"></platform-icon>
                              </button>
                          `
                        : null}
                    <h1 class="office-mobile-title">
                        ${this._mobileBarTitle(!!isEdit, isCatalogs)}
                    </h1>
                </header>
                <div class="office-content-row">
                    <div class="sidebar">
                        <office-sidebar
                            .activeView=${activeView}
                            @open-namespace-modal=${this._openNamespaceModal}
                        ></office-sidebar>
                    </div>
                    <div class="main ${isEdit ? 'main--bleed' : ''}">
                        <platform-island
                            ?content-no-scroll=${isEdit}
                            padding=${isEdit ? 'none' : 'md'}
                        >
                            ${mainContent}
                        </platform-island>
                    </div>
                </div>
            </div>
            <office-documents-shell-actions></office-documents-shell-actions>
            ${this._showNamespaceModal
                ? html`
                      <office-namespace-modal
                          .open=${true}
                          @modal-closed=${this._closeNamespaceModal}
                          @saved=${this._onOfficeNamespaceSaved}
                      ></office-namespace-modal>
                  `
                : null}
            <pwa-install-banner></pwa-install-banner>
        `;
    }
}

customElements.define('office-app', OfficeApp);

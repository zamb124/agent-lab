/**
 * Entities Page - Страница списка сущностей с фильтрами и детальной карточкой
 * Desktop: 3-колоночный layout (filters | list | card)
 * Mobile: Табы (filters | list | card)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/entity-filters.js';
import '../components/entities-list.js';
import '../components/entity-card.js';
import '@platform/lib/components/platform-icon.js';

export class EntitiesPage extends PlatformElement {
    static properties = {
        _currentEntityId: { state: true },
        _isMobile: { state: true },
        _entitiesLoading: { state: true },
        _activeMobilePanel: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                width: 100%;
                height: 100%;
                gap: var(--space-4);
                overflow: hidden;
            }

            entity-filters {
                width: 280px;
                height: 100%;
                flex-shrink: 0;
            }
            
            entity-filters[collapsed] {
                width: 48px;
                flex: 0 0 48px;
            }

            entities-list {
                width: 320px;
                height: 100%;
                flex-shrink: 0;
            }
            
            entities-list[collapsed] {
                width: 48px;
                flex: 0 0 48px;
            }

            entity-card {
                flex: 1;
                height: 100%;
                min-width: 0;
            }

            @media (min-width: 768px) and (max-width: 1023px) {
                entity-filters {
                    width: 240px;
                }
            }

            @media (max-width: 767px) {
                :host {
                    flex-direction: column;
                    padding: 0;
                    gap: 0;
                }
                
                
                .mobile-panels-container {
                    display: flex;
                    flex-direction: column;
                    width: 100%;
                    height: 100%;
                    overflow: hidden;
                }
                
                .mobile-panel entity-filters,
                .mobile-panel entities-list,
                .mobile-panel entity-card {
                    display: flex !important;
                    flex-direction: column;
                }
                
                .mobile-panel entity-filters:not(.active-panel),
                .mobile-panel entities-list:not(.active-panel),
                .mobile-panel entity-card:not(.active-panel) {
                    display: none !important;
                }
                
                .mobile-tabs {
                    display: flex;
                    padding: var(--space-2);
                    gap: var(--space-2);
                    background: var(--crm-surface-muted);
                    border-bottom: 1px solid var(--crm-stroke);
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
                    background: var(--crm-surface-muted);
                    border: 1px solid var(--crm-stroke);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                }
                
                .menu-btn:hover {
                    background: var(--crm-surface);
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
                    background: var(--crm-surface);
                    color: var(--text-primary);
                }
                
                .mobile-tab.active {
                    background: var(--crm-selected-bg);
                    border-color: var(--crm-selected-stroke);
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
        `
    ];

    constructor() {
        super();
        this._currentEntityId = null;
        this._isMobile = false;
        this._entitiesLoading = false;
        this._activeMobilePanel = 'list';

        this._unsubscribe = CRMStore.subscribe(state => {
            this._currentEntityId = state.entities.currentEntityId;
            this._isMobile = state.ui.isMobile;
            this._entitiesLoading = state.entities.entitiesLoading;
        });
    }

    async firstUpdated() {
        await this._loadEntities();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    async _loadEntities() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntities(crmApi);
    }

    _setMobilePanel(panelId) {
        this._activeMobilePanel = panelId;
    }

    _onEntitySelected() {
        if (this._isMobile) {
            this._activeMobilePanel = 'card';
        }
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    _renderMobileView() {
        const panels = [
            { id: 'filters', label: 'Фильтры', icon: 'filter' },
            { id: 'list', label: 'Список', icon: 'list' },
        ];
        
        if (this._currentEntityId) {
            panels.push({ id: 'card', label: 'Карточка', icon: 'file' });
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
        return html`
            <entity-filters 
                class="${this._activeMobilePanel === 'filters' ? 'active-panel' : ''}" 
                collapsible="false"
            ></entity-filters>
            <entities-list 
                class="${this._activeMobilePanel === 'list' ? 'active-panel' : ''}" 
                collapsible="false" 
                @entity-selected=${this._onEntitySelected}
            ></entities-list>
            <entity-card 
                class="${this._activeMobilePanel === 'card' ? 'active-panel' : ''}" 
                .entityId=${this._currentEntityId}
            ></entity-card>
        `;
    }

    render() {
        if (this._isMobile) {
            return this._renderMobileView();
        }

        return html`
            <entity-filters></entity-filters>
            <entities-list></entities-list>
            <entity-card .entityId=${this._currentEntityId}></entity-card>
        `;
    }
}

customElements.define('entities-page', EntitiesPage);

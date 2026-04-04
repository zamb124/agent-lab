/**
 * Панель фильтров списка сущностей (CRMPanel).
 */
import { html, css } from 'lit';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMPanel } from './crm-panel.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

export class EntityFilters extends CRMPanel {
    static properties = {
        ...CRMPanel.properties,
        _filters: { state: true },
        _entityTypes: { state: true },
        _selectedType: { state: true },
        _currentNamespace: { state: true },
    };

    static styles = [
        CRMPanel.panelStyles,
        formStyles,
        buttonStyles,
        css`
            .content {
                padding: var(--space-4);
                overflow-y: auto;
                flex: 1;
            }

            .filter-group {
                margin-bottom: var(--space-4);
            }

            .filter-label {
                display: block;
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }

            .filter-input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                transition: all var(--duration-fast);
                box-sizing: border-box;
            }

            .filter-input:focus {
                outline: none;
                border-color: var(--accent);
                background: var(--crm-surface);
            }

            .type-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .type-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .type-chip:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .type-chip.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .type-chip .chip-icon {
                font-size: var(--text-base);
            }

            .date-row {
                display: flex;
                gap: var(--space-2);
            }

            .date-row .filter-input,
            .date-row platform-date-picker {
                flex: 1;
            }

            .clear-btn {
                width: 100%;
                margin-top: var(--space-4);
                padding: var(--space-2) var(--space-3);
                background: transparent;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .clear-btn:hover {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }

            .namespace-indicator {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-4);
            }

            .namespace-indicator-icon {
                font-size: var(--text-lg);
            }

            .namespace-indicator-content {
                flex: 1;
            }

            .namespace-indicator-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .namespace-indicator-value {
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--crm-selected-text);
            }
        `
    ];

    constructor() {
        super();
        this.panelId = 'entity-filters';
        this.panelTitle = '';
        this.panelIcon = 'adjustment';
        
        this._filters = {
            entity_type: null,
            entity_subtype: null,
            date_from: null,
            date_to: null,
            tags: [],
            search: '',
        };
        this._entityTypes = [];
        this._selectedType = null;
        this._currentNamespace = null;
        this._applyFiltersTimer = null;

        this._filtersUnsubscribe = CRMStore.subscribe(state => {
            this._filters = state.entities.filters;
            this._entityTypes = state.entities.entityTypes || [];
            this._selectedType = state.entities.filters.entity_type;
            this._currentNamespace = state.namespaces.current;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this.panelTitle = this.i18n.t('entity_filters.panel_title');
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._filtersUnsubscribe?.();
        if (this._applyFiltersTimer) {
            clearTimeout(this._applyFiltersTimer);
            this._applyFiltersTimer = null;
        }
    }

    _onSearchInput(e) {
        CRMStore.setEntityFilters({ search: e.target.value });
        this._applyFiltersDebounced();
    }

    _onTypeSelect(typeId) {
        const newType = this._selectedType === typeId ? null : typeId;
        CRMStore.setEntityFilters({
            entity_type: newType,
            entity_subtype: null,
        });
        this._applyFilters();
    }

    _onSubtypeSelect(subtypeId) {
        const newSubtype = this._filters.entity_subtype === subtypeId ? null : subtypeId;
        CRMStore.setEntityFilters({ entity_subtype: newSubtype });
        this._applyFilters();
    }

    _onDateRangeChange(e) {
        const nextRange = e.target.value;
        if (nextRange && typeof nextRange !== 'object') {
            throw new Error('Date range value must be object');
        }
        CRMStore.setEntityFilters({
            date_from: nextRange?.start || null,
            date_to: nextRange?.end || null,
        });
        this._applyFilters();
    }

    _onClearFilters() {
        CRMStore.clearEntityFilters();
        this._applyFilters();
    }

    async _applyFilters() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadEntities(crmApi);
    }

    _applyFiltersDebounced() {
        if (this._applyFiltersTimer) {
            clearTimeout(this._applyFiltersTimer);
        }
        this._applyFiltersTimer = setTimeout(() => {
            this._applyFiltersTimer = null;
            this._applyFilters();
        }, 250);
    }

    _getBaseTypes() {
        return this._entityTypes.filter(t => !t.parent_type_id);
    }

    _getSubtypes(parentTypeId) {
        return this._entityTypes.filter(t => t.parent_type_id === parentTypeId);
    }

    _getCurrentNamespaceName() {
        if (!this._currentNamespace) {
            return '';
        }
        if (typeof this._currentNamespace === 'string') {
            return this._currentNamespace;
        }
        if (typeof this._currentNamespace === 'object' && typeof this._currentNamespace.name === 'string') {
            return this._currentNamespace.name;
        }
        throw new Error('Invalid namespace in filters state');
    }

    _resolveIconName(iconName) {
        if (iconName === 'file') {
            return 'folder';
        }
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'folder';
    }

    renderContent() {
        const baseTypes = this._getBaseTypes();
        const subtypes = this._selectedType
            ? this._getSubtypes(this._selectedType)
            : [];

        return html`
            <div class="content">
                ${this._currentNamespace ? html`
                    <div class="namespace-indicator">
                        <span class="namespace-indicator-icon">
                            <platform-icon name="folder" size="16"></platform-icon>
                        </span>
                        <div class="namespace-indicator-content">
                            <div class="namespace-indicator-label">${this.i18n.t('entity_filters.namespace_label')}</div>
                                <div class="namespace-indicator-value">${this._getCurrentNamespaceName()}</div>
                        </div>
                    </div>
                ` : ''}

                <div class="filter-group">
                    <label class="filter-label">${this.i18n.t('entity_filters.search_label')}</label>
                    <input
                        type="text"
                        class="filter-input"
                        placeholder=${this.i18n.t('entity_filters.search_placeholder')}
                        .value=${this._filters.search || ''}
                        @input=${this._onSearchInput}
                    />
                </div>

                <div class="filter-group">
                    <label class="filter-label">${this.i18n.t('entity_filters.type_label')}</label>
                    <div class="type-chips">
                        ${baseTypes.map(type => html`
                            <button
                                class="type-chip ${this._selectedType === type.type_id ? 'active' : ''}"
                                @click=${() => this._onTypeSelect(type.type_id)}
                            >
                                <span class="chip-icon">
                                    <platform-icon name="${this._resolveIconName(type.icon)}" size="15"></platform-icon>
                                </span>
                                <span>${type.name}</span>
                            </button>
                        `)}
                    </div>
                </div>

                ${subtypes.length > 0 ? html`
                    <div class="filter-group">
                        <label class="filter-label">${this.i18n.t('entity_filters.subtype_label')}</label>
                        <div class="type-chips">
                            ${subtypes.map(type => html`
                                <button
                                    class="type-chip ${this._filters.entity_subtype === type.type_id ? 'active' : ''}"
                                    @click=${() => this._onSubtypeSelect(type.type_id)}
                                >
                                    <span class="chip-icon">
                                        <platform-icon name="${this._resolveIconName(type.icon)}" size="15"></platform-icon>
                                    </span>
                                    <span>${type.name}</span>
                                </button>
                            `)}
                        </div>
                    </div>
                ` : ''}

                <div class="filter-group">
                    <label class="filter-label">${this.i18n.t('entity_filters.date_label')}</label>
                    <div class="date-row">
                        <platform-date-picker
                            class="filter-input"
                            mode="date"
                            selection="range"
                            value-format="iso"
                            .value=${{
                                start: this._filters.date_from || null,
                                end: this._filters.date_to || null,
                            }}
                            @change=${this._onDateRangeChange}
                        ></platform-date-picker>
                    </div>
                </div>

                <button class="clear-btn" @click=${this._onClearFilters}>
                    ${this.i18n.t('entity_filters.reset')}
                </button>
            </div>
        `;
    }
}

customElements.define('entity-filters', EntityFilters);

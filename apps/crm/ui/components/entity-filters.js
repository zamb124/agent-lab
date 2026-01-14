/**
 * Entity Filters - Панель фильтрации сущностей
 * Наследует CRMPanel для поддержки сворачивания
 */
import { html, css } from 'lit';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMPanel } from './crm-panel.js';
import { CRMStore } from '../store/crm.store.js';

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
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                transition: all 0.2s;
                box-sizing: border-box;
            }

            .filter-input:focus {
                outline: none;
                border-color: var(--accent);
                background: var(--glass-solid-medium);
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
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all 0.2s;
            }

            .type-chip:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .type-chip.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .type-chip .chip-icon {
                font-size: var(--text-base);
            }

            .date-row {
                display: flex;
                gap: var(--space-2);
            }

            .date-row .filter-input {
                flex: 1;
            }

            .clear-btn {
                width: 100%;
                margin-top: var(--space-4);
                padding: var(--space-2) var(--space-3);
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all 0.2s;
            }

            .clear-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .namespace-indicator {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--accent-subtle);
                border: 1px solid var(--accent);
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
                color: var(--accent);
            }
        `
    ];

    constructor() {
        super();
        this.panelId = 'entity-filters';
        this.panelTitle = 'Фильтры';
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

        this._filtersUnsubscribe = CRMStore.subscribe(state => {
            this._filters = state.entities.filters;
            this._entityTypes = state.entities.entityTypes || [];
            this._selectedType = state.entities.filters.entity_type;
            this._currentNamespace = state.namespaces.current;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._filtersUnsubscribe?.();
    }

    _onSearchInput(e) {
        CRMStore.setEntityFilters({ search: e.target.value });
        this._applyFilters();
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

    _onDateFromChange(e) {
        CRMStore.setEntityFilters({ date_from: e.target.value || null });
        this._applyFilters();
    }

    _onDateToChange(e) {
        CRMStore.setEntityFilters({ date_to: e.target.value || null });
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

    _getBaseTypes() {
        return this._entityTypes.filter(t => !t.parent_type_id);
    }

    _getSubtypes(parentTypeId) {
        return this._entityTypes.filter(t => t.parent_type_id === parentTypeId);
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
                        <span class="namespace-indicator-icon">📁</span>
                        <div class="namespace-indicator-content">
                            <div class="namespace-indicator-label">Пространство</div>
                            <div class="namespace-indicator-value">${this._currentNamespace}</div>
                        </div>
                    </div>
                ` : ''}

                <div class="filter-group">
                    <label class="filter-label">Поиск</label>
                    <input
                        type="text"
                        class="filter-input"
                        placeholder="Имя, описание..."
                        .value=${this._filters.search || ''}
                        @input=${this._onSearchInput}
                    />
                </div>

                <div class="filter-group">
                    <label class="filter-label">Тип</label>
                    <div class="type-chips">
                        ${baseTypes.map(type => html`
                            <button
                                class="type-chip ${this._selectedType === type.type_id ? 'active' : ''}"
                                @click=${() => this._onTypeSelect(type.type_id)}
                            >
                                <span class="chip-icon">${type.icon || '📄'}</span>
                                <span>${type.name}</span>
                            </button>
                        `)}
                    </div>
                </div>

                ${subtypes.length > 0 ? html`
                    <div class="filter-group">
                        <label class="filter-label">Подтип</label>
                        <div class="type-chips">
                            ${subtypes.map(type => html`
                                <button
                                    class="type-chip ${this._filters.entity_subtype === type.type_id ? 'active' : ''}"
                                    @click=${() => this._onSubtypeSelect(type.type_id)}
                                >
                                    <span class="chip-icon">${type.icon || '📄'}</span>
                                    <span>${type.name}</span>
                                </button>
                            `)}
                        </div>
                    </div>
                ` : ''}

                <div class="filter-group">
                    <label class="filter-label">Дата</label>
                    <div class="date-row">
                        <input
                            type="date"
                            class="filter-input"
                            .value=${this._filters.date_from || ''}
                            @change=${this._onDateFromChange}
                        />
                        <input
                            type="date"
                            class="filter-input"
                            .value=${this._filters.date_to || ''}
                            @change=${this._onDateToChange}
                        />
                    </div>
                </div>

                <button class="clear-btn" @click=${this._onClearFilters}>
                    Сбросить фильтры
                </button>
            </div>
        `;
    }
}

customElements.define('entity-filters', EntityFilters);

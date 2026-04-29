/**
 * CRMEntityDetailPage — страница карточки одной сущности CRM.
 *
 * Маршрут: `/crm/entities/:itemId` (роутер передаёт `itemId` через `params`).
 * Редактирование: query `?edit=1`, тело вкладки «Карточка» — `<crm-entity-card>`.
 *
 * Источники данных:
 *   - `useResource('crm/entities')`           — entity по id (GET /entities/{id}).
 *   - `useOp('crm/entity_card')`              — related/relationships/attachments.
 *   - `useResource('crm/relationship_types')` — подписи типов связей.
 *
 * UI: breadcrumbs → одна строка page-header (title + subtitle слева, действия в slot actions) →
 * вкладки → контент. Карточка: `crm-entity-card`; в режиме `?edit=1` тулбар редактирования
 * в шапке страницы (`host-toolbar` на карточке).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '../components/mini-graph-preview.js';
import '../components/entity-card.js';
import '../components/crm-related-neighbor-rows.js';
import { extractNeighborEdges } from '../utils/neighbor-edges.js';
import { searchScorePercent, relationshipConfidencePercent } from '../utils/search-score-percent.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_CARD_OP = 'crm/entity_card';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const REL_TYPES_NAME = 'crm/relationship_types';

const TAB_CARD = 'card';
const TAB_RELATIONS = 'relations';
const TAB_GRAPH = 'graph';
const TAB_ATTACHMENTS = 'attachments';
const ALL_TABS = [TAB_CARD, TAB_RELATIONS, TAB_GRAPH, TAB_ATTACHMENTS];

function _formatBytes(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '';
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function _isEditSearch(searchRaw) {
    const raw = typeof searchRaw === 'string' ? searchRaw : '';
    const q = raw.startsWith('?') ? raw.slice(1) : raw;
    return new URLSearchParams(q).get('edit') === '1';
}

export class CRMEntityDetailPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        itemId: { type: String },
        _card: { state: true },
        _cardError: { state: true },
        _activeTab: { state: true },
        _editToolbarSaveDisabled: { state: true },
        _editToolbarSubmitting: { state: true },
        _templatePickerOpen: { state: true },
        _draftStorageTypePair: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .header-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
            }

            .detail-header-actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
            }
            .detail-template-box {
                display: inline-flex;
                flex-direction: row;
                align-items: center;
                gap: 10px;
                box-sizing: border-box;
                min-height: 40px;
                min-width: 0;
                max-width: min(480px, 100%);
                padding: 0 14px;
                background: rgba(34, 34, 34, 0.06);
                border-radius: 20px;
            }
            .detail-template-select {
                flex: 1;
                min-width: 120px;
                max-width: 260px;
                height: 32px;
                border-radius: 10px;
                border: 1px solid var(--crm-stroke);
                padding: 0 10px;
                font-size: 14px;
                font-weight: 600;
                color: var(--text-primary);
                background: var(--crm-surface);
                box-sizing: border-box;
            }
            .detail-template-pencil {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 4px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                box-sizing: border-box;
            }
            .detail-template-pencil:hover:not(:disabled) {
                color: var(--text-primary);
                background: rgba(34, 34, 34, 0.06);
            }
            .detail-template-pencil:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .detail-template-label {
                flex-shrink: 0;
                font-size: 9px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: rgba(34, 34, 34, 0.42);
                line-height: 1;
            }
            .detail-template-value {
                flex: 1;
                min-width: 0;
                font-size: 14px;
                font-weight: 600;
                color: var(--text-primary);
                line-height: 1.2;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .toolbar-pill {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 40px;
                padding: 0 18px;
                border: none;
                border-radius: 20px;
                font-size: var(--text-sm);
                font-weight: 600;
                cursor: pointer;
            }
            .toolbar-pill:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .toolbar-pill-primary {
                background: #7b92ff;
                color: #fff;
            }
            .toolbar-pill-primary:hover:not(:disabled) {
                filter: brightness(1.06);
            }
            .toolbar-pill-ghost {
                background: rgba(34, 34, 34, 0.06);
                color: var(--text-secondary);
            }
            .toolbar-pill-ghost:hover:not(:disabled) {
                background: rgba(34, 34, 34, 0.1);
                color: var(--text-primary);
            }
            .toolbar-pill-muted {
                background: rgba(34, 34, 34, 0.06);
                color: var(--text-secondary);
                border: 1px solid transparent;
            }
            .toolbar-pill-muted:hover:not(:disabled) {
                background: rgba(34, 34, 34, 0.09);
                color: var(--text-primary);
            }
            .toolbar-pill-danger {
                background: transparent;
                color: #c2410c;
                border: 1px solid rgba(249, 115, 22, 0.45);
            }
            .toolbar-pill-danger:hover:not(:disabled) {
                background: rgba(249, 115, 22, 0.12);
            }
            .toolbar-icon-danger {
                width: 40px;
                height: 40px;
                padding: 0;
                border: none;
                border-radius: 14px;
                background: rgba(249, 115, 22, 0.18);
                color: #c2410c;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .toolbar-icon-danger:hover:not(:disabled) {
                background: rgba(249, 115, 22, 0.28);
            }
            .toolbar-icon-muted {
                width: 40px;
                height: 40px;
                padding: 0;
                border: none;
                border-radius: 14px;
                background: rgba(34, 34, 34, 0.06);
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .toolbar-icon-muted:hover:not(:disabled) {
                background: rgba(34, 34, 34, 0.1);
                color: var(--text-primary);
            }
            .toolbar-icon-muted:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .tabs {
                display: flex;
                gap: 2px;
                padding: 0 var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                flex-shrink: 0;
            }
            .tab {
                padding: var(--space-2) var(--space-4);
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                margin-bottom: -1px;
            }
            .tab.active {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: var(--space-4);
                overflow-y: auto;
                width: 100%;
                box-sizing: border-box;
            }
            .body.detail-body-muted {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                background: rgba(34, 34, 34, 0.02);
            }
            .body.detail-body-muted crm-entity-card {
                flex: 1;
                min-height: 400px;
                width: 100%;
                align-self: stretch;
            }
            crm-entity-card.edit-card-hidden-host {
                display: none !important;
            }
            .body.graph { overflow: hidden; padding: 0; display: flex; }
            .body.graph crm-mini-graph-preview { flex: 1; min-height: 0; }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                height: 100%;
                color: var(--text-secondary);
                text-align: center;
                padding: var(--space-6);
            }
            .center .icon { color: var(--text-tertiary); }
            .center h2 {
                margin: 0;
                font-size: var(--text-lg);
                color: var(--text-primary);
            }

            .btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--accent);
                color: white;
                border-color: var(--accent);
            }
            .btn-primary:hover:not(:disabled) { filter: brightness(1.05); }
            .btn-danger {
                color: var(--color-danger);
                border-color: var(--color-danger);
            }
            .btn-danger:hover:not(:disabled) {
                background: var(--color-danger);
                color: white;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .card-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                width: 100%;
                max-width: none;
            }
            .description {
                color: var(--text-primary);
                font-size: var(--text-base);
                line-height: 1.5;
                white-space: pre-wrap;
            }
            .empty-text {
                color: var(--text-tertiary);
                font-style: italic;
                font-size: var(--text-sm);
            }
            .tags {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .tag {
                display: inline-flex;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                background: var(--crm-selected-bg, var(--glass-tint-medium));
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .attrs {
                display: grid;
                grid-template-columns: minmax(140px, 1fr) 3fr;
                row-gap: 8px;
                column-gap: var(--space-3);
                font-size: var(--text-sm);
            }
            .attr-key {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                padding-top: 2px;
            }
            .attr-val {
                color: var(--text-primary);
                word-break: break-word;
                white-space: pre-wrap;
            }

            .section-title {
                margin: 0;
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                width: 100%;
            }
            .list-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
            }
            .list-row.clickable {
                cursor: pointer;
                background: var(--glass-tint-subtle);
                border-color: transparent;
            }
            .list-row.clickable:hover { background: var(--glass-tint-medium); }
            .list-row .icon {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                color: var(--accent);
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            .list-row .meta {
                display: flex;
                flex-direction: column;
                min-width: 0;
                flex: 1;
            }
            .list-row .name {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .list-row .sub {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .list-row .arrow { color: var(--text-tertiary); }
            .list-row a {
                color: var(--accent);
                text-decoration: none;
                font-size: var(--text-xs);
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            .list-row a:hover { text-decoration: underline; }
        `,
    ];

    constructor() {
        super();
        this.itemId = '';
        this._card = null;
        this._cardError = '';
        this._activeTab = TAB_CARD;
        this._lastRequestedId = '';
        this._editToolbarSaveDisabled = true;
        this._editToolbarSubmitting = false;
        this._templatePickerOpen = false;
        this._draftStorageTypePair = { entity_type: '', entity_subtype: '' };
        this._entityTypesQueryNs = '';
        this._onCardToolbarStateBound = this._onCardToolbarState.bind(this);
        this._onCardStorageTypeDraftBound = this._onCardStorageTypeDraft.bind(this);

        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME, { autoload: false });
        this._cardOp = this.useOp(ENTITY_CARD_OP);
        this._relTypes = this.useResource(REL_TYPES_NAME, { autoload: true });
        this._routerSearchSel = this.select((s) => s.router.search);
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.shadowRoot) {
            this.shadowRoot.addEventListener('crm-entity-card-toolbar-state', this._onCardToolbarStateBound);
            this.shadowRoot.addEventListener('crm-entity-card-storage-type-draft', this._onCardStorageTypeDraftBound);
        }

        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => {
            const result = event.payload && event.payload.result ? event.payload.result : null;
            if (!result || typeof result !== 'object') {
                throw new Error('crm/entity_card SUCCEEDED: payload.result missing');
            }
            this._card = result;
            this._cardError = '';
        });
        this.useEvent(this._cardOp.op.events.FAILED, (event) => {
            const err = event.payload && event.payload.error ? event.payload.error : null;
            this._card = null;
            this._cardError = err && typeof err.message === 'string' ? err.message : 'load_failed';
        });

        this.useEvent(this._entities.resource.events.REMOVED, (event) => {
            const payload = event && event.payload;
            const idField = this._entities.resource.idField;
            const removedId = payload && typeof payload[idField] === 'string' ? payload[idField] : null;
            if (removedId !== this.itemId) return;
            this.navigate('entities');
        });
    }

    disconnectedCallback() {
        if (this.shadowRoot) {
            this.shadowRoot.removeEventListener('crm-entity-card-toolbar-state', this._onCardToolbarStateBound);
            this.shadowRoot.removeEventListener('crm-entity-card-storage-type-draft', this._onCardStorageTypeDraftBound);
        }
        super.disconnectedCallback();
    }

    _onCardToolbarState(ev) {
        const d = ev.detail;
        if (!d || typeof d.saveDisabled !== 'boolean' || typeof d.submitting !== 'boolean') {
            throw new Error('crm-entity-card-toolbar-state: invalid detail');
        }
        this._editToolbarSaveDisabled = d.saveDisabled;
        this._editToolbarSubmitting = d.submitting;
    }

    _onCardStorageTypeDraft(ev) {
        const d = ev.detail;
        if (!d || typeof d.entity_type !== 'string' || typeof d.entity_subtype !== 'string') {
            throw new Error('crm-entity-card-storage-type-draft: invalid detail');
        }
        this._draftStorageTypePair = { entity_type: d.entity_type, entity_subtype: d.entity_subtype };
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('itemId')) {
            if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
                this._card = null;
                this._cardError = '';
                this._lastRequestedId = '';
            } else if (this._lastRequestedId !== this.itemId) {
                this._lastRequestedId = this.itemId;
                this._activeTab = TAB_CARD;
                this._reload();
            }
        }
        const editing = this._isEditingCard();
        if (!editing) {
            if (this._templatePickerOpen) {
                this._templatePickerOpen = false;
            }
            if (this._draftStorageTypePair.entity_type !== '' || this._draftStorageTypePair.entity_subtype !== '') {
                this._draftStorageTypePair = { entity_type: '', entity_subtype: '' };
            }
            return;
        }
        const entity = this._entity();
        if (!entity || typeof entity.namespace !== 'string' || entity.namespace.length === 0) {
            return;
        }
        if (this._entityTypesQueryNs !== entity.namespace) {
            this._entityTypesQueryNs = entity.namespace;
            this._entityTypes.load({ namespace: entity.namespace });
        }
    }

    _reload() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) return;
        this._entities.get(this.itemId);
        this._cardOp.run({ entity_id: this.itemId });
    }

    _entity() {
        const byId = this._entities.byId;
        if (byId && byId[this.itemId]) return byId[this.itemId];
        return null;
    }

    _onPickTab(tab) {
        if (ALL_TABS.indexOf(tab) === -1) return;
        this._activeTab = tab;
    }

    _isEditingCard() {
        return _isEditSearch(this._routerSearchSel.value);
    }

    _onEdit() {
        this.navigate('entity', { itemId: this.itemId }, { search: '?edit=1' });
        this._activeTab = TAB_CARD;
    }

    _onCardSaved() {
        this._editToolbarSaveDisabled = true;
        this._editToolbarSubmitting = false;
        this._reload();
        this.navigate('entity', { itemId: this.itemId });
    }

    _onCardEditCancelled() {
        this._editToolbarSaveDisabled = true;
        this._editToolbarSubmitting = false;
        this.navigate('entity', { itemId: this.itemId });
    }

    _onShare() {
        this.openModal('crm.share', { entityId: this.itemId });
    }

    _onAccessRequest() {
        this.openModal('crm.access_request', { entityId: this.itemId });
    }

    _onDelete() {
        this.openModal('crm.entity_delete', { entityId: this.itemId, redirectRoute: 'entities' });
    }

    _onMiniGraphEntityOpen(event) {
        const entityId = event.detail && event.detail.entityId ? event.detail.entityId : '';
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        if (entityId === this.itemId) return;
        this.navigate('entity', { itemId: entityId });
    }

    _onRelatedClick(entityId) {
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        if (entityId === this.itemId) return;
        this.navigate('entity', { itemId: entityId });
    }

    _relationshipTypeLabel(typeId) {
        const items = Array.isArray(this._relTypes.items) ? this._relTypes.items : [];
        const found = items.find((rt) => rt && rt.type_id === typeId);
        if (found && typeof found.name === 'string' && found.name.length > 0) return found.name;
        return typeId;
    }

    render() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="info" size="48"></platform-icon>
                        <h2>${this.t('entity_detail_page.no_id_title')}</h2>
                        <button class="btn" type="button" @click=${() => this.navigate('entities')}>
                            ${this.t('entity_detail_page.back_to_entities')}
                        </button>
                    </div>
                </div>
            `;
        }

        if (this._cardError) {
            return html`
                <div class="body">
                    <div class="center">
                        <platform-icon class="icon" name="warning" size="48"></platform-icon>
                        <h2>${this.t('entity_detail_page.not_found_title')}</h2>
                        <p>${this._cardError}</p>
                        <button class="btn" type="button" @click=${() => this.navigate('entities')}>
                            ${this.t('entity_detail_page.back_to_entities')}
                        </button>
                    </div>
                </div>
            `;
        }

        const entity = this._entity();
        if (entity === null || this._entities.loading) {
            return html`
                <div class="body">
                    <div class="center">
                        <glass-spinner size="lg"></glass-spinner>
                    </div>
                </div>
            `;
        }

        const isBusy = this._entities.isBusy(this.itemId);

        const entityLabel = typeof entity.name === 'string' && entity.name.length > 0
            ? entity.name
            : this.itemId;
        const editingCard = this._isEditingCard();
        const baseSubtitle = this._buildSubtitle(entity);
        const headerSubtitle = editingCard
            ? `${this.t('entity_card.edit_object_title')} · ${baseSubtitle}`
            : baseSubtitle;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${entityLabel}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    dense
                    title=${entityLabel}
                    subtitle=${headerSubtitle}
                >
                    <div slot="actions" class="detail-header-actions">
                        ${this._renderDetailHeaderActions(entity, editingCard, isBusy)}
                    </div>
                </page-header>
            </div>
            <div class="tabs">
                ${ALL_TABS.map((tab) => html`
                    <button
                        type="button"
                        class="tab ${this._activeTab === tab ? 'active' : ''}"
                        @click=${() => this._onPickTab(tab)}
                    >
                        ${this.t(`entity_detail_page.tab_${tab}`)}
                    </button>
                `)}
            </div>
            ${this._renderActiveTab(entity)}
        `;
    }

    _detailStoragePairForTemplateUi(entity) {
        const d = this._draftStorageTypePair;
        if (typeof d.entity_type === 'string' && d.entity_type.length > 0) {
            const stRaw = typeof d.entity_subtype === 'string' ? d.entity_subtype.trim() : '';
            return { entity_type: d.entity_type, subtypeNorm: stRaw.length > 0 ? stRaw : null };
        }
        if (!entity || typeof entity.entity_type !== 'string' || entity.entity_type.length === 0) {
            throw new Error('CRMEntityDetailPage._detailStoragePairForTemplateUi: entity_type required');
        }
        const stRaw = typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0
            ? entity.entity_subtype
            : '';
        return { entity_type: entity.entity_type, subtypeNorm: stRaw.length > 0 ? stRaw : null };
    }

    _detailTemplateDisplayLabel(entity) {
        const { entity_type: et, subtypeNorm } = this._detailStoragePairForTemplateUi(entity);
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        for (const t of items) {
            const rowSt = t.list_entity_subtype === undefined || t.list_entity_subtype === null || t.list_entity_subtype === ''
                ? null
                : t.list_entity_subtype;
            if (t.list_entity_type === et && rowSt === subtypeNorm) {
                if (typeof t.name === 'string' && t.name.length > 0) return t.name;
                return t.type_id;
            }
        }
        return this._entityTemplateLabel(entity);
    }

    _detailTemplateSelectedTypeId(entity) {
        const { entity_type: et, subtypeNorm } = this._detailStoragePairForTemplateUi(entity);
        const items = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        for (const t of items) {
            const rowSt = t.list_entity_subtype === undefined || t.list_entity_subtype === null || t.list_entity_subtype === ''
                ? null
                : t.list_entity_subtype;
            if (t.list_entity_type === et && rowSt === subtypeNorm) return t.type_id;
        }
        return '';
    }

    _onToggleTemplatePicker() {
        this._templatePickerOpen = !this._templatePickerOpen;
    }

    _onDetailTemplateSelect(ev) {
        const sel = ev.target;
        if (!(sel instanceof HTMLSelectElement)) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: expected select');
        }
        const typeId = sel.value;
        if (typeId.length === 0) return;
        const items = this._entityTypes.items;
        const item = items.find((it) => it.type_id === typeId);
        if (!item) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: type not found');
        }
        const root = this.shadowRoot;
        if (!root) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: shadowRoot missing');
        }
        const card = root.querySelector('crm-entity-card[panel-mode="edit"]');
        if (!card || typeof card.setEditTemplateFromListRow !== 'function') {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: edit card missing');
        }
        card.setEditTemplateFromListRow(item);
    }

    _renderEditTemplateBox(entity, isBusy) {
        const typesLoading = this._entityTypes.loading;
        const rawItems = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const items = [...rawItems].sort((a, b) => {
            const na = typeof a.name === 'string' && a.name.length > 0 ? a.name : a.type_id;
            const nb = typeof b.name === 'string' && b.name.length > 0 ? b.name : b.type_id;
            return na.localeCompare(nb);
        });
        const displayLabel = this._detailTemplateDisplayLabel(entity);
        const selectedTypeId = this._detailTemplateSelectedTypeId(entity);
        return html`
            <div class="detail-template-box detail-template-box--edit">
                <span class="detail-template-label">${this.t('entity_card.object_template_label')}</span>
                ${this._templatePickerOpen
                    ? html`
                        ${typesLoading
                            ? html`<span class="detail-template-value">${this.t('entity_modal.types_loading')}</span>`
                            : html`
                                <select
                                    class="detail-template-select"
                                    .value=${selectedTypeId}
                                    @change=${this._onDetailTemplateSelect}
                                >
                                    <option value="">${this.t('entity_modal.entity_template_pick_placeholder')}</option>
                                    ${items.map((it) => {
                                        const label = typeof it.name === 'string' && it.name.length > 0
                                            ? it.name
                                            : it.type_id;
                                        return html`<option value=${it.type_id}>${label}</option>`;
                                    })}
                                </select>
                            `}
                    `
                    : html`<span class="detail-template-value" title=${displayLabel}>${displayLabel}</span>`}
                <button
                    type="button"
                    class="detail-template-pencil"
                    title=${this.t('entity_detail_page.edit_template')}
                    aria-label=${this.t('entity_detail_page.edit_template')}
                    ?disabled=${isBusy}
                    @click=${this._onToggleTemplatePicker}
                >
                    <platform-icon name="edit" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    _entityTemplateLabel(ent) {
        if (!ent || typeof ent.entity_type !== 'string' || ent.entity_type.length === 0) {
            throw new Error('CRMEntityDetailPage._entityTemplateLabel: entity_type required');
        }
        const st = typeof ent.entity_subtype === 'string' && ent.entity_subtype.length > 0
            ? ent.entity_subtype
            : '';
        return st.length > 0 ? `${ent.entity_type} / ${st}` : ent.entity_type;
    }

    _renderDetailHeaderActions(entity, editingCard, isBusy) {
        return html`
                    ${editingCard
                        ? this._renderEditTemplateBox(entity, isBusy)
                        : html`
                            <button type="button" class="toolbar-pill toolbar-pill-primary" @click=${() => this._onEdit()}>
                                <platform-icon name="edit" size="14"></platform-icon>
                                ${this.t('entity_detail_page.action_edit')}
                            </button>
                        `}
                    <button
                        type="button"
                        class="toolbar-icon-muted"
                        title=${this.t('entity_detail_page.action_share')}
                        aria-label=${this.t('entity_detail_page.action_share')}
                        @click=${() => this._onShare()}
                    >
                        <platform-icon name="share" size="18"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="toolbar-icon-muted"
                        title=${this.t('entity_detail_page.action_access_request')}
                        aria-label=${this.t('entity_detail_page.action_access_request')}
                        @click=${() => this._onAccessRequest()}
                    >
                        <platform-icon name="lock" size="18"></platform-icon>
                    </button>
                    ${editingCard
                        ? html`
                            <button type="button" class="toolbar-pill toolbar-pill-ghost" @click=${() => this._onToolbarCancelEdit()}>
                                ${this.t('entity_modal.action_cancel')}
                            </button>
                            <button
                                type="button"
                                class="toolbar-pill toolbar-pill-primary"
                                ?disabled=${this._editToolbarSaveDisabled}
                                @click=${() => this._onToolbarSave()}
                            >
                                ${this._editToolbarSubmitting
                                    ? this.t('entity_modal.action_saving')
                                    : this.t('entity_modal.action_save')}
                            </button>
                            <button
                                type="button"
                                class="toolbar-icon-danger"
                                title=${this.t('entity_card.delete_object_tooltip')}
                                aria-label=${this.t('entity_card.delete_object_tooltip')}
                                @click=${() => this._onDelete()}
                                ?disabled=${isBusy}
                            >
                                <platform-icon name="trash" size="18"></platform-icon>
                            </button>
                        `
                        : html`
                            <button
                                type="button"
                                class="toolbar-pill toolbar-pill-danger"
                                @click=${() => this._onDelete()}
                                ?disabled=${isBusy}
                            >
                                <platform-icon name="trash" size="14"></platform-icon>
                                ${this.t('entity_detail_page.action_delete')}
                            </button>
                        `}
        `;
    }

    _onToolbarSave() {
        const root = this.shadowRoot;
        if (!root) {
            throw new Error('CRMEntityDetailPage._onToolbarSave: shadowRoot missing');
        }
        const card = root.querySelector('crm-entity-card[panel-mode="edit"]');
        if (!card || typeof card.triggerSave !== 'function') {
            throw new Error('CRMEntityDetailPage._onToolbarSave: edit card not found');
        }
        card.triggerSave();
    }

    _onToolbarCancelEdit() {
        const root = this.shadowRoot;
        if (!root) {
            throw new Error('CRMEntityDetailPage._onToolbarCancelEdit: shadowRoot missing');
        }
        const card = root.querySelector('crm-entity-card[panel-mode="edit"]');
        if (card && typeof card.triggerEditCancel === 'function') {
            card.triggerEditCancel();
            return;
        }
        this._onCardEditCancelled();
    }

    _buildSubtitle(entity) {
        const parts = [];
        if (typeof entity.namespace === 'string' && entity.namespace.length > 0) parts.push(entity.namespace);
        if (typeof entity.entity_type === 'string' && entity.entity_type.length > 0) parts.push(entity.entity_type);
        if (typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) parts.push(entity.entity_subtype);
        return parts.join(' · ');
    }

    _renderActiveTab(entity) {
        if (this._activeTab === TAB_GRAPH) {
            return html`
                <div class="body graph">
                    <crm-mini-graph-preview
                        fill-container
                        entity-id=${this.itemId}
                        .maxDepth=${4}
                        .initialDisplayDepth=${2}
                        @entity-open=${this._onMiniGraphEntityOpen}
                    ></crm-mini-graph-preview>
                </div>
            `;
        }
        const editingCard = this._isEditingCard();
        const mutedFill = this._activeTab !== TAB_GRAPH;
        return html`
            <div class="body ${mutedFill ? 'detail-body-muted' : ''}">
                ${editingCard
                    ? html`
                        <crm-entity-card
                            class=${this._activeTab === TAB_CARD ? '' : 'edit-card-hidden-host'}
                            surface="page"
                            panel-mode="edit"
                            host-toolbar
                            layout-variant="full"
                            entity-id=${this.itemId}
                            .cardBundle=${this._card}
                            .showEntityActions=${false}
                            @entity-saved=${this._onCardSaved}
                            @edit-cancelled=${this._onCardEditCancelled}
                        ></crm-entity-card>
                    `
                    : this._activeTab === TAB_CARD
                        ? html`
                            <crm-entity-card
                                surface="page"
                                panel-mode="view"
                                layout-variant="full"
                                .entity=${entity}
                                entity-id=${this.itemId}
                                .cardBundle=${this._card}
                                .showEntityActions=${false}
                            ></crm-entity-card>
                        `
                        : nothing}
                ${this._activeTab === TAB_RELATIONS ? this._renderRelationsTab(entity) : nothing}
                ${this._activeTab === TAB_ATTACHMENTS ? this._renderAttachmentsTab() : nothing}
            </div>
        `;
    }

    _neighborRowsForDetail() {
        const card = this._card;
        if (card === null || card === undefined || typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return [];
        }
        const edges = extractNeighborEdges(card, this.itemId, { skipTaskNeighbors: true });
        return edges.map(({ rel, otherId, otherEntity, isOutgoing }) => ({
            relationshipId: rel.relationship_id,
            otherId,
            otherEntity,
            relationshipTypeLabel: this._relationshipTypeLabel(rel.relationship_type),
            directionText: isOutgoing
                ? this.t('neighbor_row.outgoing_from_object')
                : this.t('neighbor_row.incoming_to_object'),
            weight: typeof rel.weight === 'number' && Number.isFinite(rel.weight) ? rel.weight : null,
            confidencePercent: relationshipConfidencePercent(rel),
            scorePercent: searchScorePercent(otherEntity),
        }));
    }

    _renderRelationsTab(_entity) {
        const rows = this._neighborRowsForDetail();
        return html`
            <div class="card-section">
                <p class="section-title">${this.t('entity_detail_page.section_neighbors')}</p>
                <crm-related-neighbor-rows
                    .rows=${rows}
                    .emptyText=${this.t('entity_detail_page.empty_neighbors')}
                    .showRemove=${false}
                    .showWeight=${true}
                    @entity-open=${(e) => this._onRelatedClick(e.detail.entityId)}
                ></crm-related-neighbor-rows>
            </div>
        `;
    }

    _renderAttachmentsTab() {
        const attachments = this._card && Array.isArray(this._card.attachments) ? this._card.attachments : [];
        if (attachments.length === 0) {
            return html`
                <div class="card-section">
                    <p class="empty-text">${this.t('entity_detail_page.empty_attachments')}</p>
                </div>
            `;
        }
        return html`
            <div class="card-section">
                <div class="list">
                    ${attachments.map((att) => {
                        const filename = typeof att.filename === 'string' && att.filename.length > 0
                            ? att.filename
                            : (typeof att.document_id === 'string' ? att.document_id : '—');
                        const sizeText = _formatBytes(att.size_bytes);
                        const downloadUrl = typeof att.download_url === 'string' && att.download_url.length > 0
                            ? att.download_url
                            : '';
                        return html`
                            <div class="list-row">
                                <span class="icon">
                                    <platform-icon name="paperclip" size="14"></platform-icon>
                                </span>
                                <span class="meta">
                                    <p class="name">${filename}</p>
                                    <p class="sub">${sizeText}${sizeText ? ' · ' : ''}${typeof att.status === 'string' ? att.status : ''}</p>
                                </span>
                                ${downloadUrl ? html`
                                    <a href=${downloadUrl} target="_blank" rel="noopener noreferrer" download=${filename}>
                                        <platform-icon name="download" size="14"></platform-icon>
                                        ${this.t('entity_detail_page.action_download')}
                                    </a>
                                ` : nothing}
                            </div>
                        `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('crm-entity-detail-page', CRMEntityDetailPage);

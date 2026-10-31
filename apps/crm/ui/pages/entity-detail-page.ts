/**
 * CRMEntityDetailPage — страница карточки одной сущности CRM.
 *
 * Маршрут: `/crm/entities/:itemId` (роутер передаёт `itemId` через `params`).
 * Редактирование: query `?edit=1` на полной странице маршрута `entity`. В режиме `embedded`
 * в панели списка кнопка «Редактировать» ведёт на тот же маршрут с `?edit=1`.
 *
 * Источники данных:
 *   - `useResource('crm/entities')`           — entity по id (GET /entities/{id}).
 *   - `useOp('crm/entity_card')`              — related/relationships/attachments.
 *   - `useResource('crm/relationship_types')` — подписи типов связей.
 *
 * UI: breadcrumbs (`:not([embedded])` скрыты на мобилке) → строка `page-header` (на мобилке контекст
 * `namespace · type` под липкой полосой, в полосе только заголовок; действия — иконки) → вкладки → контент.
 * Карточка: `crm-entity-card`; в режиме `?edit=1` тулбар редактирования
 * в шапке страницы (`host-toolbar` на карточке). Встроенный режим `embedded` на списке сущностей:
 * без breadcrumbs на родителе и внутри; компактный ряд действий (только иконки);
 * карточка с `compact-stack` — вертикальная схема как на узкой ширине; при удалении — `embedded-entity-removed`.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-work-item-badge.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/crm-mini-graph.js';
import { CRMEntityCard } from '../components/entity-card.js';
import '../components/crm-related-neighbor-rows.js';
import { extractNeighborEdges } from '../_helpers/neighbor-edges.js';
import { searchScorePercent, relationshipConfidencePercent } from '../_helpers/search-score-percent.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_CARD_OP = 'crm/entity_card';
const ENTITY_TYPES_NAME = 'crm/entity_types';
const REL_TYPES_NAME = 'crm/relationship_types';

function catalogRows(items: readonly unknown[]): Record<string, unknown>[] {
    const rows: Record<string, unknown>[] = [];
    for (const item of items) {
        if (!isPlainRecord(item)) {
            throw new Error('CRMEntityDetailPage: entity type must be an object');
        }
        rows.push(item);
    }
    return rows;
}

function typeIdOf(row: Record<string, unknown>): string {
    if (typeof row.type_id !== 'string' || row.type_id.length === 0) {
        throw new Error('CRMEntityDetailPage: type_id required');
    }
    return row.type_id;
}

function copyRecord(value: Record<string, unknown>): Record<string, unknown> {
    return { ...value };
}

function eventDetail(ev: Event, label: string): Record<string, unknown> {
    if (!(ev instanceof CustomEvent)) {
        throw new Error(`${label}: CustomEvent required`);
    }
    if (!isPlainRecord(ev.detail)) {
        throw new Error(`${label}: detail object required`);
    }
    return ev.detail;
}

function editCard(root: ParentNode): CRMEntityCard | null {
    const card = root.querySelector('crm-entity-card[panel-mode="edit"]');
    if (card === null) {
        return null;
    }
    if (!(card instanceof CRMEntityCard)) {
        throw new Error('CRMEntityDetailPage: edit card must be crm-entity-card');
    }
    return card;
}

const TAB_CARD = 'card';
const TAB_RELATIONS = 'relations';
const TAB_GRAPH = 'graph';
const ALL_TABS = [TAB_CARD, TAB_RELATIONS, TAB_GRAPH];

function _isEditSearch(searchRaw: unknown): boolean {
    const raw = typeof searchRaw === 'string' ? searchRaw : '';
    const q = raw.startsWith('?') ? raw.slice(1) : raw;
    return new URLSearchParams(q).get('edit') === '1';
}

function _isAccessSearch(searchRaw: unknown): boolean {
    const raw = typeof searchRaw === 'string' ? searchRaw : '';
    const q = raw.startsWith('?') ? raw.slice(1) : raw;
    return new URLSearchParams(q).get('access') === '1';
}

export class CRMEntityDetailPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        embedded: { type: Boolean, reflect: true },
        itemId: { type: String },
        _isMobile: { state: true },
        _card: { state: true },
        _cardError: { state: true },
        _activeTab: { state: true },
        _editToolbarSaveDisabled: { state: true },
        _editToolbarSubmitting: { state: true },
        _templatePickerOpen: { state: true },
        _draftStorageTypePair: { state: true },
    };
    declare embedded: boolean;
    declare itemId: string;
    declare _isMobile: boolean;
    declare _card: Record<string, unknown> | null;
    declare _cardError: string;
    declare _activeTab: string;
    declare _editToolbarSaveDisabled: boolean;
    declare _editToolbarSubmitting: boolean;
    declare _templatePickerOpen: boolean;
    declare _draftStorageTypePair: { entity_type: string; entity_subtype: string };

    static override styles: CSSResultGroup = [
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

            .detail-shell {
                display: flex;
                flex-direction: column;
                flex: 1 1 0%;
                min-height: 0;
                width: 100%;
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
            @media (max-width: 767px) {
                :host(:not([embedded])) .breadcrumbs-wrap {
                    display: none;
                }
                .detail-header-actions {
                    flex-wrap: nowrap;
                }
            }
            .page-subtitle-mobile {
                flex-shrink: 0;
                margin: 0 var(--space-4) var(--space-2);
                padding: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.35;
            }
            .detail-template-inline {
                display: inline-flex;
                flex-direction: row;
                align-items: center;
                gap: var(--space-3);
                box-sizing: border-box;
                min-width: 0;
                max-width: min(480px, 100%);
            }
            .detail-template-select {
                flex: 1;
                min-width: 120px;
                max-width: 260px;
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
                background: var(--crm-surface-tint-strong);
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
                color: var(--text-tertiary);
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
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }
            .toolbar-pill-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
            }
            .toolbar-pill-ghost {
                background: var(--crm-surface-tint-strong);
                color: var(--text-secondary);
            }
            .toolbar-pill-ghost:hover:not(:disabled) {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
            .toolbar-pill-muted {
                background: var(--crm-surface-tint-strong);
                color: var(--text-secondary);
                border: 1px solid transparent;
            }
            .toolbar-pill-muted:hover:not(:disabled) {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
            .toolbar-pill-danger {
                background: transparent;
                color: var(--error);
                border: 1px solid var(--crm-danger-stroke);
            }
            .toolbar-pill-danger:hover:not(:disabled) {
                background: var(--crm-danger-bg);
            }
            .toolbar-icon-danger {
                width: 40px;
                height: 40px;
                padding: 0;
                border: none;
                border-radius: 14px;
                background: var(--crm-danger-bg);
                color: var(--error);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .toolbar-icon-danger:hover:not(:disabled) {
                background: color-mix(in srgb, var(--error) 28%, transparent);
            }
            .toolbar-icon-muted {
                width: 40px;
                height: 40px;
                padding: 0;
                border: none;
                border-radius: 14px;
                background: var(--crm-surface-tint-strong);
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .toolbar-icon-muted:hover:not(:disabled) {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
            .toolbar-icon-muted:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .toolbar-icon-primary {
                width: 40px;
                height: 40px;
                padding: 0;
                border: none;
                border-radius: 14px;
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .toolbar-icon-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
            }
            .toolbar-icon-primary:disabled {
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
                flex: 1 1 0%;
                min-height: 0;
                min-width: 0;
                padding: var(--space-4);
                overflow-y: auto;
                overflow-x: hidden;
                width: 100%;
                box-sizing: border-box;
            }
            .body.detail-body-muted {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                background: var(--crm-surface-tint);
                border-radius: var(--radius-lg);
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
            .body.graph {
                overflow: hidden;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                align-items: stretch;
                flex: 1 1 0%;
                min-height: 0;
                box-sizing: border-box;
            }
            :host([embedded]) .body.graph {
                padding: 0;
            }
            .entity-graph-preview-host {
                flex: 1 1 0%;
                min-height: 0;
                min-width: 0;
                width: 100%;
                display: flex;
                flex-direction: column;
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                overflow: hidden;
                box-sizing: border-box;
            }
            .entity-graph-preview-host crm-mini-graph {
                flex: 1 1 0%;
                min-height: 0;
                width: 100%;
            }

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
                color: var(--error);
                border-color: var(--error);
            }
            .btn-danger:hover:not(:disabled) {
                background: var(--error);
                color: white;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .card-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                width: 100%;
                max-width: 100%;
                min-width: 0;
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
                background: var(--crm-selected-bg);
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

            :host([embedded]) .breadcrumbs-wrap {
                display: none;
            }
            :host([embedded]) .header-wrap {
                padding: var(--space-4) var(--space-3) var(--space-2);
            }
            :host([embedded]) .tabs {
                padding: 0 var(--space-3);
            }
            :host([embedded]) .body {
                padding: var(--space-3);
            }
            @media (max-width: 767px) {
                :host {
                    --platform-mobile-sticky-header-padding-left: max(0px, env(safe-area-inset-left, 0px));
                    --platform-mobile-sticky-header-padding-right: max(0px, env(safe-area-inset-right, 0px));
                }
                .header-wrap {
                    padding-left: 0;
                    padding-right: 0;
                    padding-top: var(--space-3);
                    padding-bottom: var(--space-2);
                }
                :host([embedded]) .header-wrap {
                    padding-left: 0;
                    padding-right: 0;
                    padding-top: var(--space-3);
                    padding-bottom: var(--space-2);
                }
                .tabs {
                    padding-left: 0;
                    padding-right: 0;
                }
                :host([embedded]) .tabs {
                    padding-left: 0;
                    padding-right: 0;
                }
                .body {
                    padding: var(--space-2) 0 var(--space-4);
                }
                :host([embedded]) .body {
                    padding-left: 0;
                    padding-right: 0;
                    padding-top: var(--space-2);
                    padding-bottom: var(--space-4);
                }
                .body.graph {
                    padding-left: 0;
                    padding-right: 0;
                    padding-top: var(--space-2);
                    padding-bottom: var(--space-4);
                }
                .body.detail-body-muted {
                    border-radius: 0;
                }
                .body.detail-body-muted crm-entity-card {
                    flex: 0 1 auto;
                    min-height: 0;
                }
                .page-subtitle-mobile {
                    margin-left: 0;
                    margin-right: 0;
                }
            }
            .embedded-host-filler {
                flex: 1;
                min-height: 0;
            }
        `,
    ];

    private _entities: ResourceController;
    private _entityTypes: ResourceController;
    private _cardOp: OpController;
    private _relTypes: ResourceController;
    private _graphView: ControllerFor<'crm/graph_view'>;
    private _routerSearchSel: SelectController<string | undefined>;
    private _lastRequestedId: string;
    private _entityTypesQueryNs: string;
    private _accessModalOpened: boolean;

    constructor() {
        super();
        this.embedded = false;
        this.itemId = '';
        this._isMobile = typeof window !== 'undefined' && window.innerWidth <= 767;
        this._card = null;
        this._cardError = '';
        this._activeTab = TAB_CARD;
        this._lastRequestedId = '';
        this._editToolbarSaveDisabled = true;
        this._editToolbarSubmitting = false;
        this._templatePickerOpen = false;
        this._draftStorageTypePair = { entity_type: '', entity_subtype: '' };
        this._entityTypesQueryNs = '';

        this._entities = this.useResource(ENTITIES_NAME);
        this._entityTypes = this.useResource(ENTITY_TYPES_NAME, { autoload: false });
        this._cardOp = this.useOp(ENTITY_CARD_OP);
        this._relTypes = this.useResource(REL_TYPES_NAME, { autoload: true });
        this._graphView = this.useSlice('crm/graph_view');
        this._routerSearchSel = this.select((state) => state.router.search);
        this._accessModalOpened = false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            const mql = window.matchMedia('(max-width: 767px)');
            this.useDomEvent(mql, 'change', (e: MediaQueryListEvent) => {
                this._isMobile = e.matches;
            });
            this._isMobile = mql.matches;
        }
        if (this.shadowRoot) {
            this.useDomEvent(this.shadowRoot, 'crm-entity-card-toolbar-state', (e) => this._onCardToolbarState(e));
            this.useDomEvent(this.shadowRoot, 'crm-entity-card-storage-type-draft', (e) => this._onCardStorageTypeDraft(e));
        }

        this.useEvent(this._cardOp.op.events.SUCCEEDED, (event) => {
            if (this._isStaleEntityCardOpEvent(event)) {
                return;
            }
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const result = payload === null ? null : payload.result;
            if (!isPlainRecord(result)) {
                throw new Error('crm/entity_card SUCCEEDED: payload.result missing');
            }
            this._card = copyRecord(result);
            this._cardError = '';
        });
        this.useEvent(this._cardOp.op.events.FAILED, (event) => {
            if (this._isStaleEntityCardOpEvent(event)) {
                return;
            }
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const err = payload !== null && isPlainRecord(payload.error) ? payload.error : null;
            this._card = null;
            this._cardError = err !== null && typeof err.message === 'string' ? err.message : 'load_failed';
        });

        this.useEvent(this._entities.resource.events.REMOVED, (event) => {
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const idField = this._entities.resource.idField;
            const removedId = payload && typeof payload[idField] === 'string' ? payload[idField] : null;
            if (removedId !== this.itemId) return;
            if (this.embedded) {
                this.emit('embedded-entity-removed', { entityId: removedId });
                return;
            }
            this.navigate('entities');
        });
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
    }

    _onCardToolbarState(ev: Event) {
        const d = eventDetail(ev, 'crm-entity-card-toolbar-state');
        if (typeof d.saveDisabled !== 'boolean' || typeof d.submitting !== 'boolean') {
            throw new Error('crm-entity-card-toolbar-state: invalid detail');
        }
        this._editToolbarSaveDisabled = d.saveDisabled;
        this._editToolbarSubmitting = d.submitting;
    }

    _onCardStorageTypeDraft(ev: Event) {
        const d = eventDetail(ev, 'crm-entity-card-storage-type-draft');
        if (typeof d.entity_type !== 'string' || typeof d.entity_subtype !== 'string') {
            throw new Error('crm-entity-card-storage-type-draft: invalid detail');
        }
        this._draftStorageTypePair = { entity_type: d.entity_type, entity_subtype: d.entity_subtype };
    }

    _isStaleEntityCardOpEvent(event: PlatformEvent | null): boolean {
        const meta = event && event.meta;
        const causationId = meta && typeof meta.causation_id === 'string' ? meta.causation_id : null;
        const latestId = this._cardOp.lastRequestId;
        return causationId !== null && latestId !== null && causationId !== latestId;
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (this._activeTab !== TAB_CARD && this._activeTab !== TAB_RELATIONS && this._activeTab !== TAB_GRAPH) {
            this._activeTab = TAB_CARD;
        }
        if (changed.has('itemId')) {
            this._accessModalOpened = false;
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

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        this._maybeOpenAccessModal();
    }

    _maybeOpenAccessModal() {
        if (this.embedded) {
            return;
        }
        if (this._accessModalOpened) {
            return;
        }
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return;
        }
        if (!_isAccessSearch(this._routerSearchSel.value)) {
            return;
        }
        this._accessModalOpened = true;
        this.openModal('crm.share', { entityId: this.itemId });
    }

    _reload() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) return;
        this._entities.get(this.itemId);
        this._cardOp.run({ entity_id: this.itemId });
    }

    _entity(): Record<string, unknown> | null {
        const byId = this._entities.byId;
        const item = byId && byId[this.itemId];
        if (item === undefined) {
            return null;
        }
        if (!isPlainRecord(item)) {
            throw new Error('CRMEntityDetailPage: entity must be an object');
        }
        return copyRecord(item);
    }

    _entityTypesCatalogRows(): Record<string, unknown>[] {
        const ctrl = this._entityTypes;
        if (!ctrl || ctrl.items === undefined || !Array.isArray(ctrl.items)) {
            return [];
        }
        const rows: Record<string, unknown>[] = [];
        for (const item of ctrl.items) {
            if (!isPlainRecord(item)) {
                throw new Error('CRMEntityDetailPage: entity type must be an object');
            }
            rows.push(copyRecord(item));
        }
        return rows;
    }

    _onPickTab(tab: string) {
        if (ALL_TABS.indexOf(tab) === -1) return;
        const prev = this._activeTab;
        this._activeTab = tab;
        if (this.embedded && prev === TAB_GRAPH && tab !== TAB_GRAPH) {
            this.emit('crm-embedded-detail-left-graph-tab');
        }
    }

    _isEditingCard() {
        if (this.embedded) {
            return false;
        }
        return _isEditSearch(this._routerSearchSel.value);
    }

    _onEdit() {
        this._activeTab = TAB_CARD;
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return;
        }
        this.navigate('entity', { itemId: this.itemId }, { search: '?edit=1' });
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

    _navigateToLinkedEntity(entityId: unknown, entityTypeRaw: unknown) {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            return;
        }
        if (entityId === this.itemId) {
            return;
        }
        const et = typeof entityTypeRaw === 'string' ? entityTypeRaw.trim() : '';
        if (et === 'note') {
            this.navigate('note', { itemId: entityId });
            return;
        }
        this.navigate('entity', { itemId: entityId });
    }

    _onMiniGraphEntityOpen(event: CustomEvent) {
        if (!isPlainRecord(event.detail)) {
            throw new Error('CRMEntityDetailPage: mini-graph entity-open detail required');
        }
        const detail = event.detail;
        const entityId = detail && typeof detail.entityId === 'string' ? detail.entityId : '';
        const entityType = detail && typeof detail.entity_type === 'string' ? detail.entity_type : '';
        this._navigateToLinkedEntity(entityId, entityType);
    }

    _onMiniGraphViewModeRequest(event: CustomEvent<{ viewMode?: unknown }>) {
        const d = event.detail && typeof event.detail === 'object' ? event.detail : null;
        const raw = d && typeof d.viewMode === 'string' ? d.viewMode.trim() : '';
        if (raw !== 'mindmap' && raw !== '3d') {
            throw new Error('CRMEntityDetailPage: view-mode-request requires viewMode mindmap|3d');
        }
        this._graphView.setViewMode({ viewMode: raw });
    }

    _onRelatedClick(event: CustomEvent) {
        if (!isPlainRecord(event.detail)) {
            throw new Error('CRMEntityDetailPage: related click detail required');
        }
        const detail = event.detail;
        const entityId = typeof detail.entityId === 'string' ? detail.entityId : '';
        const entityType = typeof detail.entity_type === 'string' ? detail.entity_type : '';
        this._navigateToLinkedEntity(entityId, entityType);
    }

    _relationshipTypeLabel(typeId: unknown): string {
        const items = Array.isArray(this._relTypes.items) ? this._relTypes.items : [];
        const found = items.find((row): row is Record<string, unknown> => isPlainRecord(row) && row.type_id === typeId);
        if (found && typeof found.name === 'string' && found.name.length > 0) return found.name;
        return typeof typeId === 'string' ? typeId : '';
    }

    override render(): TemplateResult {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            if (this.embedded) {
                return html`<div class="embedded-host-filler" aria-hidden="true"></div>`;
            }
            return html`
                <div class="body">
                    <platform-empty-state icon="info" title=${this.t('entity_detail_page.no_id_title')}>
                        <platform-button variant="secondary" @click=${() => this.navigate('entities')}>
                            ${this.t('entity_detail_page.back_to_entities')}
                        </platform-button>
                    </platform-empty-state>
                </div>
            `;
        }

        if (this._cardError) {
            return html`
                <div class="body">
                    <platform-empty-state icon="warning" title=${this.t('entity_detail_page.not_found_title')} hint=${this._cardError}>
                        ${this.embedded
                            ? nothing
                            : html`
                                <platform-button variant="secondary" @click=${() => this.navigate('entities')}>
                                    ${this.t('entity_detail_page.back_to_entities')}
                                </platform-button>
                            `}
                    </platform-empty-state>
                </div>
            `;
        }

        const entity = this._entity();
        if (entity === null || this._entities.loading) {
            return html`
                <div class="body">
                    <platform-empty-state loading></platform-empty-state>
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
        const headerSubtitleForBar =
            this.embedded ? headerSubtitle : this._isMobile ? '' : headerSubtitle;
        return html`
            <div class="detail-shell">
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${entityLabel}></platform-breadcrumbs>
                </div>
                <div class="header-wrap">
                    <page-header
                        dense
                        title=${entityLabel}
                        subtitle=${headerSubtitleForBar}
                        ?hide-mobile-menu=${this.embedded && this._isMobile}
                    >
                        <div slot="actions" class="detail-header-actions">
                            ${entity.entity_type === 'task'
                                && typeof entity.work_item_id === 'string'
                                && entity.work_item_id.length > 0
                                ? html`<platform-work-item-badge
                                    work-item-id=${entity.work_item_id}
                                    variant="chip"
                                    size="sm"
                                    interactive
                                ></platform-work-item-badge>`
                                : nothing}
                            ${this._renderDetailHeaderActions(entity, editingCard, isBusy)}
                        </div>
                    </page-header>
                </div>
                ${this._isMobile && !this.embedded
                    ? html`
                        <p class="page-subtitle-mobile">${headerSubtitle}</p>
                    `
                    : nothing}
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
            </div>
        `;
    }

    _detailStoragePairForTemplateUi(entity: Record<string, unknown> | null): { entity_type: string; subtypeNorm: string | null } {
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

    _detailTemplateDisplayLabel(entity: Record<string, unknown>): string {
        const { entity_type: et, subtypeNorm } = this._detailStoragePairForTemplateUi(entity);
        const items = catalogRows(this._entityTypes.items);
        for (const t of items) {
            const rowSt = t.list_entity_subtype === undefined || t.list_entity_subtype === null || t.list_entity_subtype === ''
                ? null
                : t.list_entity_subtype;
            if (t.list_entity_type === et && rowSt === subtypeNorm) {
                if (typeof t.name === 'string' && t.name.length > 0) return t.name;
                return typeIdOf(t);
            }
        }
        return this._entityTemplateLabel(entity);
    }

    _detailTemplateSelectedTypeId(entity: Record<string, unknown>): string {
        const { entity_type: et, subtypeNorm } = this._detailStoragePairForTemplateUi(entity);
        const items = catalogRows(this._entityTypes.items);
        for (const t of items) {
            const rowSt = t.list_entity_subtype === undefined || t.list_entity_subtype === null || t.list_entity_subtype === ''
                ? null
                : t.list_entity_subtype;
            if (t.list_entity_type === et && rowSt === subtypeNorm) return typeIdOf(t);
        }
        return '';
    }

    _detailTemplateEnumConfig(items: unknown): { values: { value: string; label: string }[] } {
        if (!Array.isArray(items)) {
            throw new Error('CRMEntityDetailPage._detailTemplateEnumConfig: items must be an array');
        }
        const values = [{ value: '', label: this.t('entity_modal.entity_template_pick_placeholder') }];
        for (const it of items) {
            if (!isPlainRecord(it)) {
                throw new Error('CRMEntityDetailPage._detailTemplateEnumConfig: type_id required');
            }
            const typeId = typeIdOf(it);
            const label = typeof it.name === 'string' && it.name.length > 0 ? it.name : typeId;
            values.push({ value: typeId, label });
        }
        return { values };
    }

    _onToggleTemplatePicker() {
        this._templatePickerOpen = !this._templatePickerOpen;
    }

    _onDetailTemplateSelect(ev: Event) {
        const d = eventDetail(ev, 'CRMEntityDetailPage._onDetailTemplateSelect');
        if (typeof d.value !== 'string') {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: expected change detail.value string');
        }
        const typeId = d.value;
        if (typeId.length === 0) return;
        const item = catalogRows(this._entityTypes.items).find((it) => it.type_id === typeId);
        if (item === undefined) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: type not found');
        }
        const root = this.shadowRoot;
        if (!root) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: shadowRoot missing');
        }
        const card = editCard(root);
        if (card === null) {
            throw new Error('CRMEntityDetailPage._onDetailTemplateSelect: edit card missing');
        }
        card.setEditTemplateFromListRow(copyRecord(item));
    }

    _renderEditTemplateBox(entity: Record<string, unknown>, isBusy: boolean): TemplateResult {
        const typesLoading = this._entityTypes.loading;
        const rawItems = Array.isArray(this._entityTypes.items) ? this._entityTypes.items : [];
        const items = catalogRows(rawItems).sort((a, b) => {
            const na = typeof a.name === 'string' && a.name.length > 0 ? a.name : typeIdOf(a);
            const nb = typeof b.name === 'string' && b.name.length > 0 ? b.name : typeIdOf(b);
            return na.localeCompare(nb);
        });
        const displayLabel = this._detailTemplateDisplayLabel(entity);
        const selectedTypeId = this._detailTemplateSelectedTypeId(entity);
        const showInlinePencil = !this._templatePickerOpen || typesLoading;
        return html`
            <div class="detail-template-inline">
                <span class="detail-template-label">${this.t('entity_card.object_template_label')}</span>
                ${this._templatePickerOpen
                    ? html`
                        ${typesLoading
                            ? html`<span class="detail-template-value"><platform-spinner size="xs"></platform-spinner></span>`
                            : html`
                                <platform-field
                                    class="detail-template-select"
                                    pill-density="compact"
                                    type="enum"
                                    mode="edit"
                                    label=""
                                    .value=${selectedTypeId}
                                    .config=${this._detailTemplateEnumConfig(items)}
                                    @change=${this._onDetailTemplateSelect}
                                >
                                    <button
                                        type="button"
                                        class="detail-template-pencil"
                                        slot="suffix"
                                        title=${this.t('entity_detail_page.edit_template')}
                                        aria-label=${this.t('entity_detail_page.edit_template')}
                                        ?disabled=${isBusy}
                                        @click=${this._onToggleTemplatePicker}
                                    >
                                        <platform-icon name="edit" size="16"></platform-icon>
                                    </button>
                                </platform-field>
                            `}
                    `
                    : html`<span class="detail-template-value" title=${displayLabel}>${displayLabel}</span>`}
                ${showInlinePencil
                    ? html`
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
                    `
                    : nothing}
            </div>
        `;
    }

    _entityTemplateLabel(ent: Record<string, unknown> | null): string {
        if (!ent || typeof ent.entity_type !== 'string' || ent.entity_type.length === 0) {
            throw new Error('CRMEntityDetailPage._entityTemplateLabel: entity_type required');
        }
        const st = typeof ent.entity_subtype === 'string' && ent.entity_subtype.length > 0
            ? ent.entity_subtype
            : '';
        return st.length > 0 ? `${ent.entity_type} / ${st}` : ent.entity_type;
    }

    _renderDetailHeaderActions(entity: Record<string, unknown>, editingCard: boolean, isBusy: boolean): TemplateResult {
        const compactToolbar = this.embedded || this._isMobile;
        if (compactToolbar && !editingCard) {
            return html`
                    <button
                        type="button"
                        class="toolbar-icon-primary"
                        title=${this.t('entity_detail_page.action_edit')}
                        aria-label=${this.t('entity_detail_page.action_edit')}
                        @click=${() => this._onEdit()}
                    >
                        <platform-icon name="edit" size="18"></platform-icon>
                    </button>
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
                    <button
                        type="button"
                        class="toolbar-icon-danger"
                        title=${this.t('entity_detail_page.action_delete')}
                        aria-label=${this.t('entity_detail_page.action_delete')}
                        @click=${() => this._onDelete()}
                        ?disabled=${isBusy}
                    >
                        <platform-icon name="trash" size="18"></platform-icon>
                    </button>
            `;
        }
        if (compactToolbar && editingCard) {
            return html`
                    ${this._isMobile ? nothing : this._renderEditTemplateBox(entity, isBusy)}
                    <button
                        type="button"
                        class="toolbar-icon-muted"
                        title=${this.t('entity_modal.action_cancel')}
                        aria-label=${this.t('entity_modal.action_cancel')}
                        @click=${() => this._onToolbarCancelEdit()}
                    >
                        <platform-icon name="close" size="18"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="toolbar-icon-primary"
                        title=${this._editToolbarSubmitting
                            ? this.t('entity_modal.action_saving')
                            : this.t('entity_modal.action_save')}
                        aria-label=${this._editToolbarSubmitting
                            ? this.t('entity_modal.action_saving')
                            : this.t('entity_modal.action_save')}
                        ?disabled=${this._editToolbarSaveDisabled || this._editToolbarSubmitting}
                        @click=${() => this._onToolbarSave()}
                    >
                        ${this._editToolbarSubmitting
                            ? html`<platform-spinner size="xs"></platform-spinner>`
                            : html`<platform-icon name="check" size="18"></platform-icon>`}
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
            `;
        }
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
        const card = editCard(root);
        if (card === null) {
            throw new Error('CRMEntityDetailPage._onToolbarSave: edit card not found');
        }
        card.triggerSave();
    }

    _onToolbarCancelEdit() {
        const root = this.shadowRoot;
        if (!root) {
            throw new Error('CRMEntityDetailPage._onToolbarCancelEdit: shadowRoot missing');
        }
        const card = editCard(root);
        if (card !== null) {
            card.triggerEditCancel();
            return;
        }
        this._onCardEditCancelled();
    }

    _buildSubtitle(entity: Record<string, unknown>): string {
        const parts: string[] = [];
        if (typeof entity.namespace === 'string' && entity.namespace.length > 0) parts.push(entity.namespace);
        if (typeof entity.entity_type === 'string' && entity.entity_type.length > 0) parts.push(entity.entity_type);
        if (typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) parts.push(entity.entity_subtype);
        return parts.join(' · ');
    }

    _renderActiveTab(entity: Record<string, unknown>): TemplateResult {
        if (this._activeTab === TAB_GRAPH) {
            const entityNs =
                entity && typeof entity.namespace === 'string' && entity.namespace.length > 0
                    ? entity.namespace
                    : '';
            const vm = this._graphView.value?.viewMode;
            return html`
                <div class="body graph">
                    <div class="entity-graph-preview-host">
                        <crm-mini-graph
                            fill-container
                            embed-chrome
                            show-view-mode-toggle
                            .entityId=${this.itemId}
                            namespace=${entityNs}
                            .viewMode=${vm}
                            @view-mode-request=${this._onMiniGraphViewModeRequest}
                            @entity-open=${this._onMiniGraphEntityOpen}
                        ></crm-mini-graph>
                    </div>
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
                            ?compact-stack=${this.embedded}
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
                                ?compact-stack=${this.embedded}
                                .entity=${entity}
                                entity-id=${this.itemId}
                                .cardBundle=${this._card}
                                .showEntityActions=${false}
                            ></crm-entity-card>
                        `
                        : nothing}
                ${this._activeTab === TAB_RELATIONS ? this._renderRelationsTab(entity) : nothing}
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

    _renderRelationsTab(_entity: Record<string, unknown>): TemplateResult {
        const rows = this._neighborRowsForDetail();
        return html`
            <div class="card-section">
                <p class="section-title">${this.t('entity_detail_page.section_neighbors')}</p>
                <crm-related-neighbor-rows
                    .rows=${rows}
                    .entityTypeRows=${this._entityTypesCatalogRows()}
                    .emptyText=${this.t('entity_detail_page.empty_neighbors')}
                    .showRemove=${false}
                    @entity-open=${this._onRelatedClick}
                ></crm-related-neighbor-rows>
            </div>
        `;
    }
}

customElements.define('crm-entity-detail-page', CRMEntityDetailPage);

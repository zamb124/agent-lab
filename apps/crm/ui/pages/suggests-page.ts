/**
 * CRMSuggestsPage — очередь фоновых AI-предложений выбранного namespace.
 *
 * Источники:
 *   - useOp('crm/suggests_list') — GET /namespaces/{namespace}/suggests.
 *   - useOp('crm/suggest_resolve') / useOp('crm/suggest_dismiss') — действия.
 *   - useResource('crm/entities') — lazy-названия целевых сущностей.
 */

import { html, css, nothing } from 'lit';
import { CRMNamespacePage } from './crm-namespace-page.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    TemplateResult,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';

const PAGE_LIMIT = 100;

const STATUS_FILTERS = Object.freeze([
    Object.freeze({ status: 'pending', labelKey: 'suggests_page.filter_pending' }),
    Object.freeze({ status: '', labelKey: 'suggests_page.filter_all' }),
    Object.freeze({ status: 'resolved', labelKey: 'suggests_page.filter_resolved' }),
    Object.freeze({ status: 'dismissed', labelKey: 'suggests_page.filter_dismissed' }),
    Object.freeze({ status: 'auto_resolved', labelKey: 'suggests_page.filter_auto_resolved' }),
]);

function isKnownStatus(status: unknown): boolean {
    for (const item of STATUS_FILTERS) {
        if (item.status === status) {
            return true;
        }
    }
    return false;
}

function requireSuggestId(suggest: { suggest_id?: unknown } | null | undefined, owner: string): string {
    if (!suggest || typeof suggest.suggest_id !== 'string' || suggest.suggest_id.length === 0) {
        throw new Error(`${owner}: suggest.suggest_id required`);
    }
    return suggest.suggest_id;
}

function requireSuggestPayload(suggest: { payload?: unknown } | null | undefined, owner: string): Record<string, unknown> {
    if (!suggest || !isPlainRecord(suggest.payload)) {
        throw new Error(`${owner}: suggest.payload object required`);
    }
    return suggest.payload;
}

function requireTargetEntityIds(suggest: unknown, owner: string): string[] {
    if (!isPlainRecord(suggest) || !Array.isArray(suggest.target_entity_ids)) {
        throw new Error(`${owner}: suggest.target_entity_ids required`);
    }
    const ids: string[] = [];
    for (const id of suggest.target_entity_ids) {
        if (typeof id !== 'string' || id.length === 0) {
            throw new Error(`${owner}: target entity id must be non-empty string`);
        }
        ids.push(id);
    }
    return ids;
}

export class CRMSuggestsPage extends CRMNamespacePage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        _status: { state: true },
    };
    declare _status: unknown;

    static override styles: CSSResultGroup = [
        CRMNamespacePage.styles,
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
                padding: var(--space-2) var(--space-2) 0;
            }

            .page-subtitle-mobile {
                display: none;
            }

            .content {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                flex-wrap: wrap;
            }

            .filters {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .filter-chip,
            .action-btn,
            .reload-btn,
            .target-chip {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font: inherit;
                cursor: pointer;
                transition:
                    background var(--duration-fast),
                    border-color var(--duration-fast),
                    color var(--duration-fast);
            }

            .filter-chip {
                min-height: 34px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                font-size: var(--text-sm);
                font-weight: 500;
            }

            .filter-chip:hover,
            .reload-btn:hover:not(:disabled),
            .target-chip:hover,
            .action-btn:hover:not(:disabled) {
                background: var(--crm-surface);
                color: var(--text-primary);
                border-color: var(--crm-selected-stroke);
            }

            .filter-chip.active {
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                border-color: var(--crm-selected-stroke);
            }

            .reload-btn {
                min-height: 34px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }

            .reload-btn:disabled,
            .action-btn:disabled {
                opacity: 0.55;
                cursor: not-allowed;
            }

            .namespace-line {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }

            .list {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
                gap: var(--space-3);
            }

            .suggest-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface);
                padding: var(--space-4);
            }

            .suggest-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
            }

            .suggest-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .suggest-icon {
                width: 34px;
                height: 34px;
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .suggest-title-text {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }

            .suggest-title-text strong {
                color: var(--text-primary);
                font-size: var(--text-base);
                line-height: 1.25;
            }

            .suggest-id {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 280px;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                padding: 3px var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                white-space: nowrap;
            }

            .status-pill.pending {
                border-color: var(--warning-border);
                background: var(--warning-bg);
                color: var(--warning);
            }

            .status-pill.resolved,
            .status-pill.auto_resolved {
                border-color: var(--success-border);
                background: var(--success-bg);
                color: var(--success);
            }

            .status-pill.dismissed {
                color: var(--text-tertiary);
            }

            .suggest-summary {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.45;
            }

            .details {
                display: grid;
                gap: var(--space-2);
            }

            .detail-row {
                display: grid;
                grid-template-columns: minmax(120px, 0.34fr) minmax(0, 1fr);
                gap: var(--space-2);
                align-items: center;
            }

            .detail-label {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .targets {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-2);
                min-width: 0;
            }

            .target-chip {
                min-width: 0;
                max-width: 100%;
                min-height: 30px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
            }

            .target-chip span {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .value-text {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .actions {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
                margin-top: auto;
            }

            .action-btn {
                min-height: 34px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
            }

            .action-btn.resolve {
                background: var(--success-bg);
                border-color: var(--success-border);
                color: var(--success);
            }

            .action-btn.dismiss {
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }

            .center {
                flex: 1;
                min-height: 280px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
            }

            .center-inner {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                max-width: 520px;
            }

            .center-inner p {
                margin: 0;
                color: var(--text-secondary);
                line-height: 1.45;
            }

            .error-text {
                color: var(--error);
            }

            @media (max-width: 767px) {
                :host {
                    padding: 0;
                    box-sizing: border-box;
                }

                .breadcrumbs-wrap,
                .content {
                    padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
                    padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                }

                .page-subtitle-mobile {
                    display: block;
                    flex-shrink: 0;
                    margin: 0 max(var(--space-2), env(safe-area-inset-right, 0px)) var(--space-2) max(var(--space-2), env(safe-area-inset-left, 0px));
                    font-size: var(--text-sm);
                    color: var(--text-secondary);
                    line-height: 1.4;
                }

                .toolbar {
                    align-items: stretch;
                }

                .filters,
                .reload-btn {
                    width: 100%;
                }

                .filter-chip {
                    flex: 1 1 auto;
                }

                .suggest-card {
                    padding: var(--space-3);
                }

                .suggest-head {
                    flex-direction: column;
                    align-items: stretch;
                }

                .detail-row {
                    grid-template-columns: 1fr;
                    align-items: start;
                }
            }
        `,
    ];

    private _suggestsList: OpController;
    private _resolveOp: OpController;
    private _dismissOp: OpController;
    private _entities: ResourceController;

    constructor() {
        super();
        this._status = 'pending';
        this._suggestsList = this.useOp('crm/suggests_list');
        this._resolveOp = this.useOp('crm/suggest_resolve');
        this._dismissOp = this.useOp('crm/suggest_dismiss');
        this._entities = this.useResource('crm/entities');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => this._loadSuggests());
        this.useEvent(this._suggestsList.op.events.SUCCEEDED, (event) => {
            if (!isPlainRecord(event.payload)) {
                throw new Error('CRMSuggestsPage: suggest list result required');
            }
            this._prefetchTargetsFromPage(event.payload.result);
        });
        this.useEvent(this._resolveOp.op.events.SUCCEEDED, () => {
            this.requestUpdate();
        });
        this.useEvent(this._dismissOp.op.events.SUCCEEDED, () => {
            this.requestUpdate();
        });
        this._loadSuggests();
    }

    _currentNamespace() {
        return this._crmNamespaceSel.value;
    }

    _loadSuggests() {
        const namespace = this._currentNamespace();
        if (typeof namespace !== 'string' || namespace.length === 0) {
            return;
        }
        this._suggestsList.run({
            namespace,
            status: this._status,
            limit: PAGE_LIMIT,
            offset: 0,
        });
    }

    _setStatus(status: unknown) {
        if (typeof status !== 'string' || !isKnownStatus(status)) {
            throw new Error('CRMSuggestsPage._setStatus: unsupported status');
        }
        if (this._status === status) {
            return;
        }
        this._status = status;
        this._loadSuggests();
    }

    _pageItems() {
        const page = this._suggestsList.lastResult;
        if (page === null) {
            return [];
        }
        if (!isPlainRecord(page) || !Array.isArray(page.items)) {
            throw new Error('CRMSuggestsPage: suggests page items required');
        }
        return page.items;
    }

    _prefetchTargetsFromPage(page: unknown) {
        if (!isPlainRecord(page) || !Array.isArray(page.items)) {
            throw new Error('CRMSuggestsPage._prefetchTargetsFromPage: page.items required');
        }
        const ids = new Set<string>();
        for (const suggest of page.items) {
            for (const id of requireTargetEntityIds(suggest, 'CRMSuggestsPage._prefetchTargetsFromPage')) {
                ids.add(id);
            }
        }
        for (const id of ids) {
            if (!Object.prototype.hasOwnProperty.call(this._entities.byId, id)) {
                this._entities.get(id);
            }
        }
    }

    _entityTitle(entityId: unknown): string {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            throw new Error('CRMSuggestsPage._entityTitle: entityId required');
        }
        const entity = this._entities.byId[entityId];
        if (isPlainRecord(entity)) {
            const name = entity.name;
            if (typeof name === 'string' && name.length > 0) {
                return name;
            }
        }
        return entityId;
    }

    _statusLabel(status: string): string {
        switch (status) {
            case 'pending':
                return this.t('suggests_page.status_pending');
            case 'resolved':
                return this.t('suggests_page.status_resolved');
            case 'dismissed':
                return this.t('suggests_page.status_dismissed');
            case 'auto_resolved':
                return this.t('suggests_page.status_auto_resolved');
            default:
                throw new Error(`CRMSuggestsPage._statusLabel: unsupported status "${status}"`);
        }
    }

    _emptyMessage() {
        switch (this._status) {
            case 'pending':
                return this.t('suggests_page.empty_pending');
            case '':
                return this.t('suggests_page.empty_all');
            case 'resolved':
                return this.t('suggests_page.empty_resolved');
            case 'dismissed':
                return this.t('suggests_page.empty_dismissed');
            case 'auto_resolved':
                return this.t('suggests_page.empty_auto_resolved');
            default:
                throw new Error(`CRMSuggestsPage._emptyMessage: unsupported status "${this._status}"`);
        }
    }

    _suggestTypeLabel(suggest: Record<string, unknown>) {
        switch (suggest.suggest_type) {
            case 'duplicate':
                return this.t('suggests_page.type_duplicate');
            case 'missed_entity':
                return this.t('suggests_page.type_missed_entity');
            default:
                throw new Error(`CRMSuggestsPage._suggestTypeLabel: unsupported type "${suggest.suggest_type}"`);
        }
    }

    _suggestIcon(suggest: Record<string, unknown>) {
        switch (suggest.suggest_type) {
            case 'duplicate':
                return 'swap-horiz';
            case 'missed_entity':
                return 'sparkle';
            default:
                throw new Error(`CRMSuggestsPage._suggestIcon: unsupported type "${suggest.suggest_type}"`);
        }
    }

    _resolveConfirm(suggest: Record<string, unknown>) {
        switch (suggest.suggest_type) {
            case 'duplicate':
                return {
                    title: this.t('suggests_page.confirm_duplicate_title'),
                    message: this.t('suggests_page.confirm_duplicate_message'),
                    variant: 'danger',
                };
            case 'missed_entity':
                return {
                    title: this.t('suggests_page.confirm_missed_title'),
                    message: this.t('suggests_page.confirm_missed_message'),
                    variant: 'warning',
                };
            default:
                throw new Error(`CRMSuggestsPage._resolveConfirm: unsupported type "${suggest.suggest_type}"`);
        }
    }

    async _onResolve(suggest: Record<string, unknown>) {
        const namespace = this._currentNamespace();
        if (typeof namespace !== 'string' || namespace.length === 0) {
            throw new Error('CRMSuggestsPage._onResolve: namespace required');
        }
        const confirmConfig = this._resolveConfirm(suggest);
        const confirmed = await platformConfirm(confirmConfig.message, {
            title: confirmConfig.title,
            variant: confirmConfig.variant,
            confirmText: this.t('suggests_page.action_resolve'),
            cancelText: this.t('suggests_page.action_cancel'),
        });
        if (!confirmed) {
            return;
        }
        this._resolveOp.run({ namespace, suggest_id: requireSuggestId(suggest, 'CRMSuggestsPage._onResolve') });
    }

    _onDismiss(suggest: Record<string, unknown>) {
        const namespace = this._currentNamespace();
        if (typeof namespace !== 'string' || namespace.length === 0) {
            throw new Error('CRMSuggestsPage._onDismiss: namespace required');
        }
        this._dismissOp.run({ namespace, suggest_id: requireSuggestId(suggest, 'CRMSuggestsPage._onDismiss') });
    }

    _openEntity(entityId: unknown) {
        if (typeof entityId !== 'string' || entityId.length === 0) {
            throw new Error('CRMSuggestsPage._openEntity: entityId required');
        }
        this.navigate('entity', { itemId: entityId });
    }

    _renderTargetChip(entityId: string): TemplateResult {
        return html`
            <button
                type="button"
                class="target-chip"
                title=${entityId}
                @click=${() => this._openEntity(entityId)}
            >
                <platform-icon name="box" size="12"></platform-icon>
                <span>${this._entityTitle(entityId)}</span>
            </button>
        `;
    }

    _renderDuplicateDetails(suggest: Record<string, unknown>) {
        const payload = requireSuggestPayload(suggest, 'CRMSuggestsPage._renderDuplicateDetails');
        if (typeof payload.survivor_entity_id !== 'string' || payload.survivor_entity_id.length === 0) {
            throw new Error('CRMSuggestsPage._renderDuplicateDetails: payload.survivor_entity_id required');
        }
        if (typeof payload.source_entity_id !== 'string' || payload.source_entity_id.length === 0) {
            throw new Error('CRMSuggestsPage._renderDuplicateDetails: payload.source_entity_id required');
        }
        return html`
            <p class="suggest-summary">${this.t('suggests_page.duplicate_summary')}</p>
            <div class="details">
                <div class="detail-row">
                    <div class="detail-label">${this.t('suggests_page.duplicate_survivor')}</div>
                    <div class="targets">${this._renderTargetChip(payload.survivor_entity_id)}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">${this.t('suggests_page.duplicate_source')}</div>
                    <div class="targets">${this._renderTargetChip(payload.source_entity_id)}</div>
                </div>
            </div>
        `;
    }

    _renderMissedEntityDetails(suggest: Record<string, unknown>) {
        const payload = requireSuggestPayload(suggest, 'CRMSuggestsPage._renderMissedEntityDetails');
        if (typeof payload.note_id !== 'string' || payload.note_id.length === 0) {
            throw new Error('CRMSuggestsPage._renderMissedEntityDetails: payload.note_id required');
        }
        if (typeof payload.draft_version !== 'number') {
            throw new Error('CRMSuggestsPage._renderMissedEntityDetails: payload.draft_version required');
        }
        return html`
            <p class="suggest-summary">${this.t('suggests_page.missed_summary')}</p>
            <div class="details">
                <div class="detail-row">
                    <div class="detail-label">${this.t('suggests_page.missed_note')}</div>
                    <div class="targets">${this._renderTargetChip(payload.note_id)}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">${this.t('suggests_page.draft_version')}</div>
                    <div class="value-text">${payload.draft_version}</div>
                </div>
            </div>
        `;
    }

    _renderSuggestDetails(suggest: Record<string, unknown>) {
        switch (suggest.suggest_type) {
            case 'duplicate':
                return this._renderDuplicateDetails(suggest);
            case 'missed_entity':
                return this._renderMissedEntityDetails(suggest);
            default:
                throw new Error(`CRMSuggestsPage._renderSuggestDetails: unsupported type "${suggest.suggest_type}"`);
        }
    }

    _renderSuggestActions(suggest: Record<string, unknown>) {
        if (suggest.status !== 'pending') {
            return nothing;
        }
        const busy = this._resolveOp.busy || this._dismissOp.busy;
        return html`
            <div class="actions">
                <button
                    type="button"
                    class="action-btn dismiss"
                    ?disabled=${busy}
                    @click=${() => this._onDismiss(suggest)}
                >
                    <platform-icon name="close" size="13"></platform-icon>
                    ${this.t('suggests_page.action_dismiss')}
                </button>
                <button
                    type="button"
                    class="action-btn resolve"
                    ?disabled=${busy}
                    @click=${() => this._onResolve(suggest)}
                >
                    <platform-icon name="check" size="13"></platform-icon>
                    ${this.t('suggests_page.action_resolve')}
                </button>
            </div>
        `;
    }

    _renderSuggest(suggest: Record<string, unknown>): TemplateResult {
        const status = suggest.status;
        if (typeof status !== 'string' || status.length === 0) {
            throw new Error('CRMSuggestsPage._renderSuggest: suggest.status required');
        }
        if (!isKnownStatus(status)) {
            throw new Error(`CRMSuggestsPage._renderSuggest: unsupported status "${status}"`);
        }
        return html`
            <article class="suggest-card">
                <div class="suggest-head">
                    <div class="suggest-title">
                        <span class="suggest-icon">
                            <platform-icon name=${this._suggestIcon(suggest)} size="18"></platform-icon>
                        </span>
                        <div class="suggest-title-text">
                            <strong>${this._suggestTypeLabel(suggest)}</strong>
                            <span class="suggest-id">${requireSuggestId(suggest, 'CRMSuggestsPage._renderSuggest')}</span>
                        </div>
                    </div>
                    <span class="status-pill ${status}">${this._statusLabel(status)}</span>
                </div>
                ${this._renderSuggestDetails(suggest)}
                ${this._renderSuggestActions(suggest)}
            </article>
        `;
    }

    _renderNamespaceRequired() {
        return html`
            <div class="center">
                <div class="center-inner">
                    <platform-icon name="target" size="46"></platform-icon>
                    <p>${this.t('suggests_page.namespace_required')}</p>
                </div>
            </div>
        `;
    }

    _renderError() {
        return html`
            <div class="center">
                <div class="center-inner">
                    <platform-icon name="alert-triangle" size="46"></platform-icon>
                    <p class="error-text">${this.t('suggests_page.load_failed')}</p>
                    <button type="button" class="reload-btn" @click=${() => this._loadSuggests()}>
                        <platform-icon name="refresh" size="14"></platform-icon>
                        ${this.t('suggests_page.refresh')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderEmpty() {
        return html`
            <div class="center">
                <div class="center-inner">
                    <platform-icon name="sparkle" size="46"></platform-icon>
                    <p>${this._emptyMessage()}</p>
                </div>
            </div>
        `;
    }

    override render(): TemplateResult {
        const namespace = this._currentNamespace();
        const loading = this._suggestsList.busy;
        const error = this._suggestsList.error;
        const items = this._pageItems();

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('suggests_page.title')}
                subtitle=${this.t('suggests_page.subtitle')}
            ></page-header>
            <p class="page-subtitle-mobile">${this.t('suggests_page.subtitle')}</p>
            <div class="content">
                <div class="toolbar">
                    <div class="filters">
                        ${STATUS_FILTERS.map((filter) => html`
                            <button
                                type="button"
                                class="filter-chip ${this._status === filter.status ? 'active' : ''}"
                                @click=${() => this._setStatus(filter.status)}
                            >
                                ${this.t(filter.labelKey)}
                            </button>
                        `)}
                    </div>
                    <button
                        type="button"
                        class="reload-btn"
                        ?disabled=${loading || typeof namespace !== 'string'}
                        @click=${() => this._loadSuggests()}
                    >
                        <platform-icon name="refresh" size="14"></platform-icon>
                        ${loading
                            ? html`<glass-spinner size="xs"></glass-spinner>`
                            : this.t('suggests_page.refresh')}
                    </button>
                </div>

                ${typeof namespace === 'string'
                    ? html`<div class="namespace-line">
                        <platform-icon name="folder" size="12"></platform-icon>
                        ${this.t('suggests_page.namespace_label', { namespace })}
                    </div>`
                    : nothing}

                ${typeof namespace !== 'string'
                    ? this._renderNamespaceRequired()
                    : error !== null
                        ? this._renderError()
                        : loading && items.length === 0
                            ? html`<div class="center"><glass-spinner size="lg"></glass-spinner></div>`
                            : items.length === 0
                                ? this._renderEmpty()
                                : html`<div class="list">${items.map((suggest) => this._renderSuggest(suggest))}</div>`}
            </div>
        `;
    }
}

customElements.define('crm-suggests-page', CRMSuggestsPage);

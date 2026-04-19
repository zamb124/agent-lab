/**
 * CRMEntityDetailPage — страница карточки одной сущности CRM.
 *
 * Маршрут: `/crm/entities/:itemId` (роутер передаёт `itemId` через `params`).
 *
 * Источники данных:
 *   - `useResource('crm/entities')`           — entity по id (GET /entities/{id}).
 *   - `useOp('crm/entity_card')`              — related/relationships/attachments.
 *   - `useResource('crm/relationship_types')` — подписи типов связей.
 *
 * UI: breadcrumbs → page-header (имя + entity_type/subtype) → панель действий
 * (edit / share / access_request / delete) → tabs «Карточка» / «Связи» /
 * «Граф» / «Вложения».
 *
 * Обработчики:
 *   - edit       → openModal('crm.entity', { mode: 'edit', id })
 *   - share      → openModal('crm.share', { entityId })
 *   - access     → openModal('crm.access_request', { entityId })
 *   - delete     → openModal('crm.entity_delete', { entityId, redirectRoute: 'entities' })
 *   - entity-open от mini-graph-preview → navigate('entity', { itemId })
 *
 * Подписки:
 *   - `entitiesResource.events.REMOVED` для текущего id → navigate('entities').
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '../components/mini-graph-preview.js';

const ENTITIES_NAME = 'crm/entities';
const ENTITY_CARD_OP = 'crm/entity_card';
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

export class CRMEntityDetailPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        itemId: { type: String },
        _card: { state: true },
        _cardError: { state: true },
        _activeTab: { state: true },
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

            .actions-bar {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                padding: 0 var(--space-4) var(--space-3);
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
                max-width: 800px;
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

        this._entities = this.useResource(ENTITIES_NAME);
        this._cardOp = this.useOp(ENTITY_CARD_OP);
        this._relTypes = this.useResource(REL_TYPES_NAME, { autoload: true });
    }

    connectedCallback() {
        super.connectedCallback();

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

    willUpdate(changed) {
        if (!changed.has('itemId')) return;
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            this._card = null;
            this._cardError = '';
            this._lastRequestedId = '';
            return;
        }
        if (this._lastRequestedId === this.itemId) return;
        this._lastRequestedId = this.itemId;
        this._activeTab = TAB_CARD;
        this._reload();
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

    _onEdit() {
        this.openModal('crm.entity', { mode: 'edit', id: this.itemId });
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

        const subtitle = this._buildSubtitle(entity);
        const isBusy = this._entities.isBusy(this.itemId);

        const entityLabel = typeof entity.name === 'string' && entity.name.length > 0
            ? entity.name
            : this.itemId;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${entityLabel}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${entityLabel}
                    subtitle=${subtitle}
                ></page-header>
            </div>
            <div class="actions-bar">
                <button class="btn btn-primary" type="button" @click=${() => this._onEdit()}>
                    <platform-icon name="edit" size="14"></platform-icon>
                    ${this.t('entity_detail_page.action_edit')}
                </button>
                <button class="btn" type="button" @click=${() => this._onShare()}>
                    <platform-icon name="share" size="14"></platform-icon>
                    ${this.t('entity_detail_page.action_share')}
                </button>
                <button class="btn" type="button" @click=${() => this._onAccessRequest()}>
                    <platform-icon name="lock" size="14"></platform-icon>
                    ${this.t('entity_detail_page.action_access_request')}
                </button>
                <button class="btn btn-danger" type="button" @click=${() => this._onDelete()} ?disabled=${isBusy}>
                    <platform-icon name="trash" size="14"></platform-icon>
                    ${this.t('entity_detail_page.action_delete')}
                </button>
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
        return html`
            <div class="body">
                ${this._activeTab === TAB_CARD ? this._renderCardTab(entity) : nothing}
                ${this._activeTab === TAB_RELATIONS ? this._renderRelationsTab(entity) : nothing}
                ${this._activeTab === TAB_ATTACHMENTS ? this._renderAttachmentsTab() : nothing}
            </div>
        `;
    }

    _renderCardTab(entity) {
        const description = typeof entity.description === 'string' ? entity.description : '';
        const tags = Array.isArray(entity.tags) ? entity.tags : [];
        const attrs = entity.attributes && typeof entity.attributes === 'object' && !Array.isArray(entity.attributes)
            ? Object.entries(entity.attributes).filter(([, v]) => v !== null && v !== undefined && v !== '')
            : [];

        return html`
            <div class="card-section">
                ${description.length > 0
                    ? html`<p class="description">${description}</p>`
                    : html`<p class="empty-text">${this.t('entity_detail_page.empty_description')}</p>`}
                ${tags.length > 0 ? html`
                    <div>
                        <p class="section-title">${this.t('entity_detail_page.section_tags')}</p>
                        <div class="tags">
                            ${tags.map((tag) => html`<span class="tag">${tag}</span>`)}
                        </div>
                    </div>
                ` : nothing}
                ${attrs.length > 0 ? html`
                    <div>
                        <p class="section-title">${this.t('entity_detail_page.section_attributes')}</p>
                        <div class="attrs">
                            ${attrs.map(([k, v]) => html`
                                <div class="attr-key">${k}</div>
                                <div class="attr-val">${typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}</div>
                            `)}
                        </div>
                    </div>
                ` : nothing}
            </div>
        `;
    }

    _renderRelationsTab(entity) {
        const card = this._card;
        const related = card && Array.isArray(card.related_entities)
            ? card.related_entities.filter((e) => e && e.entity_id !== this.itemId)
            : [];
        const relationships = card && Array.isArray(card.relationships) ? card.relationships : [];

        return html`
            <div class="card-section">
                <div>
                    <p class="section-title">${this.t('entity_detail_page.section_related')}</p>
                    ${related.length === 0
                        ? html`<p class="empty-text">${this.t('entity_detail_page.empty_related')}</p>`
                        : html`
                            <div class="list">
                                ${related.map((it) => html`
                                    <button
                                        type="button"
                                        class="list-row clickable"
                                        @click=${() => this._onRelatedClick(it.entity_id)}
                                    >
                                        <span class="icon">
                                            <platform-icon name="link" size="14"></platform-icon>
                                        </span>
                                        <span class="meta">
                                            <p class="name">${it.name && it.name.length > 0 ? it.name : it.entity_id}</p>
                                            <p class="sub">${typeof it.entity_type === 'string' ? it.entity_type : ''}</p>
                                        </span>
                                        <span class="arrow">
                                            <platform-icon name="chevron-right" size="14"></platform-icon>
                                        </span>
                                    </button>
                                `)}
                            </div>
                        `}
                </div>
                <div>
                    <p class="section-title">${this.t('entity_detail_page.section_relationships')}</p>
                    ${relationships.length === 0
                        ? html`<p class="empty-text">${this.t('entity_detail_page.empty_relationships')}</p>`
                        : html`
                            <div class="list">
                                ${relationships.map((rel) => this._renderRelationshipRow(entity, rel))}
                            </div>
                        `}
                </div>
            </div>
        `;
    }

    _renderRelationshipRow(entity, rel) {
        const isOutgoing = rel.source_entity_id === this.itemId;
        const otherId = isOutgoing ? rel.target_entity_id : rel.source_entity_id;
        const card = this._card;
        const otherEntity = card && Array.isArray(card.related_entities)
            ? card.related_entities.find((e) => e.entity_id === otherId)
            : null;
        const otherName = otherEntity !== null && otherEntity !== undefined && typeof otherEntity.name === 'string'
            ? otherEntity.name
            : otherId;
        const arrow = isOutgoing ? '→' : '←';
        return html`
            <button type="button" class="list-row clickable" @click=${() => this._onRelatedClick(otherId)}>
                <span class="icon">
                    <platform-icon name="git-branch" size="14"></platform-icon>
                </span>
                <span class="meta">
                    <p class="name">${entity.name || this.itemId} ${arrow} ${otherName}</p>
                    <p class="sub">${this._relationshipTypeLabel(rel.relationship_type)}</p>
                </span>
                <span class="arrow">
                    <platform-icon name="chevron-right" size="14"></platform-icon>
                </span>
            </button>
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

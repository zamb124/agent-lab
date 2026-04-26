/**
 * EntityCard — правая детальная панель карточки сущности на странице
 * `entities-page`. Получает entity-объект через свойство `.entity` (полная
 * запись из выдачи `crm/entities_list` или `crm/entities/get`).
 *
 * Источники данных:
 *   - `useResource('crm/entities')`   — загрузить сущность по id, если в проп
 *     пришёл только идентификатор (карточку открыли по ссылке).
 *   - `useOp('crm/entity_grants_list')` — список грантов по этой сущности
 *     (lazy, по кнопке «Доступы»).
 *   - `useOp('crm/related_entities')`  — связанные сущности 1-го уровня
 *     (lazy, по кнопке «Граф связей»).
 *
 * Никаких прямых HTTP-вызовов и stateful-импортов — только helpers платформы.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class CRMEntityCard extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        entity: { attribute: false },
        entityId: { type: String, attribute: 'entity-id' },
        _grantsExpanded: { state: true },
        _relatedExpanded: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                background: var(--crm-surface, #fff);
                border: 1px solid var(--crm-stroke);
                border-radius: 16px;
                overflow: hidden;
            }

            .empty {
                display: flex;
                flex: 1;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                padding: var(--space-6);
                text-align: center;
            }
            .empty-title { font-size: var(--text-base); color: var(--text-secondary); }
            .empty-subtitle { font-size: var(--text-sm); }

            .scroll {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .header {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
            }

            .type-icon {
                width: 48px;
                height: 48px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
                flex-shrink: 0;
            }

            .header-text { flex: 1; min-width: 0; }
            .name {
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                margin: 0 0 4px 0;
                word-wrap: break-word;
            }
            .meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .meta .dot { color: var(--text-tertiary); opacity: 0.4; }

            .search-score {
                display: flex;
                align-items: center;
                gap: 6px;
                height: 18px;
                position: relative;
                background: var(--crm-surface-tint);
                border-radius: 8px;
                overflow: hidden;
                max-width: 220px;
            }
            .search-score .score-bar {
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                opacity: 0.25;
            }
            .search-score .score-label {
                position: relative;
                z-index: 1;
                font-size: 11px;
                font-weight: 600;
                padding-left: 8px;
            }
            .search-score .match-type-badge {
                position: relative;
                z-index: 1;
                font-size: 9px;
                text-transform: uppercase;
                color: var(--text-tertiary);
                margin-left: auto;
                padding-right: 8px;
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: 500;
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
            }
            .status-badge.active { background: rgba(34, 197, 94, 0.15); color: #16a34a; }
            .status-badge.archived { background: rgba(148, 163, 184, 0.15); color: #64748b; }
            .status-badge.pending { background: rgba(234, 179, 8, 0.15); color: #ca8a04; }
            .status-badge.approved { background: rgba(34, 197, 94, 0.15); color: #16a34a; }
            .status-badge.rejected { background: rgba(244, 63, 94, 0.15); color: #e11d48; }

            .description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
                margin: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }

            .actions-bar {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 32px;
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .btn:hover { background: var(--crm-surface); color: var(--text-primary); }
            .btn-primary {
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                border-color: transparent;
            }
            .btn-primary:hover { background: var(--crm-daily-notes-cta-hover); }
            .btn-danger { color: var(--error, #f43f5e); border-color: rgba(244, 63, 94, 0.35); }

            .section-title {
                font-size: var(--text-xs);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
                margin: 0;
            }

            .tags {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .tag {
                display: inline-flex;
                align-items: center;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                background: var(--crm-surface-tint);
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }

            .attrs {
                display: grid;
                grid-template-columns: minmax(100px, 1fr) 2fr;
                row-gap: 6px;
                column-gap: var(--space-2);
                font-size: var(--text-sm);
            }
            .attr-key {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                padding-top: 2px;
            }
            .attr-val { color: var(--text-primary); word-break: break-word; }

            .collapsible-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                cursor: pointer;
                padding: var(--space-2) 0;
                border-top: 1px solid var(--crm-stroke);
            }

            .collapsible-content {
                padding-bottom: var(--space-2);
            }

            .empty-soft {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                padding: var(--space-2) 0;
            }

            .related-list {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .related-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 6px 8px;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                cursor: pointer;
                background: var(--crm-surface-muted);
                transition: background var(--duration-fast);
            }
            .related-item:hover { background: var(--crm-surface); }
            .related-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .related-type { font-size: var(--text-xs); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this.entity = null;
        this.entityId = '';
        this._grantsExpanded = false;
        this._relatedExpanded = false;
        this._entityResource = this.useResource('crm/entities');
        this._grantsOp = this.useOp('crm/entity_grants_list');
        this._relatedOp = this.useOp('crm/related_entities');
    }

    willUpdate(changed) {
        if (changed.has('entityId') && this.entityId && (!this.entity || this.entity.entity_id !== this.entityId)) {
            this._entityResource.get(this.entityId);
        }
    }

    _resolveEntity() {
        if (this.entity && typeof this.entity === 'object') return this.entity;
        if (!this.entityId) return null;
        const byId = this._entityResource.byId;
        if (byId && byId[this.entityId]) return byId[this.entityId];
        return null;
    }

    _onEdit(entity) {
        this.openModal('crm.entity', { mode: 'edit', id: entity.entity_id });
    }

    _onShare(entity) {
        this.openModal('crm.share', { entityId: entity.entity_id });
    }

    _onAccessRequest(entity) {
        this.openModal('crm.access_request', { entityId: entity.entity_id });
    }

    _onToggleGrants(entityId) {
        this._grantsExpanded = !this._grantsExpanded;
        if (this._grantsExpanded) {
            this._grantsOp.run({ entity_id: entityId });
        }
    }

    _onToggleRelated(entityId) {
        this._relatedExpanded = !this._relatedExpanded;
        if (this._relatedExpanded) {
            this._relatedOp.run({ entity_id: entityId });
        }
    }

    _onOpenRelated(relatedId) {
        this.dispatch('crm/entity_card/related_selected', { entity_id: relatedId }, { source: 'local' });
    }

    _searchScorePercent(entity) {
        if (!entity || typeof entity.score !== 'number' || !Number.isFinite(entity.score)) {
            return null;
        }
        const raw = entity.score;
        const pct = raw <= 1 ? raw * 100 : raw;
        return Math.min(100, Math.max(0, pct));
    }

    _renderAttrs(entity) {
        const attrs = entity.attributes;
        if (!attrs || typeof attrs !== 'object') return nothing;
        const entries = Object.entries(attrs).filter(([, v]) => v !== null && v !== undefined && v !== '');
        if (entries.length === 0) return nothing;
        return html`
            <div class="attrs">
                ${entries.map(([k, v]) => html`
                    <div class="attr-key">${k}</div>
                    <div class="attr-val">${typeof v === 'object' ? JSON.stringify(v) : String(v)}</div>
                `)}
            </div>
        `;
    }

    _renderRelated() {
        if (this._relatedOp.busy) {
            return html`<div class="empty-soft"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        const result = this._relatedOp.lastResult;
        const items = result && Array.isArray(result.items) ? result.items : [];
        if (items.length === 0) {
            return html`<div class="empty-soft">${this.t('entity_card.requests_empty')}</div>`;
        }
        return html`
            <div class="related-list">
                ${items.map((it) => html`
                    <div class="related-item" @click=${() => this._onOpenRelated(it.entity_id)}>
                        <platform-icon name="link" size="14"></platform-icon>
                        <span class="related-name">${it.name}</span>
                        <span class="related-type">${it.entity_type}</span>
                    </div>
                `)}
            </div>
        `;
    }

    render() {
        const entity = this._resolveEntity();
        if (!entity) {
            if (this.entityId && this._entityResource.loading) {
                return html`
                    <div class="empty">
                        <glass-spinner size="md"></glass-spinner>
                    </div>
                `;
            }
            return html`
                <div class="empty">
                    <platform-icon name="folder" size="48"></platform-icon>
                    <div class="empty-title">${this.t('entity_card.empty_pick_title')}</div>
                    <div class="empty-subtitle">${this.t('entity_card.empty_pick_subtitle')}</div>
                </div>
            `;
        }

        const tags = Array.isArray(entity.tags) ? entity.tags : [];

        return html`
            <div class="scroll">
                <div class="header">
                    <div class="type-icon">
                        <platform-icon name="folder" size="22"></platform-icon>
                    </div>
                    <div class="header-text">
                        <h2 class="name">${entity.name}</h2>
                        <div class="meta">
                            <span>${entity.entity_type}</span>
                            ${entity.entity_subtype
                                ? html`<span class="dot">/</span><span>${entity.entity_subtype}</span>`
                                : nothing}
                            ${entity.status
                                ? html`<span class="status-badge ${entity.status}">${entity.status}</span>`
                                : nothing}
                        </div>
                        ${(() => {
                            const pct = this._searchScorePercent(entity);
                            if (pct === null) return nothing;
                            const matchLabel = typeof entity.match_type === 'string' && entity.match_type.length > 0
                                ? entity.match_type
                                : '';
                            return html`
                                <div class="search-score" title=${matchLabel.length > 0 ? matchLabel : 'score'}>
                                    <div class="score-bar" style="width: ${Math.round(pct)}%"></div>
                                    <span class="score-label">${pct.toFixed(0)}%</span>
                                    ${matchLabel.length > 0
                                        ? html`<span class="match-type-badge">${matchLabel}</span>`
                                        : nothing}
                                </div>
                            `;
                        })()}
                    </div>
                </div>

                ${entity.description
                    ? html`<p class="description">${entity.description}</p>`
                    : nothing}

                ${tags.length > 0
                    ? html`
                        <div class="tags">
                            ${tags.map((t) => html`<span class="tag">${t}</span>`)}
                        </div>
                    `
                    : nothing}

                ${this._renderAttrs(entity)}

                <div class="actions-bar">
                    <button class="btn btn-primary" @click=${() => this._onEdit(entity)}>
                        <platform-icon name="edit" size="14"></platform-icon>
                        ${this.t('edit', {}, 'common')}
                    </button>
                    <button class="btn" @click=${() => this._onShare(entity)}>
                        <platform-icon name="share" size="14"></platform-icon>
                        ${this.t('grants.share_user')}
                    </button>
                    <button class="btn" @click=${() => this._onAccessRequest(entity)}>
                        <platform-icon name="lock" size="14"></platform-icon>
                        ${this.t('entity_card.request_access_tooltip')}
                    </button>
                </div>

                <div class="collapsible-header" @click=${() => this._onToggleRelated(entity.entity_id)}>
                    <span class="section-title">${this.t('entity_card.related_entities')}</span>
                    <platform-icon
                        name=${this._relatedExpanded ? 'chevron-up' : 'chevron-down'}
                        size="14"
                    ></platform-icon>
                </div>
                ${this._relatedExpanded
                    ? html`<div class="collapsible-content">${this._renderRelated()}</div>`
                    : nothing}

                <div class="collapsible-header" @click=${() => this._onToggleGrants(entity.entity_id)}>
                    <span class="section-title">${this.t('grants.section_title')}</span>
                    <platform-icon
                        name=${this._grantsExpanded ? 'chevron-up' : 'chevron-down'}
                        size="14"
                    ></platform-icon>
                </div>
                ${this._grantsExpanded
                    ? html`
                        <div class="collapsible-content">
                            ${this._grantsOp.busy
                                ? html`<div class="empty-soft"><glass-spinner size="sm"></glass-spinner></div>`
                                : html`<div class="empty-soft">${this.t('grants.loading')}</div>`}
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('crm-entity-card', CRMEntityCard);

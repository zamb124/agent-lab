import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { relatedEntityCardSharedStyles } from '../styles/related-entity-card.styles.js';
import {
    entityDisplayIconName,
    relatedSubtitle,
    relatedTone,
} from '../utils/related-entity-presenter.js';

export class CRMRelatedNeighborRows extends PlatformElement {
    static i18nNamespace = 'crm';

    static styles = [
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
        `,
        relatedEntityCardSharedStyles,
    ];

    static properties = {
        rows: { type: Array, attribute: false },
        entityTypeRows: { type: Array, attribute: false },
        emptyText: { type: String, attribute: 'empty-text' },
        showRemove: { type: Boolean, attribute: 'show-remove' },
    };

    constructor() {
        super();
        this.rows = [];
        this.entityTypeRows = [];
        this.emptyText = '';
        this.showRemove = false;
    }

    _thumbEntity(row) {
        if (row.otherEntity !== null && row.otherEntity !== undefined && typeof row.otherEntity === 'object') {
            return row.otherEntity;
        }
        return { entity_id: row.otherId, entity_type: '' };
    }

    _onOpen(row) {
        if (!row || typeof row.otherId !== 'string' || row.otherId.length === 0) {
            return;
        }
        const thumb = this._thumbEntity(row);
        const entityType = thumb && typeof thumb.entity_type === 'string' ? thumb.entity_type.trim() : '';
        this.emit('entity-open', { entityId: row.otherId, entity_type: entityType });
    }

    _onRemove(relationshipId, event) {
        event.preventDefault();
        event.stopPropagation();
        if (typeof relationshipId !== 'string' || relationshipId.length === 0) return;
        this.emit('relationship-remove', { relationshipId });
    }

    render() {
        if (!Array.isArray(this.rows)) {
            throw new Error('crm-related-neighbor-rows: rows must be an array');
        }
        if (this.rows.length === 0) {
            return html`<div class="related-empty">${this.emptyText}</div>`;
        }
        return html`
            <div class="neighbor-rows">
                ${this.rows.map((row) => {
                    if (!row || typeof row.relationshipId !== 'string' || row.relationshipId.length === 0) {
                        throw new Error('crm-related-neighbor-rows: row.relationshipId required');
                    }
                    if (typeof row.otherId !== 'string' || row.otherId.length === 0) {
                        throw new Error('crm-related-neighbor-rows: row.otherId required');
                    }
                    if (typeof row.relationshipTypeLabel !== 'string') {
                        throw new Error('crm-related-neighbor-rows: row.relationshipTypeLabel required');
                    }
                    if (typeof row.directionText !== 'string') {
                        throw new Error('crm-related-neighbor-rows: row.directionText required');
                    }
                    const thumb = this._thumbEntity(row);
                    const tone = relatedTone(thumb);
                    const iconName = entityDisplayIconName(thumb, this.entityTypeRows);
                    const name = thumb.name && typeof thumb.name === 'string' && thumb.name.length > 0
                        ? thumb.name
                        : row.otherId;
                    const sub = relatedSubtitle(thumb);
                    const scorePct = typeof row.scorePercent === 'number' && Number.isFinite(row.scorePercent)
                        ? Math.min(100, Math.max(0, row.scorePercent))
                        : null;
                    const scoreBlock = scorePct !== null
                        ? html`
                            <div class="neighbor-strength">
                                <div class="neighbor-strength-label">
                                    ${this.t('neighbor_row.semantic_match', { percent: String(Math.round(scorePct)) })}
                                </div>
                                <div class="neighbor-strength-track">
                                    <div class="neighbor-strength-fill" style="width: ${Math.round(scorePct)}%"></div>
                                </div>
                            </div>
                        `
                        : nothing;
                    const confPct = typeof row.confidencePercent === 'number' && Number.isFinite(row.confidencePercent)
                        ? Math.min(100, Math.max(0, row.confidencePercent))
                        : null;
                    const confidenceBlock = confPct !== null
                        ? html`
                            <div class="neighbor-confidence">
                                <div class="neighbor-confidence-label">
                                    ${this.t('neighbor_row.link_confidence', { percent: String(Math.round(confPct)) })}
                                </div>
                                <div class="neighbor-confidence-track">
                                    <div class="neighbor-confidence-fill" style="width: ${Math.round(confPct)}%"></div>
                                </div>
                            </div>
                        `
                        : nothing;
                    return html`
                        <div class="neighbor-line">
                            <button
                                type="button"
                                class="related-card tone-${tone} ${this.showRemove ? 'related-card--with-remove' : ''}"
                                @click=${() => this._onOpen(row)}
                            >
                                <span class="related-icon">
                                    <platform-icon name=${iconName} size="32"></platform-icon>
                                </span>
                                <span class="related-body">
                                    <p class="related-name">${name}</p>
                                    ${sub.length > 0 ? html`<p class="related-position">${sub}</p>` : ''}
                                    <p class="relationship-meta">
                                        <span class="relationship-type">${row.relationshipTypeLabel}</span>
                                        <span>${row.directionText}</span>
                                    </p>
                                    ${confidenceBlock}
                                    ${scoreBlock}
                                </span>
                            </button>
                            ${this.showRemove
                                ? html`
                                    <button
                                        type="button"
                                        class="neighbor-remove"
                                        ?disabled=${row.removeDisabled === true}
                                        title=${this.t('entity_modal.action_remove_relationship')}
                                        @click=${(e) => this._onRemove(row.relationshipId, e)}
                                    >
                                        <platform-icon name="trash" size="14"></platform-icon>
                                    </button>
                                `
                                : ''}
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('crm-related-neighbor-rows', CRMRelatedNeighborRows);

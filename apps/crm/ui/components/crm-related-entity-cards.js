import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { relatedEntityCardSharedStyles } from '../styles/related-entity-card.styles.js';
import {
    entityDisplayIconName,
    entityKind,
    relatedSubtitle,
    relatedTone,
} from '../utils/related-entity-presenter.js';

export class CRMRelatedEntityCards extends PlatformElement {
    static styles = [relatedEntityCardSharedStyles];

    static properties = {
        entities: { type: Array, attribute: false },
        entityTypeRows: { type: Array, attribute: false },
        excludeEntityIds: { type: Array, attribute: false },
        excludeKinds: { type: Array, attribute: false },
        emptyText: { type: String, attribute: 'empty-text' },
    };

    constructor() {
        super();
        this.entities = [];
        this.entityTypeRows = [];
        this.excludeEntityIds = [];
        this.excludeKinds = [];
        this.emptyText = '';
    }

    _filtered() {
        if (!Array.isArray(this.entities)) {
            throw new Error('crm-related-entity-cards: entities must be an array');
        }
        const exId = new Set(
            Array.isArray(this.excludeEntityIds)
                ? this.excludeEntityIds.filter((id) => typeof id === 'string' && id.length > 0)
                : [],
        );
        const exKind = new Set(
            Array.isArray(this.excludeKinds)
                ? this.excludeKinds.filter((k) => typeof k === 'string' && k.length > 0)
                : [],
        );
        return this.entities.filter((e) => {
            if (!e || typeof e.entity_id !== 'string' || e.entity_id.length === 0) return false;
            if (exId.has(e.entity_id)) return false;
            const kind = entityKind(e);
            if (exKind.size > 0 && kind.length > 0 && exKind.has(kind)) return false;
            return true;
        });
    }

    _onPick(entityId) {
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        this.emit('entity-open', { entityId });
    }

    render() {
        const list = this._filtered();
        if (list.length === 0) {
            return html`<div class="related-empty">${this.emptyText}</div>`;
        }
        return html`
            <div class="related-list">
                ${list.map((entity) => {
                    const tone = relatedTone(entity);
                    const subtitle = relatedSubtitle(entity);
                    const name = entity.name && entity.name.length > 0 ? entity.name : entity.entity_id;
                    const iconName = entityDisplayIconName(entity, this.entityTypeRows);
                    return html`
                        <button
                            type="button"
                            class="related-card tone-${tone}"
                            @click=${() => this._onPick(entity.entity_id)}
                        >
                            <span class="related-icon">
                                <platform-icon name=${iconName} size="32"></platform-icon>
                            </span>
                            <span class="related-body">
                                <p class="related-name">${name}</p>
                                ${subtitle.length > 0 ? html`<p class="related-position">${subtitle}</p>` : ''}
                            </span>
                        </button>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('crm-related-entity-cards', CRMRelatedEntityCards);

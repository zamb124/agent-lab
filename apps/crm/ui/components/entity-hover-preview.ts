import { html, css, nothing, unsafeCSS } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-hover-card.js';
import { formatPlatformDate } from '@platform/lib/utils/format-platform-date.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const PREVIEW_WIDTH = 320;

function _isIsoDateLike(value: unknown): value is string {
    return typeof value === 'string' && value.length > 0 && !Number.isNaN(Date.parse(value));
}

const ENTITY_PREVIEW_CSS = `
        .crm-entity-preview-portal {
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
        }
        .crm-entity-preview-portal__header {
            display: flex;
            align-items: flex-start;
            gap: var(--space-2);
        }
        .crm-entity-preview-portal__meta {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .crm-entity-preview-portal__name {
            margin: 0;
            color: var(--text-primary);
            font-size: var(--text-sm);
            font-weight: 700;
            line-height: 1.3;
            word-break: break-word;
        }
        .crm-entity-preview-portal__sub {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            flex-wrap: wrap;
            color: var(--text-secondary);
            font-size: var(--text-xs);
        }
        .crm-entity-preview-portal__status {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: var(--text-secondary);
            font-size: var(--text-xs);
            font-weight: 500;
        }
        .crm-entity-preview-portal__description {
            margin: 0;
            color: var(--text-secondary);
            font-size: var(--text-xs);
            line-height: 1.35;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .crm-entity-preview-portal__footer {
            display: flex;
            justify-content: flex-end;
        }
        .crm-entity-preview-portal__open-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 1px solid var(--glass-border-subtle);
            background: var(--glass-bg-subtle);
            color: var(--text-primary);
            border-radius: var(--radius-md);
            padding: 6px 10px;
            font-size: var(--text-xs);
            cursor: pointer;
        }
        .crm-entity-preview-portal__open-btn:hover {
            background: var(--glass-bg-medium);
        }
        .crm-entity-preview-portal__center {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 76px;
            color: var(--text-secondary);
            font-size: var(--text-xs);
        }
    `;

export class CRMEntityHoverPreview extends PlatformElement {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        // `previewOpen` вместо `open`: hover-превью — это не PlatformModal,
        // а портал-компонент. `open=true/false` в Lit-компонентах резервирует
        // CI-проверка modal canon за модалками, поэтому используем уникальное
        // имя property + атрибут `preview-open`.
        previewOpen: { type: Boolean, reflect: true, attribute: 'preview-open' },
        entityId: { type: String, attribute: 'entity-id' },
        anchorRect: { attribute: false },
    };

    private _entities: ResourceController;
    private _locale: SelectController<string>;

    constructor() {
        super();
        this.previewOpen = false;
        this.entityId = '';
        this.anchorRect = null;
        this._entities = this.useResource('crm/entities');
        this._locale = this.select((s: Record<string, any>) => typeof s.i18n.locale === 'string' && s.i18n.locale.length > 0 ? s.i18n.locale : 'en');
    }

    _formatDate(value: unknown): string {
        if (!_isIsoDateLike(value)) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return formatPlatformDate(parsed, this._locale.value ?? 'en', { day: '2-digit', month: '2-digit', year: 'numeric' });
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        if (!this.previewOpen) {
            return;
        }
        if ((changed.has('previewOpen') || changed.has('entityId'))
            && typeof this.entityId === 'string'
            && this.entityId.length > 0
            && this._entities.byId[this.entityId] === undefined) {
            this._entities.get(this.entityId);
        }
    }

    _iconByType(entity: Record<string, any> | null | undefined): string {
        const type = entity && typeof entity.entity_type === 'string' ? entity.entity_type : '';
        if (type === 'task') return 'tasks';
        if (type === 'note') return 'note';
        if (type === 'company' || type === 'organization') return 'building';
        if (type === 'document') return 'folder';
        if (type === 'meeting' || type === 'event') return 'calendar';
        return 'user';
    }

    _entityTypeLabel(entity: Record<string, any> | null | undefined): string {
        if (entity && typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) {
            return entity.entity_subtype;
        }
        return entity && typeof entity.entity_type === 'string' ? entity.entity_type : '';
    }

    _description(entity: Record<string, any> | null | undefined): string {
        const text = entity && typeof entity.description === 'string' ? entity.description.trim() : '';
        if (text.length <= 180) {
            return text;
        }
        return `${text.slice(0, 180)}...`;
    }

    _emitOpen() {
        if (typeof this.entityId !== 'string' || this.entityId.length === 0) {
            return;
        }
        this.emit('open', { entityId: this.entityId });
    }

    _renderCardBody() {
        const entity = typeof this.entityId === 'string' && this.entityId.length > 0
            ? this._entities.byId[this.entityId]
            : null;
        const hasEntity = entity !== undefined && entity !== null;
        const createdAt = hasEntity && typeof entity.created_at === 'string' ? this._formatDate(entity.created_at) : '';
        const description = hasEntity ? this._description(entity) : '';
        return hasEntity
            ? html`
                <div class="crm-entity-preview-portal__header">
                    <platform-icon name=${this._iconByType(entity)} size="18"></platform-icon>
                    <div class="crm-entity-preview-portal__meta">
                        <p class="crm-entity-preview-portal__name">${entity.name}</p>
                        <div class="crm-entity-preview-portal__sub">
                            <span>${this._entityTypeLabel(entity)}</span>
                            ${createdAt.length > 0 ? html`<span>${createdAt}</span>` : ''}
                        </div>
                    </div>
                </div>
                ${typeof entity.status === 'string' && entity.status.length > 0
                    ? html`<span class="crm-entity-preview-portal__status">${entity.status}</span>`
                    : ''}
                ${description.length > 0
                    ? html`<p class="crm-entity-preview-portal__description">${description}</p>`
                    : ''}
                <div class="crm-entity-preview-portal__footer">
                    <button type="button" class="crm-entity-preview-portal__open-btn" @click=${() => this._emitOpen()}>
                        <platform-icon name="arrow-right" size="14"></platform-icon>
                        ${this.t('note_view.summary_entity_open')}
                    </button>
                </div>
            `
            : html`
                <div class="crm-entity-preview-portal__center">
                    ${this._entities.loading
                        ? html`<glass-spinner size="xs"></glass-spinner>`
                        : this.t('note_page.not_found_title')}
                </div>
            `;
    }

    override render(): TemplateResult {
        return html`
            <platform-hover-card
                ?open=${this.previewOpen}
                .anchor=${this.anchorRect}
                width=${PREVIEW_WIDTH}
                @hover-card-enter=${() => this.emit('preview-enter')}
                @hover-card-leave=${() => this.emit('preview-leave')}
            >
                ${this.previewOpen
                    ? html`<div class="crm-entity-preview-portal">${this._renderCardBody()}</div>`
                    : nothing}
            </platform-hover-card>
        `;
    }
    declare previewOpen: boolean;
    declare entityId: string;
    declare anchorRect: unknown;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        unsafeCSS(ENTITY_PREVIEW_CSS),
        css`
            :host {
                display: contents;
            }
        `,
    ];
}

customElements.define('crm-entity-hover-preview', CRMEntityHoverPreview);

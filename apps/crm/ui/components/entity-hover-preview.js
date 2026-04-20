import { html, render as litRender } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';

const PREVIEW_WIDTH = 320;
const PREVIEW_GAP = 10;
const PREVIEW_VIEWPORT_PADDING = 12;
const PREVIEW_EXPECTED_HEIGHT = 180;

let _previewStylesInjected = false;

function _ensurePreviewStyles() {
    if (_previewStylesInjected) return;
    _previewStylesInjected = true;
    const style = document.createElement('style');
    style.id = 'crm-entity-hover-preview-portal-styles';
    style.textContent = `
        .crm-entity-preview-portal {
            position: fixed;
            width: ${PREVIEW_WIDTH}px;
            max-width: min(${PREVIEW_WIDTH}px, calc(100vw - 24px));
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-strong, 16px));
            -webkit-backdrop-filter: blur(var(--glass-blur-strong, 16px));
            border-radius: var(--radius-lg);
            padding: var(--space-3);
            box-shadow: var(--glass-shadow-strong, 0 16px 40px rgba(0, 0, 0, 0.35));
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
            opacity: 0;
            transform: translateY(4px);
            transition: opacity 140ms ease, transform 140ms ease;
            color: var(--text-primary);
            font-family: var(--font-sans);
        }
        .crm-entity-preview-portal[data-open="true"] {
            opacity: 1;
            transform: translateY(0);
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
    document.head.appendChild(style);
}

function _isIsoDateLike(value) {
    return typeof value === 'string' && value.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(value);
}

function _formatDate(value) {
    if (!_isIsoDateLike(value)) {
        return '';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return '';
    }
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(parsed);
}

export class CRMEntityHoverPreview extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        // `previewOpen` вместо `open`: hover-превью — это не PlatformModal,
        // а портал-компонент. `open=true/false` в Lit-компонентах резервирует
        // CI-проверка modal canon за модалками, поэтому используем уникальное
        // имя property + атрибут `preview-open`.
        previewOpen: { type: Boolean, reflect: true, attribute: 'preview-open' },
        entityId: { type: String, attribute: 'entity-id' },
        anchorRect: { attribute: false },
    };

    constructor() {
        super();
        this.previewOpen = false;
        this.entityId = '';
        this.anchorRect = null;
        this._entities = this.useResource('crm/entities');
        this._portal = null;
        this._onReposition = this._onReposition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        _ensurePreviewStyles();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._closePortal();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('previewOpen')) {
            if (this.previewOpen) {
                this._openPortal();
            } else {
                this._closePortal();
                return;
            }
        }
        if (this.previewOpen) {
            if ((changed.has('previewOpen') || changed.has('entityId'))
                && typeof this.entityId === 'string'
                && this.entityId.length > 0
                && this._entities.byId[this.entityId] === undefined) {
                this._entities.get(this.entityId);
            }
            this._renderPortal();
            this._reposition();
        }
    }

    _openPortal() {
        if (this._portal) return;
        const node = document.createElement('div');
        node.className = 'crm-entity-preview-portal';
        node.style.zIndex = String(nextModalLayerZIndex());
        node.addEventListener('mouseenter', () => this.emit('preview-enter'));
        node.addEventListener('mouseleave', () => this.emit('preview-leave'));
        document.body.appendChild(node);
        this._portal = node;
        this._resizeObserver = new ResizeObserver(this._onReposition);
        this._resizeObserver.observe(document.documentElement);
        document.addEventListener('scroll', this._onReposition, true);
        requestAnimationFrame(() => {
            if (this._portal) {
                this._portal.dataset.open = 'true';
            }
        });
    }

    _closePortal() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        document.removeEventListener('scroll', this._onReposition, true);
        if (this._portal && this._portal.parentNode) {
            litRender(null, this._portal);
            this._portal.remove();
        }
        this._portal = null;
    }

    _onReposition() {
        if (!this._portal) return;
        requestAnimationFrame(() => this._reposition());
    }

    _reposition() {
        if (!this._portal) return;
        if (this.anchorRect === null || typeof this.anchorRect !== 'object') return;
        const leftSource = typeof this.anchorRect.left === 'number' ? this.anchorRect.left : 0;
        const topSource = typeof this.anchorRect.top === 'number' ? this.anchorRect.top : 0;
        const heightSource = typeof this.anchorRect.height === 'number' ? this.anchorRect.height : 0;
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const maxLeft = Math.max(PREVIEW_VIEWPORT_PADDING, viewportWidth - PREVIEW_WIDTH - PREVIEW_VIEWPORT_PADDING);
        const left = Math.min(Math.max(PREVIEW_VIEWPORT_PADDING, leftSource), maxLeft);
        const belowTop = topSource + heightSource + PREVIEW_GAP;
        const aboveTop = topSource - PREVIEW_GAP - PREVIEW_EXPECTED_HEIGHT;
        const top = belowTop + PREVIEW_EXPECTED_HEIGHT <= viewportHeight
            ? belowTop
            : Math.max(PREVIEW_VIEWPORT_PADDING, aboveTop);
        this._portal.style.left = `${Math.round(left)}px`;
        this._portal.style.top = `${Math.round(top)}px`;
    }

    _iconByType(entity) {
        const type = entity && typeof entity.entity_type === 'string' ? entity.entity_type : '';
        if (type === 'task') return 'tasks';
        if (type === 'note') return 'note';
        if (type === 'company' || type === 'organization') return 'building';
        if (type === 'document') return 'folder';
        if (type === 'meeting' || type === 'event') return 'calendar';
        return 'user';
    }

    _entityTypeLabel(entity) {
        if (entity && typeof entity.entity_subtype === 'string' && entity.entity_subtype.length > 0) {
            return entity.entity_subtype;
        }
        return entity && typeof entity.entity_type === 'string' ? entity.entity_type : '';
    }

    _description(entity) {
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

    _renderPortal() {
        if (!this._portal) return;
        const entity = typeof this.entityId === 'string' && this.entityId.length > 0
            ? this._entities.byId[this.entityId]
            : null;
        const hasEntity = entity !== undefined && entity !== null;
        const createdAt = hasEntity && typeof entity.created_at === 'string' ? _formatDate(entity.created_at) : '';
        const description = hasEntity ? this._description(entity) : '';
        const tpl = hasEntity
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
                        ? html`<glass-spinner size="16"></glass-spinner>`
                        : this.t('note_page.not_found_title')}
                </div>
            `;
        litRender(tpl, this._portal);
    }

    render() {
        return html``;
    }
}

customElements.define('crm-entity-hover-preview', CRMEntityHoverPreview);

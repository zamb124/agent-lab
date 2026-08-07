/**
 * Lazy live-preview card for a Flow UI page template in the gallery modal.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buildFlowUIPageTemplatePreviewDocument } from '@platform/lib/flow-ui/templates/gallery/preview-document.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceTemplateCard extends PlatformElement {
    static properties = {
        template: { attribute: false },
        locale: { type: String },
        selected: { type: Boolean, reflect: true },
        _visible: { type: Boolean, state: true },
        _previewDocument: { attribute: false, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
            .card {
                display: grid;
                grid-template-rows: minmax(168px, 200px) auto;
                gap: 0;
                height: 100%;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                overflow: hidden;
                cursor: pointer;
                transition:
                    border-color 160ms ease,
                    transform 160ms ease,
                    box-shadow 160ms ease,
                    background 160ms ease;
            }
            .card:hover,
            :host([selected]) .card {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
                transform: translateY(-2px);
                box-shadow: var(--shadow-md, 0 8px 24px color-mix(in srgb, var(--bg-primary) 35%, transparent));
            }
            .card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .preview {
                position: relative;
                overflow: hidden;
                background:
                    radial-gradient(120% 80% at 10% 0%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 55%),
                    var(--bg-secondary, var(--glass-tint-medium));
                pointer-events: none;
            }
            .preview-stage {
                position: absolute;
                inset: 0;
                display: grid;
                place-items: start stretch;
                overflow: hidden;
            }
            .preview-scale {
                width: 360px;
                height: 420px;
                transform: scale(0.52);
                transform-origin: top left;
                margin: var(--space-3) 0 0 var(--space-3);
            }
            .preview-scale platform-flow-ui {
                display: block;
                width: 360px;
                height: 420px;
                border-radius: var(--radius-md);
                overflow: hidden;
                background: var(--flow-ui-page-background, var(--bg-primary));
                box-shadow: var(--shadow-sm, 0 2px 8px color-mix(in srgb, var(--bg-primary) 25%, transparent));
            }
            .preview-placeholder {
                position: absolute;
                inset: 0;
                display: grid;
                place-items: center;
                color: var(--text-tertiary);
            }
            .meta {
                display: grid;
                gap: var(--space-1);
                padding: var(--space-3) var(--space-4) var(--space-4);
                min-width: 0;
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .title {
                font-weight: 650;
                color: var(--text-primary);
                font-size: var(--text-sm);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .desc {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.45;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            platform-icon {
                color: var(--accent);
                flex-shrink: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.template = null;
        this.locale = 'en';
        this.selected = false;
        this._visible = false;
        this._previewDocument = null;
        this._observer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    this._mountPreview();
                    break;
                }
            }
        }, { rootMargin: '120px 0px' });
        this.updateComplete.then(() => {
            const card = this.renderRoot?.querySelector('.card');
            if (card && this._observer) {
                this._observer.observe(card);
            }
        });
    }

    disconnectedCallback() {
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
        super.disconnectedCallback();
    }

    _mountPreview() {
        if (this._visible || !this.template) {
            return;
        }
        const locale = this.locale === 'ru' ? 'ru' : 'en';
        this._previewDocument = buildFlowUIPageTemplatePreviewDocument(this.template.template_id, locale);
        this._visible = true;
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
    }

    _onActivate() {
        this.emit('template-select', { templateId: this.template.template_id });
    }

    render() {
        if (!this.template) {
            return nothing;
        }
        const locale = this.locale === 'ru' ? 'ru' : 'en';
        return html`
            <article
                class="card"
                role="button"
                tabindex="0"
                aria-pressed=${this.selected ? 'true' : 'false'}
                @click=${() => this._onActivate()}
                @keydown=${(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        this._onActivate();
                    }
                }}
            >
                <div class="preview" aria-hidden="true">
                    ${this._visible && this._previewDocument
                        ? html`<div class="preview-stage">
                            <div class="preview-scale">
                                <platform-flow-ui
                                    profile="editor_test"
                                    .initialDocument=${this._previewDocument}
                                    theme="auto"
                                ></platform-flow-ui>
                            </div>
                        </div>`
                        : html`<div class="preview-placeholder">
                            <platform-icon name=${this.template.icon} size="28"></platform-icon>
                        </div>`}
                </div>
                <div class="meta">
                    <div class="head">
                        <platform-icon name=${this.template.icon} size="16"></platform-icon>
                        <span class="title">${this.template.title[locale]}</span>
                    </div>
                    <div class="desc">${this.template.description[locale]}</div>
                </div>
            </article>
        `;
    }
}

if (!customElements.get('flows-interface-template-card')) {
    customElements.define('flows-interface-template-card', FlowsInterfaceTemplateCard);
}

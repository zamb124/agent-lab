/**
 * Flow UI page template gallery for the Interface Editor.
 * Browse (search + categories + live preview cards) → detail → apply.
 * Applying a template replaces the page surface as one undoable transaction —
 * the caller owns the document mutation.
 */
import { css, html, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import {
    FLOW_UI_PAGE_TEMPLATE_CATEGORIES,
    filterFlowUIPageTemplates,
    flowUIPageTemplate,
} from '@platform/lib/flow-ui/templates/page-templates.js';
import { buildFlowUIPageTemplatePreviewDocument } from '@platform/lib/flow-ui/templates/gallery/preview-document.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '../components/interface-editor/flows-interface-template-card.js';

export class FlowsInterfaceTemplateModal extends PlatformModal {
    static modalKind = 'flows.interface_template';
    static i18nNamespace = 'flows';

    static properties = {
        onApply: { attribute: false },
        _query: { type: String, state: true },
        _category: { type: String, state: true },
        _detailTemplateId: { type: String, state: true },
        _detailDocument: { attribute: false, state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --platform-modal-xl-body-min-block-size: min(72vh, 640px);
            }
            .gallery {
                display: grid;
                gap: var(--space-4);
                min-height: min(64vh, 560px);
            }
            .toolbar {
                display: grid;
                gap: var(--space-3);
            }
            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .chip {
                display: inline-flex;
                align-items: center;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border-radius: var(--radius-full);
                padding: 6px 12px;
                font: inherit;
                font-size: var(--text-xs);
                font-weight: 600;
                cursor: pointer;
                user-select: none;
                transition: border-color 140ms ease, background 140ms ease, color 140ms ease;
            }
            .chip:hover {
                border-color: var(--accent);
                color: var(--text-primary);
            }
            .chip[aria-pressed='true'] {
                border-color: var(--accent);
                background: color-mix(in srgb, var(--accent) 16%, transparent);
                color: var(--text-primary);
            }
            .chip:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
                gap: var(--space-4);
            }
            .empty {
                display: grid;
                place-items: center;
                gap: var(--space-2);
                min-height: 220px;
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-lg);
                background:
                    radial-gradient(80% 60% at 50% 0%, color-mix(in srgb, var(--accent) 10%, transparent), transparent 70%),
                    var(--glass-solid-subtle);
            }
            .detail {
                display: grid;
                grid-template-columns: minmax(0, 1.4fr) minmax(240px, 0.7fr);
                gap: var(--space-5);
                min-height: min(64vh, 560px);
            }
            @media (max-width: 900px) {
                .detail {
                    grid-template-columns: 1fr;
                }
            }
            .detail-preview {
                position: relative;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
                background:
                    radial-gradient(120% 80% at 0% 0%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 50%),
                    var(--bg-secondary, var(--glass-tint-medium));
                min-height: 360px;
            }
            .detail-preview platform-flow-ui {
                display: block;
                width: 100%;
                height: 100%;
                min-height: 420px;
                pointer-events: none;
                background: var(--flow-ui-page-background, var(--bg-primary));
            }
            .detail-side {
                display: grid;
                align-content: start;
                gap: var(--space-4);
            }
            .detail-title {
                margin: 0;
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
            }
            .detail-desc {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
            }
            .detail-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .tag {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full);
                padding: 4px 10px;
                background: var(--glass-solid-subtle);
            }
            .hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.45;
            }
            .detail-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.onApply = null;
        this.size = 'xl';
        this._query = '';
        this._category = 'all';
        this._detailTemplateId = null;
        this._detailDocument = null;
    }

    _locale() {
        return this.select((state) => state.i18n.locale).value === 'ru' ? 'ru' : 'en';
    }

    _filtered() {
        return filterFlowUIPageTemplates({
            category: this._category,
            query: this._query,
            locale: this._locale(),
        });
    }

    _openDetail(templateId) {
        const locale = this._locale();
        this._detailTemplateId = templateId;
        this._detailDocument = buildFlowUIPageTemplatePreviewDocument(templateId, locale);
    }

    _closeDetail() {
        this._detailTemplateId = null;
        this._detailDocument = null;
    }

    _apply(templateId) {
        if (typeof this.onApply !== 'function') {
            throw new Error('flows.interface_template: onApply callback is required');
        }
        this.onApply(templateId);
        this.close();
    }

    _categoryLabel(category) {
        if (category === 'all') {
            return this.t('interface_editor.template_category_all');
        }
        return this.t(`interface_editor.template_category_${category}`);
    }

    renderHeader() {
        if (this._detailTemplateId) {
            return this.t('interface_editor.template_detail_title');
        }
        return this.t('interface_editor.template_modal_title');
    }

    renderBody() {
        if (this._detailTemplateId) {
            return this._renderDetail();
        }
        return this._renderBrowse();
    }

    _renderBrowse() {
        const locale = this._locale();
        const templates = this._filtered();
        const categories = ['all', ...FLOW_UI_PAGE_TEMPLATE_CATEGORIES];
        return html`<div class="gallery">
            <div class="toolbar">
                <platform-modal-search-field
                    layout="fill"
                    .value=${this._query}
                    placeholder=${this.t('interface_editor.template_search')}
                    @change=${(event) => {
                        const value = event.detail?.value;
                        this._query = typeof value === 'string' ? value : '';
                    }}
                ></platform-modal-search-field>
                <div class="chips" role="toolbar" aria-label=${this.t('interface_editor.template_categories')}>
                    ${categories.map((category) => html`
                        <span
                            class="chip"
                            role="button"
                            tabindex="0"
                            aria-pressed=${this._category === category ? 'true' : 'false'}
                            @click=${() => { this._category = category; }}
                            @keydown=${(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault();
                                    this._category = category;
                                }
                            }}
                        >${this._categoryLabel(category)}</span>
                    `)}
                </div>
            </div>
            ${templates.length === 0
                ? html`<div class="empty">
                    <platform-icon name="search" size="24"></platform-icon>
                    <div>${this.t('interface_editor.template_empty')}</div>
                </div>`
                : html`<div class="grid">
                    ${templates.map((template) => html`
                        <flows-interface-template-card
                            .template=${template}
                            locale=${locale}
                            @template-select=${(event) => this._openDetail(event.detail.templateId)}
                        ></flows-interface-template-card>
                    `)}
                </div>`}
        </div>`;
    }

    _renderDetail() {
        const locale = this._locale();
        const template = flowUIPageTemplate(this._detailTemplateId);
        return html`<div class="detail">
            <div class="detail-preview">
                ${this._detailDocument
                    ? html`<platform-flow-ui
                        profile="editor_test"
                        .initialDocument=${this._detailDocument}
                        theme="auto"
                    ></platform-flow-ui>`
                    : nothing}
            </div>
            <div class="detail-side">
                <div class="detail-meta">
                    <span class="tag">${this._categoryLabel(template.category)}</span>
                    ${template.tags.map((tag) => html`<span class="tag">${tag}</span>`)}
                </div>
                <h3 class="detail-title">${template.title[locale]}</h3>
                <p class="detail-desc">${template.description[locale]}</p>
                <p class="hint">${this.t('interface_editor.template_replace_hint')}</p>
                <div class="detail-actions">
                    <platform-button variant="ghost" @click=${() => this._closeDetail()}>
                        ${this.t('interface_editor.template_back')}
                    </platform-button>
                    <platform-button variant="primary" @click=${() => this._apply(template.template_id)}>
                        ${this.t('interface_editor.template_apply')}
                    </platform-button>
                </div>
            </div>
        </div>`;
    }
}

if (!customElements.get('flows-interface-template-modal')) {
    customElements.define('flows-interface-template-modal', FlowsInterfaceTemplateModal);
}
registerModalKind(FlowsInterfaceTemplateModal.modalKind, 'flows-interface-template-modal');

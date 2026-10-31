/**
 * Галерея шаблонов документа Flow UI (``GET /flows/api/v1/flow-ui/templates``): поиск, категории,
 * живые карточки → детальный просмотр → «Применить». Применение заменяет весь документ одной
 * командой истории; мутацию выполняет вызывающий через ``onApply(document)``.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { css, html, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '../components/interface-editor/flows-interface-template-card.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

const CATEGORIES = Object.freeze(['all', 'conversation', 'forms', 'dashboards', 'content', 'utility']);

export class FlowsInterfaceTemplateModal extends PlatformModal {
    static modalKind = 'flows.interface_template';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        onApply: { attribute: false },
        _query: { type: String, state: true },
        _category: { type: String, state: true },
        _detailId: { type: String, state: true },
    }
    declare onApply: any;
    declare _query: string;
    declare _category: string;
    declare _detailId: string;
;

    static override styles: CSSResultGroup = [PlatformModal.styles, css`
        :host { --platform-modal-xl-body-min-block-size: min(72vh, 640px); }
        .gallery { display: grid; gap: var(--space-4); min-height: min(64vh, 560px); align-content: start; }
        .toolbar { display: grid; gap: var(--space-3); }
        .chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
        .chip { display: inline-flex; align-items: center; border: 1px solid var(--border-subtle); background: var(--glass-solid-subtle); color: var(--text-secondary); border-radius: var(--radius-full); padding: 4px 12px; font-size: 12px; cursor: pointer; }
        .chip[aria-pressed='true'] { border-color: var(--accent); color: var(--text-primary); background: color-mix(in srgb, var(--accent) 12%, transparent); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--space-3); }
        .empty { display: grid; place-items: center; gap: var(--space-2); padding: var(--space-8); color: var(--text-tertiary); }
        .detail { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(260px, 1fr); gap: var(--space-4); min-height: min(64vh, 560px); }
        .detail-preview { border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); overflow: auto; background: var(--bg-secondary); padding: var(--space-4); }
        .detail-preview platform-flow-ui { display: block; pointer-events: none; }
        .detail-side { display: grid; gap: var(--space-3); align-content: start; }
        .detail-title { margin: 0; font-size: 18px; font-weight: 650; color: var(--text-primary); }
        .detail-desc { margin: 0; color: var(--text-secondary); line-height: 1.5; }
        .hint { margin: 0; font-size: 12px; color: var(--text-tertiary); }
        .detail-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
        @media (max-width: 900px) { .detail { grid-template-columns: 1fr; } }
    `];
    private _templates: OpController;

    constructor() {
        super();
        this.onApply = null;
        this.size = 'xl';
        this._query = '';
        this._category = 'all';
        this._detailId = '';
        this._templates = this.useOp('flows/flow_ui_templates');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._templates.run(null);
    }

    _items() {
        const page = this._templates.lastResult;
        if (page === null || page === undefined) return [];
        if (!isPlainObject(page)) {
            throw new Error('flows-interface-template-modal: templates items required');
        }
        const rawItems = page.items;
        if (!Array.isArray(rawItems)) {
            throw new Error('flows-interface-template-modal: templates items required');
        }
        const items = rawItems;
        const query = this._query.trim().toLowerCase();
        return items.filter((template: any) => (this._category === 'all' || template.category === this._category)
            && (query === '' || template.title.toLowerCase().includes(query) || template.description.toLowerCase().includes(query)));
    }

    _apply(template: any) {
        if (typeof this.onApply !== 'function') throw new Error('flows.interface_template: onApply callback is required');
        this.onApply(template.document);
        this.close();
    }

    override renderHeader() {
        return this.t(this._detailId === '' ? 'interface_editor.template_modal_title' : 'interface_editor.template_detail_title');
    }

    override renderBody() {
        if (this._detailId !== '') {
            return this._renderDetail(((this._templates.lastResult as any).items.find as any)((item: any) => item.template_id === this._detailId));
        }
        return this._renderBrowse();
    }

    _renderBrowse() {
        const templates = this._items();
        return html`<div class="gallery">
            <div class="toolbar">
                <platform-modal-search-field layout="fill" .value=${this._query} placeholder=${this.t('interface_editor.template_search')}
                    @change=${(event: CustomEvent) => { this._query = event.detail.value; }}></platform-modal-search-field>
                <div class="chips" role="toolbar" aria-label=${this.t('interface_editor.template_categories')}>
                    ${CATEGORIES.map((category) => html`<span class="chip" role="button" tabindex="0" aria-pressed=${this._category === category ? 'true' : 'false'}
                        @click=${() => { this._category = category; }}
                        @keydown=${(event: KeyboardEvent) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this._category = category; } }}
                    >${this.t(`interface_editor.template_category_${category}`)}</span>`)}
                </div>
            </div>
            ${this._templates.busy && templates.length === 0
                ? html`<platform-empty-state loading></platform-empty-state>`
                : templates.length === 0
                ? html`<platform-empty-state icon="search" title=${this.t('interface_editor.template_empty')}></platform-empty-state>`
                : html`<div class="grid">
                    ${templates.map((template: any) => html`<flows-interface-template-card .template=${template}
                        @template-select=${(event: CustomEvent) => { this._detailId = event.detail.templateId; }}></flows-interface-template-card>`)}
                </div>`}
        </div>`;
    }

    _renderDetail(template: any) {
        return html`<div class="detail">
            <div class="detail-preview"><platform-flow-ui editing theme="auto" .initialDocument=${template.document} .sampleState=${{}}></platform-flow-ui></div>
            <div class="detail-side">
                <span class="chip" aria-pressed="true">${this.t(`interface_editor.template_category_${template.category}`)}</span>
                <h3 class="detail-title">${template.title}</h3>
                <p class="detail-desc">${template.description}</p>
                <p class="hint">${this.t('interface_editor.template_replace_hint')}</p>
                <div class="detail-actions">
                    <platform-button ghost @click=${() => { this._detailId = ''; }}>${this.t('interface_editor.template_back')}</platform-button>
                    <platform-button primary @click=${() => this._apply(template)}>${this.t('interface_editor.template_apply')}</platform-button>
                </div>
            </div>
        </div>`;
    }
}

if (!customElements.get('flows-interface-template-modal')) customElements.define('flows-interface-template-modal', FlowsInterfaceTemplateModal);
registerModalKind(FlowsInterfaceTemplateModal.modalKind, 'flows-interface-template-modal');

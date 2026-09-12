/**
 * Карточка шаблона документа Flow UI в галерее: живой уменьшенный рендер ``<platform-flow-ui editing>``
 * (монтируется при появлении во viewport), название и описание.
 *
 * Событие: ``template-select {templateId}``.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceTemplateCard extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        template: { attribute: false },
        selected: { type: Boolean, reflect: true },
        _visible: { type: Boolean, state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; min-width: 0; }
        .card { display: grid; grid-template-rows: 180px auto; height: 100%; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--glass-solid-subtle); overflow: hidden; cursor: pointer; transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease; }
        .card:hover, :host([selected]) .card { border-color: var(--accent); transform: translateY(-2px); box-shadow: var(--shadow-md); }
        .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
        .preview { position: relative; overflow: hidden; background: var(--bg-secondary, var(--glass-tint-medium)); pointer-events: none; }
        .preview platform-flow-ui { position: absolute; top: 12px; left: 12px; width: 640px; transform: scale(0.42); transform-origin: top left; }
        .placeholder { position: absolute; inset: 0; display: grid; place-items: center; color: var(--text-tertiary); }
        .meta { display: grid; gap: 4px; padding: 10px 12px 12px; }
        .title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 650; color: var(--text-primary); }
        .description { font-size: 12px; line-height: 1.4; color: var(--text-tertiary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    `];

    constructor() {
        super();
        this.template = null;
        this.selected = false;
        this._visible = false;
        this._observer = null;
    }

    firstUpdated() {
        this._observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                this._visible = true;
                this._observer.disconnect();
            }
        }, { rootMargin: '120px' });
        this._observer.observe(this);
    }

    disconnectedCallback() {
        if (this._observer) this._observer.disconnect();
        super.disconnectedCallback();
    }

    _select() {
        this.emit('template-select', { templateId: this.template.template_id });
    }

    render() {
        if (this.template === null) return nothing;
        return html`<div class="card" role="button" tabindex="0" @click=${this._select}
            @keydown=${(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this._select(); } }}>
            <div class="preview">
                ${this._visible
                    ? html`<platform-flow-ui editing theme="auto" .initialDocument=${this.template.document} .sampleState=${{}}></platform-flow-ui>`
                    : html`<div class="placeholder"><platform-icon name=${this.template.icon} size="28"></platform-icon></div>`}
            </div>
            <div class="meta">
                <div class="title"><platform-icon name=${this.template.icon} size="14"></platform-icon>${this.template.title}</div>
                <div class="description">${this.template.description}</div>
            </div>
        </div>`;
    }
}

if (!customElements.get('flows-interface-template-card')) customElements.define('flows-interface-template-card', FlowsInterfaceTemplateCard);

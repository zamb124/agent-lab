/**
 * Страница документа: блоки верхнего уровня в одну колонку. Контекст рендера блоков даёт хост
 * ``<platform-flow-ui>`` (``host.blockContext()``); на холсте редактора тот же хост с атрибутом ``editing``.
 */

import { LitElement, css, html, nothing, type PropertyValues } from '../../lit-shim.js';
import { blockStyles, renderBlocks } from '../blocks/registry.js';
import type { FlowUIStore, FlowUiPage as FlowUiPageModel, FlowUiBlock, FlowUiRenderContext } from '../runtime/flow-ui-store.js';
import { blockText } from '../runtime/templating.js';

/** Хост ``<platform-flow-ui>``, нужный странице: store и контекст рендера блоков. */
export interface FlowUiPageHostLike {
    store: FlowUIStore;
    blockContext(): FlowUiRenderContext;
}

/** Чат на весь экран только если на странице нет других блоков: иначе overflow:hidden их срезает. */
export function pageFillsViewport(page: { blocks?: unknown }): boolean {
    return Array.isArray(page.blocks)
        && (page.blocks as FlowUiBlock[]).some((block) => block.type === 'conversation')
        && (page.blocks as FlowUiBlock[]).every((block) => block.type === 'conversation' || block.type === 'agent_identity');
}

export class FlowUIPage extends LitElement {
    declare host: FlowUiPageHostLike | null;
    declare page: FlowUiPageModel | null;
    declare showTitle: boolean;
    declare editing: boolean;
    declare fluid: boolean;
    declare selectedBlockId: string;
    private _unsubscribe: (() => void) | null;

    static override properties = {
        host: { attribute: false },
        page: { attribute: false },
        showTitle: { type: Boolean, attribute: 'show-title' },
        editing: { type: Boolean, reflect: true },
        fluid: { type: Boolean, reflect: true },
        selectedBlockId: { attribute: false },
    };

    static override styles = [blockStyles, css`
        :host { display: flex; flex-direction: column; min-height: 0; height: 100%; }
        .page { flex: 1 1 0; min-height: 0; overflow: auto; padding: 24px clamp(16px, 4vw, 48px) 32px; box-sizing: border-box; }
        .page[data-fill='true'] { padding: 0; display: flex; flex-direction: column; overflow: hidden; }
        .page[data-fill='true'] > .content { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; gap: 0; max-width: none; }
        .page[data-fill='true'] .fu-block[data-block-type='conversation'] { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
        .page[data-fill='true'] .fu-block[data-block-type='agent_identity'] {
            position: sticky; top: 0; z-index: 2; flex: none;
            display: flex; justify-content: center;
            padding: 12px max(16px, min(96px, 12vw)) 8px;
            background: color-mix(in srgb, var(--flow-ui-page-background, transparent) 88%, transparent);
            backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
        }
        .page[data-fill='true'] .fu-identity { justify-content: center; }
        /* Пустая лента уже показывает mark в hero — полоса identity не дублирует логотип. */
        :host(:not([editing])) .page[data-fill='true']:has(flow-ui-conversation[data-empty]) .fu-block[data-block-type='agent_identity'] {
            display: none;
        }
        .content { display: grid; gap: var(--flow-ui-space-4); max-width: var(--flow-ui-content-medium, 960px); margin: 0 auto; width: 100%; box-sizing: border-box; }
        /* Холст редактора и live-тест в рамке: страница растёт с блоками, иначе overflow:hidden срезает html/form. */
        :host([editing]), :host([editing]) .page,
        :host([fluid]), :host([fluid]) .page { height: auto; min-height: 0; overflow: visible; flex: none; }
        :host([editing]) .content, :host([fluid]) .content { min-height: 120px; }
        :host([editing]) .page[data-fill='true'],
        :host([fluid]) .page[data-fill='true'] { overflow: visible; }
        :host([editing]) .page[data-fill='true'] > .content,
        :host([fluid]) .page[data-fill='true'] > .content {
            flex: none; min-height: auto; gap: 16px; padding: 8px 16px 20px;
        }
        :host([editing]) .page[data-fill='true'] .fu-block[data-block-type='conversation'],
        :host([fluid]) .page[data-fill='true'] .fu-block[data-block-type='conversation'] {
            flex: none; min-height: 0; height: auto;
        }
        :host([editing]) .page[data-fill='true'] .fu-block[data-block-type='agent_identity'],
        :host([fluid]) .page[data-fill='true'] .fu-block[data-block-type='agent_identity'] { position: relative; }
        h1.page-title { margin: 0 0 8px; font-size: var(--flow-ui-font-size-hero, 22px); font-weight: 650; letter-spacing: -.02em; color: var(--flow-ui-heading); }
    `];

    constructor() {
        super();
        this.host = null;
        this.page = null;
        this.showTitle = false;
        this.editing = false;
        this.fluid = false;
        this.selectedBlockId = '';
        this._unsubscribe = null;
    }

    override connectedCallback() {
        super.connectedCallback();
        this._subscribe();
    }

    override disconnectedCallback() {
        super.disconnectedCallback();
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = null;
    }

    override updated(changed: PropertyValues<this>) {
        if (changed.has('host')) this._subscribe();
    }

    _subscribe() {
        if (this._unsubscribe) this._unsubscribe();
        this._unsubscribe = this.host ? this.host.store.subscribe(() => this.requestUpdate()) : null;
    }

    override render() {
        if (!this.host || !this.page) return nothing;
        const ctx = this.host.blockContext();
        const fill = pageFillsViewport(this.page);
        const title = this.showTitle && this.page.show_title !== false ? (blockText(ctx, this.page.title) ?? '') : '';
        return html`<div class="page" data-page-id=${this.page.page_id} data-fill=${fill ? 'true' : 'false'}>
            <div class="content" data-container-key="page">
                ${title !== '' ? html`<h1 class="page-title">${title}</h1>` : ''}
                ${renderBlocks(this.page.blocks, ctx)}
            </div>
        </div>`;
    }
}

if (!customElements.get('flow-ui-page')) customElements.define('flow-ui-page', FlowUIPage);

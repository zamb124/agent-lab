/** Действия: button (ui-action), link (страница или внешний URL), suggested_prompts (текстовый ход). */

import { html, nothing } from '../../lit-shim.js';
import { blockText as text, blockUrl } from '../runtime/templating.js';


export const ACTION_BLOCKS = Object.freeze({
    button(block, ctx) {
        const label = text(ctx, block.label);
        if (label === null) return nothing;
        const pageId = block.page_id;
        const url = (pageId || block.action) ? null : blockUrl(ctx, block.url);
        return html`<button type="button" class="fu-button" data-variant=${block.variant}
            data-action=${block.action?.name ?? nothing}
            data-page-id=${pageId ?? nothing}
            ?disabled=${ctx.readonly || ctx.pending}
            @click=${() => {
                if (pageId) ctx.onNavigate(pageId);
                else if (url) ctx.onOpenUrl(url);
                else if (block.action) ctx.onAction(block, block.action);
            }}>${label}</button>`;
    },

    link(block, ctx) {
        const label = text(ctx, block.label);
        if (label === null) return nothing;
        if (block.page_id !== null) {
            return html`<button type="button" class="fu-link" data-page-id=${block.page_id}
                @click=${() => ctx.onNavigate(block.page_id)}>${label}</button>`;
        }
        const url = blockUrl(ctx, block.url);
        if (url === null || url === '') return nothing;
        return html`<a class="fu-link" href=${url} target="_blank" rel="noopener noreferrer"
            @click=${(event) => { event.preventDefault(); ctx.onOpenUrl(url); }}>${label}</a>`;
    },

    suggested_prompts(block, ctx) {
        const items = block.items.map((item) => text(ctx, item)).filter((item) => item !== null && item !== '');
        if (items.length === 0) return nothing;
        return html`<div class="fu-prompts">
            ${items.map((item) => html`<button type="button" ?disabled=${ctx.readonly || ctx.pending}
                @click=${() => ctx.onPrompt(item)}>${item}</button>`)}
        </div>`;
    },
});

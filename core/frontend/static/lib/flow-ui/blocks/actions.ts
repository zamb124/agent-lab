/** Действия: button (ui-action), link (страница или внешний URL), suggested_prompts (текстовый ход). */

import { html, nothing } from '../../lit-shim.js';
import { isPlainRecord } from '../../events/payload.js';
import { blockText as text, blockUrl } from '../runtime/templating.js';
import type { FlowUiBlockRenderer } from '../runtime/flow-ui-store.js';

function buttonActionName(action: unknown): string | null {
    if (!isPlainRecord(action)) return null;
    const name = action.name;
    return typeof name === 'string' ? name : null;
}


export const ACTION_BLOCKS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    button(block, ctx) {
        const label = text(ctx, block.label);
        if (label === null) return nothing;
        const pageId = block.page_id;
        const url = (pageId || block.action) ? null : blockUrl(ctx, block.url);
        return html`<button type="button" class="fu-button" data-variant=${block.variant}
            data-action=${buttonActionName(block.action) ?? nothing}
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
            @click=${(event: Event) => { event.preventDefault(); ctx.onOpenUrl(url); }}>${label}</a>`;
    },

    suggested_prompts(block, ctx) {
        const items = (Array.isArray(block.items) ? block.items : [])
            .map((item: unknown) => text(ctx, item))
            .filter((item: string | null): item is string => item !== null && item !== '');
        if (items.length === 0) return nothing;
        return html`<div class="fu-prompts">
            ${items.map((item) => html`<button type="button" ?disabled=${ctx.readonly || ctx.pending}
                @click=${() => ctx.onPrompt(item)}>${item}</button>`)}
        </div>`;
    },
});

/**
 * Контейнеры: section, columns, tabs. Вложенные блоки — через ``ctx.renderBlocks``.
 * ``data-container-key`` (``<block_id>`` | ``<block_id>/<index>``) — адрес контейнера для drop-зон редактора.
 */

import { html } from '../../lit-shim.js';
import { blockText as text } from '../runtime/templating.js';
import { flowUIText } from '../utils/text.js';
import type { FlowUiBlock, FlowUiBlockRenderer, FlowUiRenderContext } from '../runtime/flow-ui-store.js';

function containerChildren(ctx: FlowUiRenderContext, blocks: unknown) {
    if (ctx.editing === true && Array.isArray(blocks) && blocks.length === 0) {
        return html`<div class="fu-container-empty">${flowUIText(ctx.locale, 'drop_block_here')}</div>`;
    }
    return ctx.renderBlocks?.(blocks);
}

interface FlowUiColumn extends FlowUiBlock {
    width?: unknown;
}

interface FlowUiTab extends FlowUiBlock {
    title?: unknown;
}

function columnsOf(block: FlowUiBlock): FlowUiColumn[] {
    return Array.isArray(block.columns) ? block.columns as FlowUiColumn[] : [];
}

function tabsOf(block: FlowUiBlock): FlowUiTab[] {
    return Array.isArray(block.tabs) ? block.tabs as FlowUiTab[] : [];
}

export const LAYOUT_BLOCKS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    section(block, ctx) {
        const title = text(ctx, block.title);
        return html`<section class="fu-section" data-container-key=${block.block_id}>
            ${title ? html`<h3>${title}</h3>` : ''}
            ${containerChildren(ctx, block.blocks)}
        </section>`;
    },

    columns(block, ctx) {
        const columns = columnsOf(block);
        const template = columns.map((column) => `${column.width}fr`).join(' ');
        return html`<div class="fu-columns" style=${`--fu-columns:${template}`}>
            ${columns.map((column, index) => html`<div class="fu-column" data-container-key=${`${block.block_id}/${index}`}>${containerChildren(ctx, column.blocks)}</div>`)}
        </div>`;
    },

    tabs(block, ctx) {
        const tabs = tabsOf(block);
        const local = ctx.store.localState(String(block.block_id));
        const active = Math.min(typeof local.tab === 'number' ? local.tab : 0, Math.max(tabs.length - 1, 0));
        const select = (index: number) => {
            local.tab = index;
            ctx.requestUpdate();
        };
        return html`<div class="fu-tabs">
            <nav role="tablist">
                ${tabs.map((tab, index) => html`<button
                    type="button" role="tab"
                    aria-selected=${index === active ? 'true' : 'false'}
                    data-tab-index=${index}
                    @click=${() => select(index)}
                >${text(ctx, tab.title) ?? ''}</button>`)}
            </nav>
            ${tabs.length > 0
                ? html`<div class="fu-tab-panel" role="tabpanel" data-container-key=${`${block.block_id}/${active}`}>${containerChildren(ctx, tabs[active]?.blocks)}</div>`
                : ''}
        </div>`;
    },
});

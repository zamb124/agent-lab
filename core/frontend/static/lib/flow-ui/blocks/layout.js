/**
 * Контейнеры: section, columns, tabs. Вложенные блоки — через ``ctx.renderBlocks``.
 * ``data-container-key`` (``<block_id>`` | ``<block_id>/<index>``) — адрес контейнера для drop-зон редактора.
 */

import { html } from '../../lit-shim.js';
import { blockText as text } from '../runtime/templating.js';


export const LAYOUT_BLOCKS = Object.freeze({
    section(block, ctx) {
        const title = text(ctx, block.title);
        return html`<section class="fu-section" data-container-key=${block.block_id}>
            ${title ? html`<h3>${title}</h3>` : ''}
            ${ctx.renderBlocks(block.blocks)}
        </section>`;
    },

    columns(block, ctx) {
        const template = block.columns.map((column) => `${column.width}fr`).join(' ');
        return html`<div class="fu-columns" style=${`--fu-columns:${template}`}>
            ${block.columns.map((column, index) => html`<div class="fu-column" data-container-key=${`${block.block_id}/${index}`}>${ctx.renderBlocks(column.blocks)}</div>`)}
        </div>`;
    },

    tabs(block, ctx) {
        const local = ctx.store.localState(block.block_id);
        const active = Math.min(typeof local.tab === 'number' ? local.tab : 0, Math.max(block.tabs.length - 1, 0));
        const select = (index) => {
            local.tab = index;
            ctx.requestUpdate();
        };
        return html`<div class="fu-tabs">
            <nav role="tablist">
                ${block.tabs.map((tab, index) => html`<button
                    type="button" role="tab"
                    aria-selected=${index === active ? 'true' : 'false'}
                    data-tab-index=${index}
                    @click=${() => select(index)}
                >${text(ctx, tab.title) ?? ''}</button>`)}
            </nav>
            ${block.tabs.length > 0
                ? html`<div class="fu-tab-panel" role="tabpanel" data-container-key=${`${block.block_id}/${active}`}>${ctx.renderBlocks(block.tabs[active].blocks)}</div>`
                : ''}
        </div>`;
    },
});

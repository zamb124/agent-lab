/**
 * Контейнеры: section, columns, tabs. Вложенные блоки — через ``ctx.renderBlocks``.
 * ``data-container-key`` (``<block_id>`` | ``<block_id>/<index>``) — адрес контейнера для drop-зон редактора.
 */

import { isPlainRecord } from '../../events/payload.js';
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

interface FlowUiColumn {
    width?: unknown;
    blocks?: unknown;
}

interface FlowUiTab {
    title?: unknown;
    blocks?: unknown;
}

function unknownItems(value: unknown, label: string): unknown[] {
    if (!Array.isArray(value)) {
        throw new Error(`flow-ui: ${label} must be an array`);
    }
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

function isColumn(value: unknown): value is FlowUiColumn {
    return isPlainRecord(value);
}

function isTab(value: unknown): value is FlowUiTab {
    return isPlainRecord(value);
}

function columnsOf(block: FlowUiBlock): FlowUiColumn[] {
    const columns: FlowUiColumn[] = [];
    for (const item of unknownItems(block.columns, 'columns')) {
        if (!isColumn(item)) {
            throw new Error('flow-ui: columns item must be an object');
        }
        columns.push(item);
    }
    return columns;
}

function tabsOf(block: FlowUiBlock): FlowUiTab[] {
    const tabs: FlowUiTab[] = [];
    for (const item of unknownItems(block.tabs, 'tabs')) {
        if (!isTab(item)) {
            throw new Error('flow-ui: tabs item must be an object');
        }
        tabs.push(item);
    }
    return tabs;
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
                ${tabs.map((tab, index) => {
                    const title = text(ctx, tab.title);
                    return html`<button
                        type="button" role="tab"
                        aria-selected=${index === active ? 'true' : 'false'}
                        data-tab-index=${index}
                        @click=${() => select(index)}
                    >${title === null ? '' : title}</button>`;
                })}
            </nav>
            ${tabs.length > 0
                ? html`<div class="fu-tab-panel" role="tabpanel" data-container-key=${`${block.block_id}/${active}`}>${containerChildren(ctx, tabs[active]?.blocks)}</div>`
                : ''}
        </div>`;
    },
});

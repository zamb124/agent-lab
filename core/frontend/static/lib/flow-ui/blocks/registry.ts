/**
 * Реестр рендереров блоков: ключ == ``type`` грамматики ``core/flow_ui/document.py``
 * (гейт ``check_flow_ui_hard_cut``). Каждый рендерер — ``(block, ctx) => TemplateResult``.
 *
 * ``ctx``: ``state`` (проекция), ``locale``, ``readonly``, ``platformUiOrigin``, ``theme``,
 * ``fieldValue(field)``, ``onFieldChange(field, value)``, ``onAction(block, action)``,
 * ``onNavigate(page_id)``, ``onOpenUrl(url)``, ``slots``, ``turns``, ``host`` (platform-flow-ui),
 * ``store`` (``fieldErrors``/``uploading``/``localState(block_id)``), ``requestUpdate()`` — перерисовка
 * страницы через store, ``renderBlocks(blocks)`` для вложенных блоков; ``editing`` — редактор
 * (клики не отправляют действия).
 *
 * Ошибка рендерера (например, URL медиа без схемы или с неразрешённым шаблоном) остаётся внутри
 * блока: обёртка ``.fu-block`` с текстом ошибки, остальная страница рендерится. Блок без данных
 * в рантайме не рендерится, а на холсте показывает заглушку — иначе автор не смог бы его выбрать.
 */

import { html, nothing } from '../../lit-shim.js';
import { isVisible } from '../runtime/templating.js';
import type { FlowUiBlock, FlowUiBlockRenderer, FlowUiRenderContext } from '../runtime/flow-ui-store.js';
import { flowUIText } from '../utils/text.js';
import { ACTION_BLOCKS } from './actions.js';
import { CONTENT_BLOCKS } from './content.js';
import { DATA_BLOCKS } from './data.js';
import { HTML_BLOCKS } from './html.js';
import { INPUT_BLOCKS } from './inputs.js';
import { LAYOUT_BLOCKS } from './layout.js';
import { PLATFORM_BLOCKS } from './platform.js';

/** Стили блоков (``blocks/block.styles.js``); подключаются в shadow root страницы и ленты. */
export { blockStyles } from './block.styles.js';

export const FLOW_UI_BLOCK_RENDERERS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    ...LAYOUT_BLOCKS,
    ...CONTENT_BLOCKS,
    ...INPUT_BLOCKS,
    ...ACTION_BLOCKS,
    ...DATA_BLOCKS,
    ...PLATFORM_BLOCKS,
    ...HTML_BLOCKS,
});

export function renderBlock(block: FlowUiBlock, ctx: FlowUiRenderContext) {
    if (!block || typeof block !== 'object' || typeof block.type !== 'string') {
        throw new Error('flow-ui: block requires type');
    }
    const renderer = FLOW_UI_BLOCK_RENDERERS[block.type];
    if (!renderer) throw new Error(`flow-ui: unknown block type ${JSON.stringify(block.type)}`);
    if (!ctx.editing && !isVisible(block.visible_when as { path?: unknown; equals?: unknown } | null | undefined, ctx.state)) return nothing;
    let content;
    let renderError = null;
    try {
        content = renderer(block, ctx);
    } catch (error) {
        renderError = error instanceof Error ? error.message : String(error);
        content = html`<div class="fu-block-error" role="alert">${renderError}</div>`;
    }
    if (content === nothing || content === null) {
        if (!ctx.editing) return nothing;
        content = html`<div class="fu-block-empty">${flowUIText(ctx.locale, 'block_empty', { type: block.type })}</div>`;
    }
    const span = Number.isInteger(block.span) && (block.span as number) >= 1 && (block.span as number) <= 12 ? block.span as number : 12;
    const align = block.align === 'center' || block.align === 'end' ? block.align : 'start';
    const valign = block.valign === 'center' || block.valign === 'end' ? block.valign : 'start';
    return html`<div
        class="fu-block"
        style=${`--fu-span:${span}`}
        data-block-id=${block.block_id}
        data-block-type=${block.type}
        data-span=${span}
        data-align=${align}
        data-valign=${valign}
        data-selected=${ctx.selectedBlockId === block.block_id ? 'true' : nothing}
        data-render-error=${renderError !== null ? 'true' : nothing}
    >${content}</div>`;
}

export function renderBlocks(blocks: unknown, ctx: FlowUiRenderContext) {
    const scoped: FlowUiRenderContext = ctx.renderBlocks ? ctx : { ...ctx, renderBlocks: (children: unknown) => renderBlocks(children, scoped) };
    return (Array.isArray(blocks) ? blocks : []).map((block) => renderBlock(block, scoped));
}

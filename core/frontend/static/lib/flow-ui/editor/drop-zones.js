/**
 * Drop-зоны редактора: поточная раскладка, вставка только между блоками контейнера.
 * Цель вычисляется из composed path drag-события и геометрии прямых детей контейнера,
 * без внедрения узлов в shadow DOM страницы.
 */

import { containerFromPath, relativeRect } from './selection.js';

export const BLOCK_TYPE_MIME = 'application/x-flow-ui-block';
export const BLOCK_ID_MIME = 'application/x-flow-ui-block-id';

/** Прямые дети-блоки контейнера; перетаскиваемый блок исключается из расчёта позиции. */
function containerChildren(element, excludeBlockId) {
    return [...element.children].filter((child) => child.classList.contains('fu-block') && child.dataset.blockId !== excludeBlockId);
}

function insideBlock(element, blockId) {
    return blockId !== null && element.closest(`.fu-block[data-block-id="${blockId}"]`) !== null;
}

/**
 * @returns {{ containerKey: string, index: number, indicator: {top, left, width} } | null}
 * ``indicator`` — горизонтальная линия вставки относительно ``origin``.
 */
export function dropTargetFromEvent(event, origin, excludeBlockId = null) {
    const container = containerFromPath(event.composedPath());
    if (container === null || insideBlock(container.element, excludeBlockId)) return null;
    const children = containerChildren(container.element, excludeBlockId);
    let index = 0;
    for (const child of children) {
        const rect = child.getBoundingClientRect();
        if (event.clientY > rect.top + rect.height / 2) index += 1;
    }
    const containerRect = container.element.getBoundingClientRect();
    let lineTop;
    if (children.length === 0) {
        lineTop = containerRect.top + Math.min(12, containerRect.height / 2);
    } else if (index < children.length) {
        const rect = children[index].getBoundingClientRect();
        const previous = index > 0 ? children[index - 1].getBoundingClientRect().bottom : rect.top;
        lineTop = (previous + rect.top) / 2;
    } else {
        lineTop = children[children.length - 1].getBoundingClientRect().bottom + 4;
    }
    const line = relativeRect({ top: lineTop, left: containerRect.left, width: containerRect.width, height: 0 }, origin);
    return {
        containerKey: container.key,
        index: excludeBlockId === null ? index : indexIncludingExcluded(container.element, children, index, excludeBlockId),
        indicator: { top: line.top, left: line.left, width: line.width },
    };
}

/** Индекс в реальном массиве контейнера, где перетаскиваемый блок ещё присутствует. */
function indexIncludingExcluded(element, visibleChildren, index, excludeBlockId) {
    const all = [...element.children].filter((child) => child.classList.contains('fu-block'));
    if (index >= visibleChildren.length) return all.length;
    return all.indexOf(visibleChildren[index]);
}

export function readDragPayload(dataTransfer) {
    const blockId = dataTransfer.getData(BLOCK_ID_MIME);
    if (blockId !== '') return { kind: 'move', blockId };
    const raw = dataTransfer.getData(BLOCK_TYPE_MIME);
    if (raw === '') return null;
    const payload = JSON.parse(raw);
    if (typeof payload.type !== 'string') throw new Error('flow-ui editor: drag payload requires type');
    return { kind: 'insert', type: payload.type, columns: typeof payload.columns === 'number' ? payload.columns : null };
}

export function hasFlowUiDrag(dataTransfer) {
    return [...dataTransfer.types].some((type) => type === BLOCK_TYPE_MIME || type === BLOCK_ID_MIME);
}

/**
 * Выбор блока на холсте редактора: hit-testing сквозь shadow DOM ``<platform-flow-ui editing>``
 * по ``event.composedPath()`` и поиск DOM-узлов блоков для рамки выделения.
 */

function isElement(node) {
    return node instanceof Element;
}

/** Ближайший к цели элемент блока (``.fu-block[data-block-id]``) в composed path. */
export function blockElementFromPath(path) {
    for (const node of path) {
        if (isElement(node) && node.classList.contains('fu-block') && typeof node.dataset.blockId === 'string') return node;
    }
    return null;
}

export function blockIdFromEvent(event) {
    const element = blockElementFromPath(event.composedPath());
    return element === null ? null : element.dataset.blockId;
}

/** Ближайший контейнер (``[data-container-key]``) в composed path: ``{key, element}``. */
export function containerFromPath(path) {
    for (const node of path) {
        if (isElement(node) && typeof node.dataset.containerKey === 'string') return { key: node.dataset.containerKey, element: node };
    }
    return null;
}

/** Shadow root страницы внутри ``<platform-flow-ui>``: там живут узлы блоков. */
export function pageRenderRoot(flowUiElement) {
    if (!flowUiElement || !flowUiElement.shadowRoot) return null;
    const page = flowUiElement.shadowRoot.querySelector('flow-ui-page');
    return page && page.shadowRoot ? page.shadowRoot : null;
}

export function blockElement(flowUiElement, blockId) {
    const root = pageRenderRoot(flowUiElement);
    if (root === null || typeof blockId !== 'string' || blockId === '') return null;
    return root.querySelector(`.fu-block[data-block-id="${blockId}"]`);
}

/** Прямоугольник блока относительно ``origin`` (контейнер холста с ``position: relative``). */
export function blockFrame(flowUiElement, blockId, origin) {
    const element = blockElement(flowUiElement, blockId);
    if (element === null) return null;
    return relativeRect(element.getBoundingClientRect(), origin);
}

export function relativeRect(rect, origin) {
    const base = origin.getBoundingClientRect();
    return {
        top: rect.top - base.top + origin.scrollTop,
        left: rect.left - base.left + origin.scrollLeft,
        width: rect.width,
        height: rect.height,
    };
}

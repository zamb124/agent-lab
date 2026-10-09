/**
 * Выбор блока на холсте редактора: hit-testing сквозь shadow DOM ``<platform-flow-ui editing>``
 * по ``event.composedPath()`` и поиск DOM-узлов блоков для рамки выделения.
 */

function isElement(node: unknown): node is Element {
    return node instanceof Element;
}

/** Ближайший к цели элемент блока (``.fu-block[data-block-id]``) в composed path. */
export function blockElementFromPath(path: readonly EventTarget[]): HTMLElement | null {
    for (const node of path) {
        if (isElement(node) && node.classList.contains('fu-block') && typeof (node as HTMLElement).dataset.blockId === 'string') return node as HTMLElement;
    }
    return null;
}

export function blockIdFromEvent(event: Event): string | null {
    const element = blockElementFromPath(event.composedPath());
    return element === null ? null : element.dataset.blockId ?? null;
}

/** Ближайший контейнер (``[data-container-key]``) в composed path: ``{key, element}``. */
export function containerFromPath(path: readonly EventTarget[]): { key: string; element: Element } | null {
    for (const node of path) {
        if (isElement(node) && typeof (node as HTMLElement).dataset.containerKey === 'string') return { key: (node as HTMLElement).dataset.containerKey as string, element: node };
    }
    return null;
}

/** Shadow root страницы внутри ``<platform-flow-ui>``: там живут узлы блоков. */
export function pageRenderRoot(flowUiElement: { shadowRoot?: ShadowRoot | null } | null | undefined): ShadowRoot | null {
    if (!flowUiElement || !flowUiElement.shadowRoot) return null;
    const page = flowUiElement.shadowRoot.querySelector('flow-ui-page');
    return page && page.shadowRoot ? page.shadowRoot : null;
}

export function blockElement(flowUiElement: { shadowRoot?: ShadowRoot | null } | null | undefined, blockId: unknown): Element | null {
    const root = pageRenderRoot(flowUiElement);
    if (root === null || typeof blockId !== 'string' || blockId === '') return null;
    return root.querySelector(`.fu-block[data-block-id="${blockId}"]`);
}

/** Прямоугольник блока относительно ``origin`` (контейнер холста с ``position: relative``). */
export function blockFrame(flowUiElement: { shadowRoot?: ShadowRoot | null } | null | undefined, blockId: unknown, origin: Element) {
    const element = blockElement(flowUiElement, blockId);
    if (element === null) return null;
    return relativeRect(element.getBoundingClientRect(), origin);
}

export function relativeRect(rect: { top: number; left: number; width: number; height: number }, origin: Element) {
    const base = origin.getBoundingClientRect();
    return {
        top: rect.top - base.top + origin.scrollTop,
        left: rect.left - base.left + origin.scrollLeft,
        width: rect.width,
        height: rect.height,
    };
}

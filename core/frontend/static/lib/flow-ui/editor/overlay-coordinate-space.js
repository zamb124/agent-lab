export function framePointFromOverlay({ x, y }, frameRect, zoom = 1) {
    if (!(zoom > 0)) throw new Error('flow-ui overlay zoom must be positive');
    return Object.freeze({ x: (x - frameRect.left) / zoom, y: (y - frameRect.top) / zoom });
}

export function overlayRectFromFrame(rect, frameRect, zoom = 1) {
    return Object.freeze({
        x: frameRect.left + rect.x * zoom, y: frameRect.top + rect.y * zoom,
        width: rect.width * zoom, height: rect.height * zoom,
    });
}

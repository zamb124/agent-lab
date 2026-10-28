/**
 * Fail-closed lookup test-run хендлера Play по nodeType / resourceType.
 * Не фабрика: без slice и транспорта.
 */

const _handlers: any[] = [];

export function registerNodeTestRunHandler(handler: any) {
    if (!handler || typeof handler !== 'object') {
        throw new Error('node-test-run-registry: handler object required');
    }
    if (typeof handler.id !== 'string' || handler.id.length === 0) {
        throw new Error('node-test-run-registry: handler.id required');
    }
    if (typeof handler.match !== 'function') {
        throw new Error(`node-test-run-registry: handler ${handler.id} match required`);
    }
    if (typeof handler.opName !== 'string' || handler.opName.length === 0) {
        throw new Error(`node-test-run-registry: handler ${handler.id} opName required`);
    }
    if (typeof handler.run !== 'function') {
        throw new Error(`node-test-run-registry: handler ${handler.id} run required`);
    }
    if (typeof handler.formatViewModel !== 'function') {
        throw new Error(`node-test-run-registry: handler ${handler.id} formatViewModel required`);
    }
    if (typeof handler.busyOf !== 'function') {
        throw new Error(`node-test-run-registry: handler ${handler.id} busyOf required`);
    }
    if (_handlers.some((item) => item.id === handler.id)) {
        throw new Error(`node-test-run-registry: duplicate handler id ${handler.id}`);
    }
    _handlers.push(handler);
}

export function listNodeTestRunHandlers() {
    return _handlers.slice();
}

export function findNodeTestRunHandlers(ctx: any) {
    if (!ctx || typeof ctx !== 'object') {
        throw new Error('node-test-run-registry: match ctx object required');
    }
    if (typeof ctx.nodeType !== 'string' || ctx.nodeType.length === 0) {
        throw new Error('node-test-run-registry: ctx.nodeType required');
    }
    return _handlers.filter((handler) => handler.match(ctx) === true);
}

export function resolveNodeTestRunHandler(ctx: any) {
    const matches = findNodeTestRunHandlers(ctx);
    if (matches.length !== 1) {
        const resourceType = typeof ctx.resourceType === 'string' ? ctx.resourceType : '';
        throw new Error(
            `node-test-run-registry: expected exactly 1 handler, got ${matches.length} `
            + `for nodeType=${ctx.nodeType} resourceType=${resourceType}`,
        );
    }
    return matches[0];
}

export function clearNodeTestRunHandlersForTests() {
    _handlers.length = 0;
}

import { cloneSerializable } from '../utils/clone.js';

function decodeSegment(value) {
    return value.replace(/~1/g, '/').replace(/~0/g, '~');
}

export function getPointer(root, path) {
    if (!path || path === '/') return root;
    let value = root;
    for (const segment of path.slice(1).split('/').map(decodeSegment)) {
        if (value == null || typeof value !== 'object') return undefined;
        value = value[segment];
    }
    return value;
}

export function setPointer(root, path, value) {
    if (!path.startsWith('/values/') && path !== '/values') {
        throw new Error(`flow-ui: browser may only write /values, received ${path}`);
    }
    const result = cloneSerializable(root || {});
    const parts = path.slice(1).split('/').map(decodeSegment);
    let target = result;
    for (let index = 0; index < parts.length - 1; index += 1) {
        const key = parts[index];
        if (!target[key] || typeof target[key] !== 'object') target[key] = {};
        target = target[key];
    }
    target[parts[parts.length - 1]] = cloneSerializable(value);
    return result;
}

export function surfaceValues(document) {
    return Object.fromEntries(Object.entries(document?.surfaces || {}).map(([id, surface]) => [
        id, cloneSerializable(surface?.data_model?.values || {}),
    ]));
}

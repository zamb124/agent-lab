import { FLOW_UI_CATALOG_MANIFEST } from './manifest.js';

const renderers = new Map();

export function registerFlowUIComponent(type, renderer) {
    if (!FLOW_UI_CATALOG_MANIFEST.components[type]) throw new Error(`flow-ui: ${type} is not in the trusted catalog`);
    if (typeof renderer !== 'function') throw new Error('flow-ui: renderer must be a function');
    renderers.set(type, renderer);
}

export function flowUIComponentRenderer(type) {
    return renderers.get(type) || null;
}

export function flowUIComponentDefinition(type) {
    return FLOW_UI_CATALOG_MANIFEST.components[type] || null;
}

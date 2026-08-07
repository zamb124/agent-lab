import { html } from '../../../lit-shim.js';
import {
    localizedText,
    optionalComponentProperty,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';

export function renderText(host, component) {
    const value = resolveBound(host.surface, component, 'text', host.tasks)
        ?? optionalComponentProperty(component, 'text');
    return wrapFlowNode(host, component, html`<p>${localizedText(value)}</p>`);
}

export function renderDivider(host, component) {
    return wrapFlowNode(host, component, html`<div class="divider" role="separator"></div>`);
}

export function registerBasicText(register) {
    register('Text', renderText);
    register('Divider', renderDivider);
}

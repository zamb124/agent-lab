import { html } from '../../../lit-shim.js';
import { renderChildren, wrapFlowNode } from '../render-helpers.js';

function container(host, component, tag, className) {
    return wrapFlowNode(host, component, renderChildren(host, component), {
        surfaceTag: tag,
        surfaceClass: className,
    });
}

export function renderRow(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderColumn(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderList(host, component) {
    return wrapFlowNode(host, component, html`${renderChildren(host, component)}`);
}

export function renderCard(host, component) {
    return container(host, component, 'article', 'card');
}

export function registerBasicLayout(register) {
    register('Row', renderRow);
    register('Column', renderColumn);
    register('List', renderList);
    register('Card', renderCard);
}

import { html } from '../../../lit-shim.js';
import {
    localizedText,
    optionalComponentProperty,
    renderSanitizedMarkdown,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';

export function renderHeading(host, component) {
    const value = resolveBound(host.surface, component, 'text', host.tasks)
        ?? optionalComponentProperty(component, 'text')
        ?? optionalComponentProperty(component, 'title');
    const text = localizedText(value);
    const level = Number(optionalComponentProperty(component, 'level') ?? 2);
    if (level === 1) return wrapFlowNode(host, component, html`<h1>${text}</h1>`);
    if (level === 3) return wrapFlowNode(host, component, html`<h3>${text}</h3>`);
    if (level === 4) return wrapFlowNode(host, component, html`<h4>${text}</h4>`);
    return wrapFlowNode(host, component, html`<h2>${text}</h2>`);
}

export function renderMarkdown(host, component) {
    const content = resolveBound(host.surface, component, 'content', host.tasks)
        ?? optionalComponentProperty(component, 'content');
    return wrapFlowNode(
        host,
        component,
        html`<div class="part-text">${renderSanitizedMarkdown(content)}</div>`,
    );
}

export function renderCodeBlock(host, component) {
    const code = resolveBound(host.surface, component, 'code', host.tasks)
        ?? optionalComponentProperty(component, 'code');
    return wrapFlowNode(host, component, html`<pre>${code == null ? '' : String(code)}</pre>`);
}

export function registerPlatformText(register) {
    register('Heading', renderHeading);
    register('Markdown', renderMarkdown);
    register('CodeBlock', renderCodeBlock);
}

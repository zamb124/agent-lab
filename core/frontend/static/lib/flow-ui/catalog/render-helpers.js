/**
 * Shared helpers for Flow UI catalog renderers.
 * Missing bindings/properties fail closed — no silent defaults for required values.
 */

import { html, nothing } from '../../lit-shim.js';
import { getPointer } from '../runtime/flow-ui-actions.js';
import { containerLayoutStyle, gridRowCount, placementStyle } from '../layout/layout-resolver.js';
import { projectA2AArtifact } from '../protocol/generic-part-projector.js';
import { flowUIText } from '../utils/text.js';

export function requireComponentProperty(component, name) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui: component is required');
    }
    if (!(name in (component.properties || {}))) {
        throw new Error(`flow-ui: component ${component.component_id} missing property ${name}`);
    }
    return component.properties[name];
}

export function optionalComponentProperty(component, name) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui: component is required');
    }
    if (!component.properties || !(name in component.properties)) {
        return undefined;
    }
    return component.properties[name];
}

export function localizedText(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'object' && typeof value.default === 'string') return value.default;
    throw new Error('flow-ui: localized text must be a string or {default}');
}

export function resolveBound(surface, component, name, tasks) {
    const path = component?.bindings?.[name];
    if (!path) {
        return optionalComponentProperty(component, name);
    }
    if (path === '/system/tasks') return tasks;
    if (path === '/system/activeTask') {
        if (!Array.isArray(tasks) || tasks.length === 0) return null;
        return tasks[tasks.length - 1];
    }
    return getPointer(surface.data_model, path);
}

export function componentHasRequiredCheck(component) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui: component is required');
    }
    return (Array.isArray(component.checks) ? component.checks : [])
        .some((check) => check && check.function === 'required');
}

export function componentFieldError(host, component) {
    if (!component || typeof component !== 'object') {
        throw new Error('flow-ui: component is required');
    }
    const errors = host?.controller?.fieldErrors;
    if (!errors || typeof errors !== 'object') return '';
    const message = errors[component.component_id];
    return typeof message === 'string' ? message : '';
}

export function renderInputLabelText(host, component, label) {
    // Must be one DOM node: parent `label { display: grid }` would otherwise
    // put the required asterisk on its own row between caption and control.
    if (!componentHasRequiredCheck(component)) {
        return html`<span class="field-label">${label}</span>`;
    }
    return html`<span class="field-label">${label}<span class="field-required" aria-hidden="true">*</span></span>`;
}

export function renderFieldError(host, component) {
    const message = componentFieldError(host, component);
    if (message === '') return nothing;
    return html`<span class="field-error" role="alert">${message}</span>`;
}

export function wrapFlowNode(host, component, content, options = {}) {
    // Composer Form synthesizes a pill from children and does not place them in its
    // own CSS grid. Applying container_layout here would reserve empty rows for
    // file-upload / message-input / submit and inflate the selection box.
    const applyContainerLayout = options.applyContainerLayout !== false;
    const layout = applyContainerLayout
        ? containerLayoutStyle(
            component.container_layout,
            gridRowCount(component, host?.surface?.components),
        )
        : '';
    const extraClass = typeof options.extraClass === 'string' ? options.extraClass.trim() : '';
    const isGrid = applyContainerLayout && component.container_layout?.mode === 'grid';
    // The layout must sit on the element that directly holds the children. A visual
    // surface (card, section, field group) is that element, so it carries the grid and
    // the outer node only carries placement — otherwise the children would stack as
    // blocks while the outer grid reserved empty rows for them.
    const surfaceClass = typeof options.surfaceClass === 'string' ? options.surfaceClass.trim() : '';
    const classes = [
        'flow-node',
        isGrid && surfaceClass === '' ? 'flow-grid' : '',
        extraClass,
    ].filter(Boolean).join(' ');
    const placement = component.placement != null && typeof component.placement === 'object'
        ? component.placement
        : { base: {}, overrides: {} };
    const nodeStyle = surfaceClass === ''
        ? (layout === '' ? placementStyle(placement) : `${placementStyle(placement)};${layout}`)
        : placementStyle(placement);
    return html`<div
        class=${classes}
        style=${nodeStyle}
        data-flow-ui-component=${component.component_id}
        data-flow-ui-type=${component.type}
        data-selected=${host.selectedComponentId === component.component_id ? 'true' : 'false'}
    >${surfaceClass === '' ? content : renderFlowSurface(options, layout, isGrid, content)}</div>`;
}

/** Visual surface of a container: it owns the grid its children live in. */
function renderFlowSurface(options, layout, isGrid, content) {
    const className = [options.surfaceClass, isGrid ? 'flow-grid' : ''].filter(Boolean).join(' ');
    const role = typeof options.surfaceRole === 'string' ? options.surfaceRole : nothing;
    if (options.surfaceTag === 'section') {
        return html`<section class=${className} style=${layout} role=${role}>${content}</section>`;
    }
    if (options.surfaceTag === 'article') {
        return html`<article class=${className} style=${layout} role=${role}>${content}</article>`;
    }
    return html`<div class=${className} style=${layout} role=${role}>${content}</div>`;
}

export function renderChildren(host, component) {
    return (component.children || [])
        .map((id) => host._component(host.surface.components[id]))
        .filter((node) => node !== nothing && node != null);
}

export function unknownExternalComponent(host, component) {
    return wrapFlowNode(
        host,
        component,
        html`<div class="unknown" role="note">
            <strong>${component.type || flowUIText(host.locale, 'unknown_component')}</strong>
            <div>${flowUIText(host.locale, 'unknown_component')} · ${component.component_id}</div>
            ${renderChildren(host, component)}
        </div>`,
    );
}

/**
 * Generic trusted projection of one ordinary A2A Artifact:
 * text → text, file → link/name card, data → JSON tree, raw → media label.
 */
export function renderProjectedArtifactCard(locale, artifact) {
    const projected = projectA2AArtifact(artifact);
    return html`<article class="artifact-card">
        ${(projected.name || projected.description) ? html`<div>
            <div class="artifact-title">${projected.name || flowUIText(locale, 'artifact')}</div>
            ${projected.description ? html`<div class="muted">${projected.description}</div>` : nothing}
        </div>` : nothing}
        ${projected.parts.map((part) => {
            if (part.kind === 'text') return html`<div class="part-text">${part.text}</div>`;
            if (part.kind === 'file') {
                return html`<div class="file">${part.url
                    ? html`<a href=${part.url} target="_blank" rel="noopener">${part.filename || part.url}</a>`
                    : (part.filename || flowUIText(locale, 'binary_file'))}</div>`;
            }
            if (part.kind === 'data') return html`<pre>${JSON.stringify(part.data, null, 2)}</pre>`;
            if (part.kind === 'raw') return html`<div class="file">${flowUIText(locale, 'binary_data')} · ${part.mediaType}</div>`;
            throw new Error(`flow-ui: unsupported projected part kind ${part.kind}`);
        })}
    </article>`;
}

/**
 * Safe Markdown: no raw HTML. Supports paragraphs, line breaks, `code`, **bold**.
 * @param {unknown} source
 */
export function renderSanitizedMarkdown(source) {
    const text = source == null ? '' : String(source);
    const blocks = text.split(/\n{2,}/);
    return html`${blocks.map((block) => {
        const lines = block.split('\n');
        return html`<p>${lines.map((line, index) => html`${_inlineMarkdown(line)}${index < lines.length - 1 ? html`<br>` : nothing}`)}</p>`;
    })}`;
}

function _inlineMarkdown(line) {
    const parts = [];
    const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    let match = pattern.exec(line);
    while (match) {
        if (match.index > last) parts.push(line.slice(last, match.index));
        const token = match[0];
        if (token.startsWith('**')) {
            parts.push(html`<strong>${token.slice(2, -2)}</strong>`);
        } else {
            parts.push(html`<code>${token.slice(1, -1)}</code>`);
        }
        last = match.index + token.length;
        match = pattern.exec(line);
    }
    if (last < line.length) parts.push(line.slice(last));
    return parts.length ? parts : line;
}

export function labelOfComponent(host, component) {
    const bound = resolveBound(host.surface, component, 'label', host.tasks);
    if (bound === undefined) {
        const title = optionalComponentProperty(component, 'title');
        return title === undefined ? '' : localizedText(title);
    }
    return localizedText(bound);
}

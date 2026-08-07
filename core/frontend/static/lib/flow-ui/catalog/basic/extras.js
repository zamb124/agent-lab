import { html, nothing } from '../../../lit-shim.js';
import { flowUIGlyph } from '../flow-ui-glyph.js';
import {
    localizedText,
    optionalComponentProperty,
    renderChildren,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import { flowUIText } from '../../utils/text.js';

function labelOf(host, component) {
    const bound = resolveBound(host.surface, component, 'label', host.tasks);
    if (bound === undefined) return '';
    return localizedText(bound);
}

export function renderIcon(host, component) {
    const name = optionalComponentProperty(component, 'name')
        ?? resolveBound(host.surface, component, 'name', host.tasks);
    if (name == null || String(name).trim() === '') {
        throw new Error(`flow-ui: Icon ${component.component_id} requires name`);
    }
    const label = labelOf(host, component) || String(name);
    return wrapFlowNode(
        host,
        component,
        html`<span class="flow-ui-icon" role="img" aria-label=${label}>
            ${flowUIGlyph(String(name).trim(), 20)}
        </span>`,
    );
}

export function renderTabs(host, component) {
    const tabs = resolveBound(host.surface, component, 'tabs', host.tasks)
        ?? optionalComponentProperty(component, 'tabs')
        ?? [];
    if (!Array.isArray(tabs)) {
        throw new Error(`flow-ui: Tabs ${component.component_id} tabs must be an array`);
    }
    const active = resolveBound(host.surface, component, 'value', host.tasks)
        ?? optionalComponentProperty(component, 'value')
        ?? (tabs[0] && typeof tabs[0] === 'object' ? tabs[0].id : tabs[0]);
    return wrapFlowNode(
        host,
        component,
        html`<div role="tablist" class="suggestions">
            ${tabs.map((tab) => {
                const tabId = typeof tab === 'object' ? tab.id : tab;
                const tabLabel = typeof tab === 'object' ? (tab.label || tab.id) : tab;
                return html`<button
                    role="tab"
                    class=${String(tabId) === String(active) ? '' : 'secondary'}
                    aria-selected=${String(tabId) === String(active) ? 'true' : 'false'}
                    ?disabled=${host.readonly}
                    @click=${() => host._change(component, 'value', tabId)}
                >${tabLabel}</button>`;
            })}
        </div>
        ${renderChildren(host, component)}`,
    );
}

export function renderModal(host, component) {
    const open = resolveBound(host.surface, component, 'open', host.tasks)
        ?? optionalComponentProperty(component, 'open')
        ?? false;
    if (open !== true) return nothing;
    const title = labelOf(host, component);
    return wrapFlowNode(
        host,
        component,
        html`<div class="card" role="dialog" aria-modal="true" aria-label=${title || flowUIText(host.locale, 'dialog')}>
            ${title ? html`<h3>${title}</h3>` : nothing}
            ${renderChildren(host, component)}
        </div>`,
    );
}

export function registerBasicExtras(register) {
    register('Icon', renderIcon);
    register('Tabs', renderTabs);
    register('Modal', renderModal);
}

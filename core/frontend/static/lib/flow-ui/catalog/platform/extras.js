import { html, nothing } from '../../../lit-shim.js';
import { isA2UIArtifact } from '../../protocol/a2ui-0-9-1-codec.js';
import {
    localizedText,
    optionalComponentProperty,
    renderChildren,
    renderProjectedArtifactCard,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import { flowUIText } from '../../utils/text.js';

function labelOf(host, component) {
    const bound = resolveBound(host.surface, component, 'label', host.tasks);
    if (bound === undefined) return optionalComponentProperty(component, 'title') || '';
    return localizedText(bound);
}

export function renderJsonInspector(host, component) {
    const data = resolveBound(host.surface, component, 'data', host.tasks)
        ?? resolveBound(host.surface, component, 'artifact', host.tasks)
        ?? component.properties;
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || 'JSON'}</div>
            <pre>${JSON.stringify(data, null, 2)}</pre>
        </article>`,
    );
}

export function renderCitations(host, component) {
    const items = resolveBound(host.surface, component, 'items', host.tasks)
        ?? optionalComponentProperty(component, 'items')
        ?? [];
    if (!Array.isArray(items)) {
        throw new Error(`flow-ui: Citations ${component.component_id} items must be an array`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<div class="section">
            <div class="artifact-title">${labelOf(host, component) || flowUIText(host.locale, 'citations')}</div>
            <ol>${items.map((item) => {
                const title = typeof item === 'object' ? (item.title || item.url || item.id) : item;
                const href = typeof item === 'object' && typeof item.url === 'string' ? item.url : '';
                const safe = /^(https?:|\/)/i.test(href) ? href : '';
                return html`<li>${safe
                    ? html`<a href=${safe} target="_blank" rel="noopener">${title}</a>`
                    : html`<span>${title}</span>`}</li>`;
            })}</ol>
        </div>`,
    );
}

export function renderFileCard(host, component) {
    const file = resolveBound(host.surface, component, 'file', host.tasks)
        ?? resolveBound(host.surface, component, 'value', host.tasks)
        ?? optionalComponentProperty(component, 'file');
    if (file == null || typeof file !== 'object') {
        throw new Error(`flow-ui: FileCard ${component.component_id} requires file object`);
    }
    const name = file.original_name || file.filename;
    if (!name) {
        throw new Error(`flow-ui: FileCard ${component.component_id} file missing original_name`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<div class="file">
            ${file.url
                ? html`<a href=${file.url} target="_blank" rel="noopener">${name}</a>`
                : html`<span>${name}</span>`}
            ${file.content_type ? html`<span class="muted">${file.content_type}</span>` : nothing}
        </div>`,
    );
}

export function renderFileList(host, component) {
    const files = resolveBound(host.surface, component, 'files', host.tasks)
        ?? resolveBound(host.surface, component, 'value', host.tasks)
        ?? optionalComponentProperty(component, 'files')
        ?? [];
    if (!Array.isArray(files)) {
        throw new Error(`flow-ui: FileList ${component.component_id} files must be an array`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<div class="section">${files.map((file) => {
            const name = file?.original_name || file?.filename;
            if (!name) throw new Error('flow-ui: FileList entry missing original_name');
            return html`<div class="file">${file.url
                ? html`<a href=${file.url} target="_blank" rel="noopener">${name}</a>`
                : html`<span>${name}</span>`}</div>`;
        })}</div>`,
    );
}

export function renderFileCollection(host, component) {
    return renderFileList(host, component);
}

export function renderArtifactCard(host, component) {
    const artifact = resolveBound(host.surface, component, 'artifact', host.tasks)
        ?? optionalComponentProperty(component, 'artifact');
    if (artifact == null || typeof artifact !== 'object') {
        throw new Error(`flow-ui: ArtifactCard ${component.component_id} requires artifact`);
    }
    return wrapFlowNode(host, component, renderProjectedArtifactCard(host.locale, artifact));
}

export function renderChart(host, component) {
    const spec = resolveBound(host.surface, component, 'spec', host.tasks)
        ?? optionalComponentProperty(component, 'spec');
    if (spec == null || typeof spec !== 'object') {
        throw new Error(`flow-ui: Chart ${component.component_id} requires declarative spec`);
    }
    const kind = spec.kind || spec.type;
    if (!['bar', 'line', 'pie', 'area'].includes(kind)) {
        throw new Error(`flow-ui: Chart ${component.component_id} unsupported kind ${kind}`);
    }
    const series = Array.isArray(spec.series) ? spec.series : [];
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || `${flowUIText(host.locale, 'chart')} · ${kind}`}</div>
            <ul>${series.map((item) => html`<li>${item.label || item.name}: ${item.value}</li>`)}</ul>
        </article>`,
    );
}

export function renderRunTrace(host, component) {
    const spans = resolveBound(host.surface, component, 'spans', host.tasks)
        ?? optionalComponentProperty(component, 'spans')
        ?? [];
    if (!Array.isArray(spans)) {
        throw new Error(`flow-ui: RunTrace ${component.component_id} spans must be an array`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || flowUIText(host.locale, 'run_trace')}</div>
            <ol>${spans.map((span) => html`<li>
                <strong>${span.name || span.span_id}</strong>
                <span class="muted">${span.status || ''}</span>
            </li>`)}</ol>
        </article>`,
    );
}

export function renderToolActivity(host, component) {
    const calls = resolveBound(host.surface, component, 'calls', host.tasks)
        ?? optionalComponentProperty(component, 'calls')
        ?? [];
    if (!Array.isArray(calls)) {
        throw new Error(`flow-ui: ToolActivity ${component.component_id} calls must be an array`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || flowUIText(host.locale, 'tool_activity')}</div>
            ${calls.map((call) => html`<div class="file">
                <strong>${call.name || call.tool_id}</strong>
                <span class="muted">${call.status || ''}</span>
            </div>`)}
        </article>`,
    );
}

export function renderBrowserPreview(host, component) {
    const sessionRef = resolveBound(host.surface, component, 'sessionRef', host.tasks)
        ?? optionalComponentProperty(component, 'sessionRef');
    if (!sessionRef || typeof sessionRef !== 'object' || !sessionRef.session_id) {
        throw new Error(`flow-ui: BrowserPreview ${component.component_id} requires sessionRef.session_id`);
    }
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || flowUIText(host.locale, 'browser_preview')}</div>
            <div class="muted">session ${sessionRef.session_id}</div>
            ${sessionRef.page_id ? html`<div class="muted">page ${sessionRef.page_id}</div>` : nothing}
        </article>`,
    );
}

export function renderAvatar(host, component) {
    const name = resolveBound(host.surface, component, 'name', host.tasks)
        ?? optionalComponentProperty(component, 'name')
        ?? labelOf(host, component);
    if (!name) throw new Error(`flow-ui: Avatar ${component.component_id} requires name`);
    const logoSrc = optionalComponentProperty(component, 'logo_path')
        || '/static/core/assets/service_logos/linnex_spinner_logo.png';
    return wrapFlowNode(
        host,
        component,
        html`<div class="identity"><div class="avatar" aria-hidden="true"><img src=${logoSrc} alt=""></div></div>`,
    );
}

function activityPayload(host, component) {
    return resolveBound(host.surface, component, 'artifact', host.tasks)
        ?? resolveBound(host.surface, component, 'data', host.tasks)
        ?? component.properties;
}

function renderActivityShell(host, component, title) {
    const payload = activityPayload(host, component);
    return wrapFlowNode(
        host,
        component,
        html`<article class="artifact-card">
            <div class="artifact-title">${labelOf(host, component) || title}</div>
            ${typeof payload === 'object' && payload != null && 'summary' in payload
                ? html`<p>${payload.summary}</p>`
                : html`<pre>${JSON.stringify(payload, null, 2)}</pre>`}
            ${renderChildren(host, component)}
        </article>`,
    );
}

export function renderSkillActivity(host, component) {
    return renderActivityShell(host, component, flowUIText(host.locale, 'skill_activity'));
}

export function renderReflectionResult(host, component) {
    return renderActivityShell(host, component, flowUIText(host.locale, 'reflection'));
}

export function renderActionPreview(host, component) {
    return renderActivityShell(host, component, flowUIText(host.locale, 'action_preview'));
}

export function renderActionResult(host, component) {
    return renderActivityShell(host, component, flowUIText(host.locale, 'action_result'));
}

export function renderActivityCard(host, component) {
    return renderActivityShell(host, component, flowUIText(host.locale, 'activity'));
}

export function registerPlatformExtras(register) {
    register('JsonInspector', renderJsonInspector);
    register('Citations', renderCitations);
    register('FileCard', renderFileCard);
    register('FileList', renderFileList);
    register('FileCollection', renderFileCollection);
    register('ArtifactCard', renderArtifactCard);
    register('Chart', renderChart);
    register('RunTrace', renderRunTrace);
    register('ToolActivity', renderToolActivity);
    register('BrowserPreview', renderBrowserPreview);
    register('Avatar', renderAvatar);
    register('SkillActivity', renderSkillActivity);
    register('ReflectionResult', renderReflectionResult);
    register('ActionPreview', renderActionPreview);
    register('ActionResult', renderActionResult);
    register('ActivityCard', renderActivityCard);
}

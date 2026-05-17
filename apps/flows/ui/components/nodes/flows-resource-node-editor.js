/**
 * flows-resource-node-editor — редактор ноды `resource` на графе.
 *
 * Закрепляет определения ресурсов (ветка / каталог); поля конфигурации — как в каталоге.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    branchDataResources,
    mergeBranchResourceRef,
    resolveResourceForPanel,
} from '../../_helpers/flows-branch-resource.js';
import { renderResourceDefinitionEditor } from '../editor/flows-resource-definition-editor-surface.js';

const SAVE_DEBOUNCE_MS = 400;

export class FlowsResourceNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .hint-text {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
                margin: 0;
            }
            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin: 0;
            }
            .resource-definitions {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-width: 0;
            }
            .resource-def-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                overflow: visible;
                min-width: 0;
                padding: var(--space-5);
                box-sizing: border-box;
            }
            .resource-def-miss {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px dashed var(--border-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'resource';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.expanded = false;
        this.embedded = false;
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._update = this.useOp('flows/resource_update');
        this._catalogPending = new Map();
        this._branchPending = new Map();
        this._timers = new Map();
        this._branchResourcesSlice = this.select((s) => {
            const bd = s.flowsEditor?.branchData;
            if (!bd || typeof bd.resources !== 'object') return null;
            return bd.resources;
        });
    }

    disconnectedCallback() {
        for (const timer of this._timers.values()) clearTimeout(timer);
        this._timers.clear();
        this._catalogPending.clear();
        this._branchPending.clear();
        super.disconnectedCallback?.();
    }

    _pinnedBranchResourceIds() {
        const raw = this.nodeConfig?.resources;
        if (!isPlainObject(raw)) {
            return [];
        }
        const out = [];
        const seen = new Set();
        for (const [k, ref] of Object.entries(raw)) {
            if (!isPlainObject(ref)) continue;
            const rid = typeof ref.resource_id === 'string' && ref.resource_id.length > 0 ? ref.resource_id : k;
            if (typeof rid !== 'string' || rid.length === 0) continue;
            if (seen.has(rid)) continue;
            seen.add(rid);
            out.push(rid);
        }
        return out;
    }

    _clearTimer(key) {
        const existing = this._timers.get(key);
        if (existing) clearTimeout(existing);
        this._timers.delete(key);
    }

    _scheduleCatalogSave(resourceId, body) {
        const key = `catalog:${resourceId}`;
        this._catalogPending.set(resourceId, body);
        this._clearTimer(key);
        const timer = setTimeout(() => {
            const payload = this._catalogPending.get(resourceId);
            this._catalogPending.delete(resourceId);
            this._timers.delete(key);
            if (!payload) return;
            void this._update.run({ resource_id: resourceId, body: payload });
        }, SAVE_DEBOUNCE_MS);
        this._timers.set(key, timer);
    }

    _getBranchRefSnapshot(resourceId) {
        const state = this._editor.state;
        if (!isPlainObject(state) || !isPlainObject(state.branchData)) {
            return null;
        }
        const resources = branchDataResources(state.branchData);
        const ref = resources[resourceId];
        return isPlainObject(ref) ? { ...ref } : null;
    }

    _flushBranchResource(resourceId, nextRef) {
        const state = this._editor.state;
        if (!isPlainObject(state) || !isPlainObject(state.branchData)) {
            throw new Error('flows-resource-node-editor: branchData missing for flush');
        }
        const data = state.branchData;
        const resources = { ...branchDataResources(data), [resourceId]: nextRef };
        const snapshot = { ...data, resources };
        this._editor.updateBranchData({ data: snapshot });
        this._editor.setDirty({ dirty: true });
        this._editor.pushHistory({ snapshot });
    }

    _scheduleBranchSave(resourceId, patch) {
        const key = `branch:${resourceId}`;
        const existingTimer = this._timers.get(key);
        if (existingTimer) clearTimeout(existingTimer);
        const prevAccum = this._branchPending.get(resourceId);
        const base = prevAccum ?? this._getBranchRefSnapshot(resourceId);
        if (!isPlainObject(base)) {
            return;
        }
        const merged = mergeBranchResourceRef(base, patch);
        this._branchPending.set(resourceId, merged);
        const timer = setTimeout(() => {
            const body = this._branchPending.get(resourceId);
            this._branchPending.delete(resourceId);
            this._timers.delete(key);
            if (!body) return;
            this._flushBranchResource(resourceId, body);
        }, SAVE_DEBOUNCE_MS);
        this._timers.set(key, timer);
    }

    _onResourceDefinitionChange(e) {
        const { resourceId, patch } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof resourceId !== 'string' || resourceId.length === 0 || !isPlainObject(patch)) {
            return;
        }
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const catalogItem = items.find((r) => r && r.resource_id === resourceId);
        if (catalogItem) {
            const body = { ...catalogItem };
            for (const [k, v] of Object.entries(patch)) {
                if (k === 'config' && isPlainObject(v)) {
                    const baseCfg = isPlainObject(catalogItem.config) ? catalogItem.config : {};
                    body.config = { ...baseCfg, ...v };
                } else {
                    body[k] = v;
                }
            }
            this._scheduleCatalogSave(resourceId, body);
            return;
        }
        const resources = branchDataResources(state.branchData);
        if (Object.prototype.hasOwnProperty.call(resources, resourceId)) {
            this._scheduleBranchSave(resourceId, patch);
        }
    }

    _renderPinnedDefinitionEditors() {
        void this._branchResourcesSlice.value;
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return '';
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const ids = this._pinnedBranchResourceIds();
        if (ids.length === 0) {
            return '';
        }
        return html`
            <div class="resource-definitions">
                <h3 class="section-title">${this.t('resource_node_editor.section_definitions')}</h3>
                ${ids.map((branchKey) => {
                    const resolved = resolveResourceForPanel(branchKey, state, items);
                    if (resolved === null) {
                        return html`
                            <div class="resource-def-miss">
                                <p class="hint-text">${this.t('resource_node_editor.unresolved', { vars: { id: branchKey } })}</p>
                            </div>
                        `;
                    }
                    return html`
                        <div class="resource-def-card">
                            ${renderResourceDefinitionEditor(
                                resolved.resource,
                                (ev) => this._onResourceDefinitionChange(ev),
                                { compactHeader: true },
                            )}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'resource'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="settings-wrap">
                    ${this._renderPinnedDefinitionEditors()}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-resource-node-editor', FlowsResourceNodeEditor);

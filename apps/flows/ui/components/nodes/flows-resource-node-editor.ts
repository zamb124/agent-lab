/**
 * flows-resource-node-editor — редактор ноды `resource` на графе.
 *
 * Закрепляет определения ресурсов (ветка / каталог); поля конфигурации — как в каталоге.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    branchDataResources,
    mergeBranchResourceRef,
    resolveResourceForPanel,
} from '../../_helpers/flows-branch-resource.js';
import { renderResourceDefinitionEditor } from '../editor/flows-resource-definition-editor-surface.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

const SAVE_DEBOUNCE_MS = 400;

export class FlowsResourceNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        flowNodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, unknown> | null;
    declare flowNodeType: string;
    declare flowVariables: Record<string, unknown> | null;
    declare graphNodes: unknown[] | null;
    declare previewExecutionState: Record<string, unknown> | null;
    declare dataflowNode: Record<string, unknown> | null;
    declare embedded: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        panelShellStyles,
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
    private _editor: ControllerFor<'flows/editor'>;
    private _resources: ResourceController;
    private _branchResourcesSlice: SelectController<Record<string, unknown> | null>;
    private _catalogPending: Map<string, Record<string, unknown>>;
    private _branchPending: Map<string, Record<string, unknown>>;
    private _timers: Map<string, ReturnType<typeof setTimeout>>;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.flowNodeType = 'resource';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._catalogPending = new Map();
        this._branchPending = new Map();
        this._timers = new Map();
        this._branchResourcesSlice = this.select((s) => {
            const editor = s.flowsEditor;
            if (!isPlainObject(editor)) return null;
            const bd = editor.branchData;
            if (!isPlainObject(bd)) return null;
            const resources = bd.resources;
            if (!isPlainObject(resources)) return null;
            return resources;
        });
    }

    override disconnectedCallback(): void {
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
        const out: string[] = [];
        const seen = new Set<string>();
        for (const [key, ref] of Object.entries(raw)) {
            if (!isPlainObject(ref)) continue;
            const resourceId = ref.resource_id;
            const rid = typeof resourceId === 'string' && resourceId.length > 0 ? resourceId : key;
            if (typeof rid !== 'string' || rid.length === 0) continue;
            if (seen.has(rid)) continue;
            seen.add(rid);
            out.push(rid);
        }
        return out;
    }

    _clearTimer(key: string) {
        const existing = this._timers.get(key);
        if (existing) clearTimeout(existing);
        this._timers.delete(key);
    }

    _scheduleCatalogSave(resourceId: string, body: Record<string, unknown>) {
        const key = `catalog:${resourceId}`;
        this._catalogPending.set(resourceId, body);
        this._clearTimer(key);
        const timer = setTimeout(() => {
            const payload = this._catalogPending.get(resourceId);
            this._catalogPending.delete(resourceId);
            this._timers.delete(key);
            if (!payload) return;
            this._resources.update(resourceId, {
                name: payload.name,
                description: payload.description,
                config: payload.config,
                tags: payload.tags,
                permission: payload.permission,
            });
        }, SAVE_DEBOUNCE_MS);
        this._timers.set(key, timer);
    }

    _getBranchRefSnapshot(resourceId: string) {
        const state = this._editor.state;
        if (!isPlainObject(state) || !isPlainObject(state.branchData)) {
            return null;
        }
        const resources = branchDataResources(state.branchData);
        const ref = resources[resourceId];
        return isPlainObject(ref) ? { ...ref } : null;
    }

    _flushBranchResource(resourceId: string, nextRef: Record<string, unknown>) {
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

    _scheduleBranchSave(resourceId: string, patch: Record<string, unknown>) {
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

    _onResourceDefinitionChange(e: CustomEvent) {
        const { resourceId, patch } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof resourceId !== 'string' || resourceId.length === 0 || !isPlainObject(patch)) {
            return;
        }
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const catalogItem = items.find((item): item is Record<string, unknown> => (
            isPlainObject(item) && item.resource_id === resourceId
        ));
        if (catalogItem) {
            const body: Record<string, unknown> = { ...catalogItem };
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
                                <p class="hint-text">${this.t('resource_node_editor.unresolved', { id: branchKey })}</p>
                            </div>
                        `;
                    }
                    return html`
                        <div class="resource-def-card content-panel">
                            ${renderResourceDefinitionEditor(
                                resolved.resource,
                                (ev: CustomEvent) => this._onResourceDefinitionChange(ev),
                                { compactHeader: true, flowId: this.flowId, nodeId: this.nodeId },
                            )}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    override render(): TemplateResult {
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .flowNodeType=${this.flowNodeType.length > 0 ? this.flowNodeType : 'resource'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
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

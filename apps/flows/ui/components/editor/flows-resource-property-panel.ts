/**
 * flows-resource-property-panel — слот для активного редактора ресурса.
 *
 * Читает selectedResourceId из useOp('flows/editor') as unknown as ControllerFor<'flows/editor'>.
 * Ресурс: либо запись каталога useResource('flows/resources'), либо ключ в
 * branchData.resources (inline / ссылка на shared с ключа ветки r_…).
 *
 * Save каталога → useResource('flows/resources').update с debounce 400ms.
 * Save ветки → merge в branchData.resources + updateBranchData + debounce 400ms.
 * Delete каталога → flows/resources.remove.
 * Delete ветки → удалить ключ из branchData.resources.
 *
 * Кнопка удаления монтируется в `.header-actions-host` у `flows-floating-panel`
 * (как Run у flows-base-node-editor): слева от «развернуть» и «закрыть».
 *
 * Роутинг по `resource.type` (ResourceType): llm | secret | code | …
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    branchDataResources,
    mergeBranchResourceRef,
    resolveResourceForPanel,
} from '../../_helpers/flows-branch-resource.js';
import { renderResourceDefinitionEditor } from './flows-resource-definition-editor-surface.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const SAVE_DEBOUNCE_MS = 400;

export class FlowsResourcePropertyPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String },
    }
    declare flowId: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _resources: ResourceController;
    private _catalogPending: Map<any, any>;
    private _branchPending: Map<any, any>;
    private _timers: Map<any, any>;
    private _headerDeleteBtn: any;

    constructor() {
        super();
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._catalogPending = new Map();
        this._branchPending = new Map();
        this._timers = new Map();
        this._headerDeleteBtn = null;
        this._onHeaderDeleteClick = this._onHeaderDeleteClick.bind(this);
    }

    override connectedCallback(): void {
        super.connectedCallback?.();
        queueMicrotask(() => this._placeResourceHeaderDelete());
        requestAnimationFrame(() => this._placeResourceHeaderDelete());
    }

    override disconnectedCallback(): void {
        this._teardownHeaderDelete();
        super.disconnectedCallback?.();
        for (const timer of this._timers.values()) clearTimeout(timer);
        this._timers.clear();
        this._catalogPending.clear();
        this._branchPending.clear();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        this._placeResourceHeaderDelete();
    }

    /**
     * ShadowRoot → host, как у flows-base-node-editor до flows-floating-panel.
     */
    _findFlowsFloatingPanel() {
        let n: any = this;
        for (let d = 0; d < 128; d += 1) {
            if (!n) {
                return null;
            }
            if (n.nodeName === 'FLOWS-FLOATING-PANEL') {
                return n;
            }
            const p = n.parentNode;
            if (p instanceof ShadowRoot) {
                n = p.host;
            } else {
                n = p;
            }
        }
        return null;
    }

    _floatingPanelHeaderActionsHost(panel: any) {
        const root = panel.shadowRoot;
        if (!root) {
            return null;
        }
        return root.querySelector('.header-actions-host');
    }

    _ensureHeaderDeleteBtn() {
        if (this._headerDeleteBtn) {
            return this._headerDeleteBtn;
        }
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'panel-btn';
        btn.addEventListener('click', this._onHeaderDeleteClick);
        const icon = document.createElement('platform-icon');
        icon.setAttribute('name', 'trash');
        icon.setAttribute('size', '14');
        btn.appendChild(icon);
        this._headerDeleteBtn = btn;
        return btn;
    }

    _teardownHeaderDelete() {
        if (this._headerDeleteBtn && this._headerDeleteBtn.parentNode) {
            this._headerDeleteBtn.parentNode.removeChild(this._headerDeleteBtn);
        }
    }

    _placeResourceHeaderDelete() {
        if (!this.isConnected) {
            return;
        }
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            this._teardownHeaderDelete();
            return;
        }
        const resourceId = state.selectedResourceId;
        if (typeof resourceId !== 'string' || resourceId.length === 0) {
            this._teardownHeaderDelete();
            return;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const resolved = resolveResourceForPanel(resourceId, state, items);
        if (resolved === null) {
            this._teardownHeaderDelete();
            return;
        }
        const panel = this._findFlowsFloatingPanel();
        const host = panel ? this._floatingPanelHeaderActionsHost(panel) : null;
        if (!host) {
            this._teardownHeaderDelete();
            return;
        }
        const btn = this._ensureHeaderDeleteBtn();
        btn.title = this.t('property_panel.action_delete_resource');
        if (btn.parentNode !== host) {
            host.appendChild(btn);
        }
    }

    _onHeaderDeleteClick() {
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return;
        }
        const rid = state.selectedResourceId;
        if (typeof rid !== 'string' || rid.length === 0) {
            return;
        }
        void this._onDelete(rid);
    }

    _clearTimer(key: string) {
        const existing = this._timers.get(key);
        if (existing) clearTimeout(existing);
        this._timers.delete(key);
    }

    _scheduleCatalogSave(resourceId: string, body: any) {
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

    _flushBranchResource(resourceId: string, nextRef: any) {
        const state = this._editor.state;
        if (!isPlainObject(state) || !isPlainObject(state.branchData)) {
            throw new Error('flows-resource-property-panel: branchData missing for flush');
        }
        const data = state.branchData;
        const resources = { ...branchDataResources(data), [resourceId]: nextRef };
        const snapshot = { ...data, resources };
        (this._editor.updateBranchData({ data: snapshot }) as any);
        (this._editor.setDirty({ dirty: true }) as any);
        (this._editor.pushHistory({ snapshot }) as any);
    }

    _scheduleBranchSave(resourceId: string, patch: any) {
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

    _onChange(e: CustomEvent) {
        const { resourceId, patch } = isPlainObject(e.detail) ? e.detail : {};
        if (typeof resourceId !== 'string' || resourceId.length === 0 || !isPlainObject(patch)) {
            return;
        }
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const catalogItem = items.find((r: any) => r && r.resource_id === resourceId);
        if (catalogItem) {
            const body: any = { ...catalogItem };
            for (const [k, v] of Object.entries(patch)) {
                if (k === 'config' && isPlainObject(v)) {
                    const baseCfg = isPlainObject(catalogItem.config) ? catalogItem.config : {};
                    body.config = { ...baseCfg, ...(v as Record<string, any>) };
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

    async _onDelete(resourceId: string) {
        if (typeof resourceId !== 'string' || resourceId.length === 0) {
            return;
        }
        const state = this._editor.state;
        const resources = branchDataResources(isPlainObject(state) ? state.branchData : null);
        if (Object.prototype.hasOwnProperty.call(resources, resourceId)) {
            const keyCatalog = `catalog:${resourceId}`;
            const keyBranch = `branch:${resourceId}`;
            this._clearTimer(keyCatalog);
            this._clearTimer(keyBranch);
            this._catalogPending.delete(resourceId);
            this._branchPending.delete(resourceId);
            const data = isPlainObject(state.branchData) ? state.branchData : {};
            const nextRes = { ...resources };
            delete nextRes[resourceId];
            const snapshot = { ...data, resources: nextRes };
            (this._editor.updateBranchData({ data: snapshot }) as any);
            (this._editor.setDirty({ dirty: true }) as any);
            (this._editor.pushHistory({ snapshot }) as any);
            (this._editor.selectResource({ resourceId: null }) as any);
            return;
        }
        await this._resources.remove(resourceId);
        (this._editor.selectResource({ resourceId: null }) as any);
    }

    override render(): TemplateResult {
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_resource')}</div>`;
        }
        const resourceId = state.selectedResourceId;
        if (typeof resourceId !== 'string' || resourceId.length === 0) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_resource')}</div>`;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const resolved = resolveResourceForPanel(resourceId, state, items);
        if (resolved === null) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_resource')}</div>`;
        }
        return html`${renderResourceDefinitionEditor(resolved.resource, (e: CustomEvent) => this._onChange(e), { flowId: this.flowId })}`;
    }
}

customElements.define('flows-resource-property-panel', FlowsResourcePropertyPanel);

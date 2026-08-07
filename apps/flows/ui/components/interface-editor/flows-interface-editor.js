/**
 * Interface editor orchestrator: pages/layers/palette · production canvas ·
 * inspector, with slice-backed command history (undo/redo survives remounts),
 * clipboard, keyboard shortcuts and a selection breadcrumb.
 * Every document edit is one labeled history transaction.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { applyLayoutCommand } from '@platform/lib/flow-ui/editor/layout-domain-commands.js';
import { flowUIPageTemplate } from '@platform/lib/flow-ui/templates/page-templates.js';
import {
    activeSurface,
    clone,
    cloneSubtree,
    columnsPresetCount,
    containerLayoutPreset,
    createColumnsPreset,
    defaultComponent,
    findParentId,
    materializeClipboard,
    applyRowShifts,
    normalizeAuthorContainersToGrid,
    placeInGrid,
    quickFixAddSubmit,
    removeSubtree,
    renameComponent,
    serializeClipboard,
    uniqueComponentId,
    validateInterfaceDocument,
} from './interface-editor-domain.js';
import './flows-interface-toolbar.js';
import './flows-interface-pages-panel.js';
import './flows-interface-palette.js';
import './flows-interface-layers-tree.js';
import './flows-interface-canvas.js';
import './flows-interface-inspector.js';
import './flows-interface-component-menu.js';
import './flows-interface-data-model-panel.js';
import './flows-interface-contract-panel.js';
import './flows-interface-problems-panel.js';

// One clipboard per editor session; survives selection changes, not reloads.
let interfaceClipboard = null;

export class FlowsInterfaceEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        interfaceConfig: { attribute: false },
        flowId: { type: String },
        branchId: { type: String },
        parity: { state: true },
        rightPanel: { state: true },
        _componentMenu: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host {
            display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
            min-width: 0; min-height: 0; height: 100%; background: var(--bg-elevated);
        }
        .body {
            display: grid;
            grid-template-columns: minmax(260px, 280px) minmax(0, 1fr) minmax(300px, 340px);
            min-height: 0;
        }
        .left, .right { min-height: 0; overflow: auto; background: var(--glass-solid-medium); }
        .left { border-right: 1px solid var(--border-subtle); padding: 12px; display: grid; align-content: start; gap: 4px; }
        .right { border-left: 1px solid var(--border-subtle); }
        flows-interface-canvas { min-width: 0; min-height: 0; }
        .tabs { display: flex; border-bottom: 1px solid var(--border-subtle); }
        .tabs .tab {
            flex: 1; color: var(--text-tertiary); text-align: center;
            padding: 11px 9px; cursor: pointer; font-size: 12px; font-weight: 600;
        }
        .tabs .tab[data-active="true"] {
            color: var(--text-primary); box-shadow: inset 0 -2px var(--accent);
        }
        .tabs .tab:hover { color: var(--text-primary); }
        .tabs .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
        .footer {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: stretch;
            border-top: 1px solid var(--border-subtle);
            background: var(--glass-solid-medium);
            min-height: 34px;
        }
        .breadcrumb {
            display: flex; align-items: center; gap: 2px; padding: 6px 12px;
            font-size: 11px; overflow-x: auto; white-space: nowrap; min-width: 0;
        }
        .breadcrumb .crumb {
            color: var(--text-tertiary);
            cursor: pointer; font-size: 11px; padding: 2px 4px; border-radius: 5px;
        }
        .breadcrumb .crumb:hover { color: var(--text-primary); background: var(--glass-solid-subtle); }
        .breadcrumb .crumb[data-current="true"] { color: var(--accent); font-weight: 650; }
        .breadcrumb .crumb:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .breadcrumb .sep { color: var(--text-tertiary); opacity: .5; }
        .footer flows-interface-problems-panel {
            border-top: none;
            background: transparent;
        }
        @media (max-width: 1000px) {
            .body { grid-template-columns: 220px minmax(0, 1fr); }
            .right {
                position: absolute; right: 0; top: 100px; bottom: 40px; width: 320px;
                z-index: 5; box-shadow: var(--shadow-lg);
            }
        }
    `];

    constructor() {
        super();
        this.interfaceConfig = null;
        this.flowId = '';
        this.branchId = 'default';
        this.parity = {
            status: 'Loading',
            fingerprint: '',
            assetsReady: false,
            expectedContext: null,
            actualContext: null,
            diff: [],
        };
        this.rightPanel = 'properties';
        this._componentMenu = null;
        this._normalizedDocument = null;
        this._editorState = this.useSlice('flows/interface_editor');
        this._onKeyDown = (event) => this._handleHotkeys(event);
    }

    updated(changed) {
        if (!changed.has('interfaceConfig')) return;
        const document = this.interfaceConfig?.template?.document;
        // On-load migrate runs once per loaded document, not per config change: the
        // document it emits comes back as the same object, so the pass cannot re-enter.
        if (!document || document === this._normalizedDocument) return;
        this._normalizedDocument = document;
        queueMicrotask(() => this._normalizeAuthorGrids(document));
    }

    /**
     * Grid-first on-load migrate: author containers → grid, `row_start: 'auto'` → a
     * real row. Emits interface-change without history when anything changed.
     */
    _normalizeAuthorGrids(source) {
        if (this.interfaceConfig?.template?.document !== source) return;
        const document = clone(source);
        if (!normalizeAuthorContainersToGrid(document)) return;
        document.revision = Number(document.revision || 0) + 1;
        const config = clone(this.interfaceConfig);
        config.template.document = document;
        config.policy = clone(document.policy);
        this._normalizedDocument = document;
        this.emit('interface-change', { config });
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._onKeyDown);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._onKeyDown);
        super.disconnectedCallback();
    }

    get editorState() {
        return this._editorState.value;
    }

    get document() {
        return this.interfaceConfig?.template?.document || null;
    }

    get surface() {
        return this.document ? activeSurface(this.document) : null;
    }

    get selected() {
        return this.surface?.components?.[this.editorState?.selectedComponentId] || null;
    }

    _locale() {
        return this.select((state) => state.i18n.locale).value === 'ru' ? 'ru' : 'en';
    }

    _dispatchConfig(config) {
        this.emit('interface-change', { config });
    }

    _pushHistory(label, coalesceKey = '') {
        if (!this.interfaceConfig) return;
        this._editorState.historyPush({
            label,
            coalesceKey,
            config: clone(this.interfaceConfig),
        });
    }

    _commitDocument(document, { label, coalesceKey = '' }) {
        if (typeof label !== 'string' || label === '') {
            throw new Error('flows-interface-editor: history label required');
        }
        this._pushHistory(label, coalesceKey);
        const config = clone(this.interfaceConfig);
        config.template.document = document;
        config.policy = clone(document.policy);
        this._dispatchConfig(config);
    }

    _mutate(label, mutator, { coalesceKey = '' } = {}) {
        if (!this.interfaceConfig || !this.document) {
            throw new Error('flows-interface-editor: cannot mutate without interface document');
        }
        const document = clone(this.document);
        mutator(document);
        document.revision = Number(document.revision || 0) + 1;
        this._commitDocument(document, { label, coalesceKey });
    }

    _undo() {
        const past = this.editorState.history?.past || [];
        if (!past.length) return;
        const entry = past[past.length - 1];
        this._editorState.historyUndo({ config: clone(this.interfaceConfig) });
        this._dispatchConfig(clone(entry.config));
    }

    _redo() {
        const future = this.editorState.history?.future || [];
        if (!future.length) return;
        const entry = future[0];
        this._editorState.historyRedo({ config: clone(this.interfaceConfig) });
        this._dispatchConfig(clone(entry.config));
    }

    _selectComponent(event) {
        this._editorState.selectComponent({
            componentId: event.detail.componentId,
            additive: event.detail.additive === true,
        });
    }

    _selectPage(event) {
        const pageId = event.detail.pageId;
        this._editorState.selectPage({ pageId });
        this._mutate(this.t('interface_editor.history_page_select'), (document) => {
            document.active_page_id = pageId;
        });
    }

    /**
     * Insert a component into a grid parent. `area` is the exact cell chosen on
     * the canvas; without it (palette click, keyboard) the component appends to
     * the first free row below everything else.
     */
    _insertComponent(type, targetParentId = null, index = null, area = null, shifted = null) {
        let createdId = '';
        this._mutate(this.t('interface_editor.history_insert'), (document) => {
            const surface = activeSurface(document);
            let parent = targetParentId
                ? surface.components[targetParentId]
                : surface.components[this.editorState.selectedComponentId];
            if (!parent || parent.kind !== 'container') {
                parent = surface.components[surface.root_component_id || 'root'];
            }
            const children = [...(parent.children || [])];
            const at = Number.isInteger(index) ? Math.min(Math.max(index, 0), children.length) : children.length;
            const columnCount = columnsPresetCount(type);
            if (columnCount != null) {
                const preset = createColumnsPreset(columnCount, surface, this._locale());
                Object.assign(surface.components, preset.components);
                applyRowShifts(surface, shifted);
                placeInGrid(parent, surface, preset.components[preset.rootId], area);
                children.splice(at, 0, preset.rootId);
                parent.children = children;
                createdId = preset.rootId;
                return;
            }
            const component = defaultComponent(
                type,
                uniqueComponentId(surface, type),
                this._locale(),
            );
            applyRowShifts(surface, shifted);
            placeInGrid(parent, surface, component, area);
            surface.components[component.component_id] = component;
            children.splice(at, 0, component.component_id);
            parent.children = children;
            createdId = component.component_id;
        });
        if (createdId) {
            this._editorState.selectComponent({ componentId: createdId, additive: false });
        }
    }

    _addComponent(event) {
        this._insertComponent(event.detail.type);
    }

    _dropComponent(event) {
        this._insertComponent(
            event.detail.type,
            event.detail.targetParentId,
            event.detail.index,
            event.detail.area,
            event.detail.shifted,
        );
    }

    _deleteSelection() {
        const surface = this.surface;
        if (!surface) return;
        const rootId = surface.root_component_id || 'root';
        const ids = (this.editorState.selectedComponentIds || [])
            .filter((id) => id !== rootId && surface.components[id]);
        if (!ids.length) return;
        this._mutate(this.t('interface_editor.history_delete'), (document) => {
            const target = activeSurface(document);
            for (const id of ids) removeSubtree(target, id);
        });
        this._editorState.selectComponent({ componentId: rootId, additive: false });
    }

    _deleteComponent(event) {
        const id = event.detail.componentId;
        const surface = this.surface;
        if (!surface || id === (surface.root_component_id || 'root')) return;
        this._mutate(this.t('interface_editor.history_delete'), (document) => {
            removeSubtree(activeSurface(document), id);
        });
        this._editorState.selectComponent({
            componentId: surface.root_component_id || 'root',
            additive: false,
        });
    }

    _renameComponent(event) {
        const { componentId, nextId } = event.detail;
        this._mutate(this.t('interface_editor.history_rename'), (document) => {
            renameComponent(activeSurface(document), componentId, nextId);
        });
        this._editorState.selectComponent({ componentId: nextId, additive: false });
    }

    _componentVisibility(event) {
        const { componentId, visible } = event.detail;
        this._mutate(this.t('interface_editor.history_visibility'), (document) => {
            const component = activeSurface(document).components[componentId];
            if (!component) return;
            component.visibility = visible ? null : false;
        });
    }

    _layersMove(event) {
        const { componentId, targetId, position } = event.detail;
        const surface = this.surface;
        if (!surface) return;
        const surfaceId = surface.surface_id
            || this.document.pages[this.document.active_page_id].root_surface_id;
        let targetParentId;
        let index;
        if (position === 'inside') {
            targetParentId = targetId;
            index = (surface.components[targetId]?.children || []).length;
        } else {
            targetParentId = findParentId(surface, targetId);
            if (!targetParentId) return;
            const siblings = (surface.components[targetParentId].children || [])
                .filter((id) => id !== componentId);
            index = siblings.indexOf(targetId);
            if (index < 0) return;
            if (position === 'after') index += 1;
        }
        this._applyLayoutCommand({
            kind: 'children.move',
            surfaceId,
            componentId,
            targetParentId,
            index,
        }, this.t('interface_editor.history_move'));
    }

    _duplicateComponent(componentId) {
        const surface = this.surface;
        if (!surface || componentId === (surface.root_component_id || 'root')) return;
        let createdId = '';
        this._mutate(this.t('interface_editor.history_duplicate'), (document) => {
            const target = activeSurface(document);
            const parentId = findParentId(target, componentId);
            if (!parentId) return;
            const { rootId, components } = cloneSubtree(target, componentId);
            Object.assign(target.components, components);
            const parent = target.components[parentId];
            const children = [...(parent.children || [])];
            children.splice(children.indexOf(componentId) + 1, 0, rootId);
            parent.children = children;
            createdId = rootId;
        });
        if (createdId) {
            this._editorState.selectComponent({ componentId: createdId, additive: false });
        }
    }

    _copySelection() {
        const surface = this.surface;
        if (!surface) return;
        const rootId = surface.root_component_id || 'root';
        const ids = (this.editorState.selectedComponentIds || []).filter((id) => id !== rootId);
        if (!ids.length) return;
        interfaceClipboard = serializeClipboard(surface, ids);
    }

    _pasteClipboard(targetComponentId = null) {
        if (!interfaceClipboard) return;
        const surface = this.surface;
        if (!surface) return;
        let lastId = '';
        this._mutate(this.t('interface_editor.history_paste'), (document) => {
            const target = activeSurface(document);
            const { roots, components } = materializeClipboard(target, interfaceClipboard);
            Object.assign(target.components, components);
            let parent = target.components[targetComponentId || this.editorState.selectedComponentId];
            if (parent && parent.kind !== 'container') {
                const parentId = findParentId(target, parent.component_id);
                parent = parentId ? target.components[parentId] : null;
            }
            if (!parent || parent.kind !== 'container') {
                parent = target.components[target.root_component_id || 'root'];
            }
            parent.children = [...(parent.children || []), ...roots];
            lastId = roots[roots.length - 1];
        });
        if (lastId) {
            this._editorState.selectComponent({ componentId: lastId, additive: false });
        }
    }

    /**
     * Wrap a component into a Section grid. The wrapper takes the component's own
     * cell in the parent, and the component moves to the wrapper's first cell —
     * so no sibling cell is disturbed.
     */
    _wrapInSection(componentId) {
        const surface = this.surface;
        if (!surface || componentId === (surface.root_component_id || 'root')) return;
        let wrapperId = '';
        this._mutate(this.t('interface_editor.history_wrap'), (document) => {
            const target = activeSurface(document);
            const parentId = findParentId(target, componentId);
            if (!parentId) return;
            const wrapped = target.components[componentId];
            const wrapper = defaultComponent('Section', uniqueComponentId(target, 'Section'), this._locale());
            wrapper.container_layout = containerLayoutPreset('grid');
            wrapper.children = [componentId];
            wrapper.placement.base = { ...wrapper.placement.base, ...wrapped.placement.base };
            wrapper.placement.overrides = clone(wrapped.placement.overrides || {});
            wrapped.placement.base = {
                ...wrapped.placement.base,
                column_start: 1,
                column_span: 'full',
                row_start: 1,
            };
            wrapped.placement.overrides = {};
            target.components[wrapper.component_id] = wrapper;
            const parent = target.components[parentId];
            parent.children = (parent.children || [])
                .map((childId) => (childId === componentId ? wrapper.component_id : childId));
            wrapperId = wrapper.component_id;
        });
        if (wrapperId) {
            this._editorState.selectComponent({ componentId: wrapperId, additive: false });
        }
    }

    _addPage() {
        this._mutate(this.t('interface_editor.history_page_add'), (document) => {
            let index = Object.keys(document.pages).length + 1;
            let pageId = `page-${index}`;
            while (document.pages[pageId]) {
                index += 1;
                pageId = `page-${index}`;
            }
            const surfaceId = pageId;
            document.pages[pageId] = {
                page_id: pageId,
                title: { default: `${this.t('interface_editor.page_default_title')} ${index}`, translations: {} },
                route: `/${pageId}`,
                root_surface_id: surfaceId,
                navigation: { visible: true, allow_back: true, allow_direct: true },
                default_target_profile_id: 'runtime',
            };
            const root = defaultComponent('PageShell', 'root', this._locale());
            root.container_layout = containerLayoutPreset('grid');
            const submit = defaultComponent('Submit', 'submit', this._locale());
            root.children = ['submit'];
            document.surfaces[surfaceId] = {
                surface_id: surfaceId,
                catalog_id: document.catalog_id,
                root_component_id: 'root',
                components: { root, submit },
                data_model: { content: {}, values: {}, system: {} },
                owner: 'platform',
                send_data_model: true,
            };
            document.active_page_id = pageId;
            queueMicrotask(() => this._editorState.selectPage({ pageId }));
        });
    }

    _renamePage(event) {
        const { pageId, title } = event.detail;
        this._mutate(this.t('interface_editor.history_page_rename'), (document) => {
            const page = document.pages[pageId];
            if (!page) return;
            page.title = { ...(page.title || { translations: {} }), default: title };
        });
    }

    _duplicatePage(event) {
        const sourcePageId = event.detail.pageId;
        this._mutate(this.t('interface_editor.history_page_duplicate'), (document) => {
            const source = document.pages[sourcePageId];
            if (!source) return;
            let index = Object.keys(document.pages).length + 1;
            let pageId = `page-${index}`;
            while (document.pages[pageId]) {
                index += 1;
                pageId = `page-${index}`;
            }
            const surfaceId = pageId;
            document.pages[pageId] = {
                ...clone(source),
                page_id: pageId,
                title: {
                    default: `${source.title?.default || sourcePageId} ${this.t('interface_editor.page_copy_suffix')}`,
                    translations: {},
                },
                route: `/${pageId}`,
                root_surface_id: surfaceId,
            };
            const sourceSurface = document.surfaces[source.root_surface_id];
            document.surfaces[surfaceId] = {
                ...clone(sourceSurface),
                surface_id: surfaceId,
            };
            document.active_page_id = pageId;
            queueMicrotask(() => this._editorState.selectPage({ pageId }));
        });
    }

    _deletePage(event) {
        const pageId = event.detail.pageId;
        this._mutate(this.t('interface_editor.history_page_delete'), (document) => {
            if (Object.keys(document.pages).length <= 1) return;
            const page = document.pages[pageId];
            if (!page) return;
            delete document.pages[pageId];
            delete document.surfaces[page.root_surface_id];
            if (document.active_page_id === pageId) {
                document.active_page_id = Object.keys(document.pages)[0];
            }
        });
        this._editorState.selectPage({ pageId: this.document?.active_page_id || 'main' });
    }

    _patchSelected(label, mutator, options = {}) {
        this._mutate(label, (document) => {
            const component = activeSurface(document).components[this.editorState.selectedComponentId];
            if (!component) return;
            mutator(component);
        }, options);
    }

    _propertyChange(event) {
        this._patchSelected(this.t('interface_editor.history_property'), (component) => {
            component.properties = {
                ...(component.properties || {}),
                [event.detail.name]: event.detail.value,
            };
        }, { coalesceKey: `property:${this.editorState.selectedComponentId}:${event.detail.name}` });
    }

    _openComponentMenu(event) {
        const { componentId, clientX, clientY } = event.detail || {};
        if (typeof componentId !== 'string' || componentId === '') {
            throw new Error('flows-interface-editor: component-menu-open requires componentId');
        }
        if (typeof clientX !== 'number' || typeof clientY !== 'number') {
            throw new Error('flows-interface-editor: component-menu-open requires clientX/clientY');
        }
        this._editorState.selectComponent({ componentId, additive: false });
        this._componentMenu = { componentId, x: clientX, y: clientY };
    }

    _closeComponentMenu() {
        this._componentMenu = null;
    }

    _checksChange(event) {
        this._patchSelected(this.t('interface_editor.history_validation'), (component) => {
            component.checks = Array.isArray(event.detail.checks)
                ? event.detail.checks.map((check) => ({ ...check }))
                : [];
        }, { coalesceKey: `checks:${this.editorState.selectedComponentId}` });
    }

    _inlineEdit(event) {
        const { componentId, name, value } = event.detail;
        this._mutate(this.t('interface_editor.history_property'), (document) => {
            const component = activeSurface(document).components[componentId];
            if (!component) return;
            component.properties = { ...(component.properties || {}), [name]: value };
        });
    }

    _placement(event) {
        this._patchSelected(this.t('interface_editor.history_placement'), (component) => {
            component.placement ||= { base: {}, overrides: {} };
            const patch = { ...event.detail.patch };
            if (Number.isInteger(patch.row_span)) {
                patch.block_clamp = true;
            }
            const band = event.detail.band;
            const writeBase = band === 'base' || band === 'wide';
            if (writeBase) {
                component.placement.base = { ...component.placement.base, ...patch };
                const wideOverride = component.placement.overrides?.wide;
                if (wideOverride != null && typeof wideOverride === 'object') {
                    const cleared = { ...wideOverride };
                    let changed = false;
                    for (const key of Object.keys(patch)) {
                        if (Object.prototype.hasOwnProperty.call(cleared, key)) {
                            delete cleared[key];
                            changed = true;
                        }
                    }
                    if (changed) {
                        if (Object.keys(cleared).length === 0) {
                            delete component.placement.overrides.wide;
                        } else {
                            component.placement.overrides.wide = cleared;
                        }
                    }
                }
            } else {
                component.placement.overrides[band] = {
                    ...(component.placement.overrides[band] || {}),
                    ...patch,
                };
            }
        }, { coalesceKey: `placement:${this.editorState.selectedComponentId}:${event.detail.band}` });
    }

    _placementReset(event) {
        this._patchSelected(this.t('interface_editor.history_placement_reset'), (component) => {
            if (!component.placement?.overrides) return;
            const overrides = { ...component.placement.overrides };
            delete overrides[event.detail.band];
            component.placement.overrides = overrides;
        });
    }

    _applyLayoutCommand(command, label) {
        if (!this.interfaceConfig || !this.document) {
            throw new Error('flows-interface-editor: cannot apply layout-command without interface document');
        }
        const next = applyLayoutCommand(this.document, command);
        this._commitDocument(next, {
            label,
            coalesceKey: `${command.kind}:${command.componentId}`,
        });
    }

    _layoutCommand(event) {
        const command = event.detail;
        if (!command || typeof command !== 'object') {
            throw new Error('flows-interface-editor: layout-command detail required');
        }
        this._applyLayoutCommand(command, this.t('interface_editor.history_layout'));
    }

    _layout(event) {
        this._patchSelected(this.t('interface_editor.history_layout'), (component) => {
            const patch = event.detail.patch;
            if (patch.mode && patch.mode !== component.container_layout?.mode) {
                component.container_layout = containerLayoutPreset(patch.mode);
            }
            const layout = component.container_layout;
            if (!layout) return;
            if (patch.columns && layout.grid) {
                layout.grid.columns_by_band = {
                    ...layout.grid.columns_by_band,
                    ...patch.columns,
                };
            }
            if (patch.gap && layout.grid) {
                layout.grid.column_gap_token = patch.gap;
                layout.grid.row_gap_token = patch.gap;
            }
            if (patch.flex && layout.flex) {
                layout.flex = { ...layout.flex, ...patch.flex };
            }
            if (patch.stack && layout.stack) {
                layout.stack = { ...layout.stack, ...patch.stack };
            }
        });
    }

    _binding(event) {
        this._patchSelected(this.t('interface_editor.history_binding'), (component) => {
            component.bindings = {
                ...(component.bindings || {}),
                [event.detail.name]: event.detail.path,
            };
        });
    }

    _bindingRemove(event) {
        this._patchSelected(this.t('interface_editor.history_binding'), (component) => {
            const next = { ...(component.bindings || {}) };
            delete next[event.detail.name];
            component.bindings = next;
        });
    }

    _action(event) {
        this._patchSelected(this.t('interface_editor.history_action'), (component) => {
            const name = event.detail.name;
            if (name === 'none') {
                component.actions = {};
                return;
            }
            if (name === 'platform.ui.submit') {
                const context = {};
                if (event.detail.formId) context.formId = event.detail.formId;
                component.actions = { press: { kind: 'event', name, context } };
                return;
            }
            if (name === 'page.navigate') {
                const context = {};
                if (event.detail.pageId) context.pageId = event.detail.pageId;
                component.actions = { press: { kind: 'local', name, context } };
                return;
            }
            component.actions = { press: { kind: 'local', name, context: {} } };
        });
    }

    _dataModel(event) {
        this._mutate(this.t('interface_editor.history_data_model'), (document) => {
            const surface = activeSurface(document);
            surface.data_model = event.detail.dataModel;
        });
    }

    _quickFixSubmit() {
        this._mutate(this.t('interface_editor.history_quick_fix'), (document) => {
            quickFixAddSubmit(document);
        });
    }

    _problemFocus(event) {
        const { componentId, surfaceId } = event.detail;
        if (surfaceId && this.document) {
            const page = Object.values(this.document.pages || {})
                .find((item) => item.root_surface_id === surfaceId);
            if (page && page.page_id !== this.document.active_page_id) {
                this._selectPage({ detail: { pageId: page.page_id } });
            }
        }
        if (componentId) {
            this._editorState.selectComponent({ componentId, additive: false });
        }
    }

    _toolbar(event) {
        const state = this._editorState;
        if (event.type === 'undo') { this._undo(); return; }
        if (event.type === 'redo') { this._redo(); return; }
        if (event.type === 'target-change') { state.setTarget({ target: event.detail.target }); return; }
        if (event.type === 'viewport-change') {
            state.setViewport({
                profile: event.detail.profile,
                ...(Number.isFinite(event.detail.width) ? { width: event.detail.width } : {}),
                ...(Number.isFinite(event.detail.height) ? { height: event.detail.height } : {}),
            });
            return;
        }
        if (event.type === 'zoom-change') { state.setZoom({ zoom: event.detail.zoom }); return; }
        if (event.type === 'grid-toggle') { state.toggleGrid({}); return; }
        if (event.type === 'baseline-toggle') { state.toggleBaseline({}); return; }
        if (event.type === 'rulers-toggle') { state.toggleRulers({}); return; }
        if (event.type === 'guides-toggle') { state.toggleGuides({}); return; }
        if (event.type === 'snap-toggle') { state.toggleSnap({}); return; }
        if (event.type === 'data-flow-toggle') { state.toggleDataFlow({}); return; }
        if (event.type === 'preview-toggle') {
            state.setPreview({ value: !this.editorState.previewMode });
            return;
        }
        if (event.type === 'run-toggle') {
            state.setRunMode({ value: !this.editorState.runMode });
            return;
        }
        if (event.type === 'open-device') {
            this.openModal('flows.preview_share', {
                flowId: this.flowId,
                branchId: this.branchId === 'base' ? 'default' : this.branchId,
            });
            return;
        }
        if (event.type === 'templates-open') {
            this.openModal('flows.interface_template', {
                onApply: (templateId) => this._applyPageTemplate(templateId),
            });
        }
    }

    /** Replace the active page surface with a starter template (one transaction). */
    _applyPageTemplate(templateId) {
        const template = flowUIPageTemplate(templateId);
        this._mutate(this.t('interface_editor.history_template'), (document) => {
            const page = document.pages[document.active_page_id];
            if (!page) {
                throw new Error('flows-interface-editor: active page missing for template apply');
            }
            const surfaceId = page.root_surface_id;
            const built = template.buildSurface(surfaceId, this._locale());
            document.surfaces[surfaceId] = {
                ...clone(built),
                catalog_id: document.catalog_id,
            };
            document.template_version = template.version;
        });
        this._editorState.selectComponent({ componentId: 'root', additive: false });
    }

    _committed(event) {
        const detail = event.detail || {};
        this.parity = {
            status: detail.status || 'Exact',
            fingerprint: detail.fingerprint || '',
            assetsReady: true,
            expectedContext: detail.expectedContext || null,
            actualContext: detail.actualContext || detail.context || null,
            diff: detail.diff || [],
        };
        this._editorState.setMeasuredRevision({ revision: Number(detail.revision || 0) });
    }

    _handleHotkeys(event) {
        const state = this.editorState;
        if (state.previewMode === true || state.runMode === true) return;
        if (event.target && event.target !== document.body
            && event.target.closest?.('input,textarea,select,[contenteditable]')) {
            return;
        }
        const meta = event.metaKey || event.ctrlKey;
        const key = event.key.toLowerCase();
        if (meta && key === 'z') {
            event.preventDefault();
            if (event.shiftKey) this._redo();
            else this._undo();
            return;
        }
        if (meta && key === 'd') {
            event.preventDefault();
            this._duplicateComponent(state.selectedComponentId);
            return;
        }
        if (meta && key === 'c') {
            this._copySelection();
            return;
        }
        if (meta && key === 'v') {
            this._pasteClipboard();
            return;
        }
        if (!meta && (event.key === 'Delete' || event.key === 'Backspace')) {
            event.preventDefault();
            this._deleteSelection();
            return;
        }
        if (!meta && key === 'g') { this._editorState.toggleGrid({}); return; }
        if (!meta && key === 'd') { this._editorState.toggleDataFlow({}); return; }
        if (!meta && key === 'r') { this._editorState.toggleRulers({}); }
    }

    _breadcrumbPath() {
        const surface = this.surface;
        if (!surface) return [];
        const rootId = surface.root_component_id || 'root';
        const path = [];
        let currentId = this.editorState.selectedComponentId;
        while (currentId && surface.components[currentId]) {
            path.unshift(currentId);
            if (currentId === rootId) break;
            currentId = findParentId(surface, currentId);
        }
        return path;
    }

    _tab(panel, labelKey) {
        const active = this.rightPanel === panel;
        return html`<span
            class="tab"
            role="tab"
            tabindex="0"
            aria-selected=${active ? 'true' : 'false'}
            data-active=${active ? 'true' : 'false'}
            @click=${() => { this.rightPanel = panel; }}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this.rightPanel = panel;
                }
            }}
        >${this.t(labelKey)}</span>`;
    }

    _renderBreadcrumb() {
        const path = this._breadcrumbPath();
        if (path.length === 0) return nothing;
        const surface = this.surface;
        return html`<div class="breadcrumb">
            ${path.map((id, index) => html`
                ${index > 0 ? html`<span class="sep">›</span>` : nothing}
                <span
                    class="crumb"
                    role="button"
                    tabindex="0"
                    data-current=${index === path.length - 1 ? 'true' : 'false'}
                    @click=${() => this._editorState.selectComponent({ componentId: id, additive: false })}
                    @keydown=${(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            this._editorState.selectComponent({ componentId: id, additive: false });
                        }
                    }}
                >${surface.components[id]?.type || id}</span>
            `)}
        </div>`;
    }

    _renderFooter(problems) {
        return html`<div class="footer">
            ${this._renderBreadcrumb()}
            <flows-interface-problems-panel
                .problems=${problems}
                @quick-fix-submit=${() => this._quickFixSubmit()}
                @problem-focus=${this._problemFocus}
            ></flows-interface-problems-panel>
        </div>`;
    }

    render() {
        if (!this.document) {
            return html`<div>${this.t('interface_editor.document_unavailable')}</div>`;
        }
        const editorState = this.editorState;
        const problems = validateInterfaceDocument(this.document);
        const blocking = problems.filter((problem) => problem.severity === 'error');
        const selectedIds = editorState.selectedComponentIds || [];
        return html`
            <flows-interface-toolbar
                .state=${editorState}
                .parity=${{
                    exact: this.parity.status === 'Exact',
                    label: this.parity.status === 'Exact'
                        ? this.t('interface_editor.parity_exact')
                        : (this.parity.assetsReady
                            ? this.parity.status
                            : this.t('interface_editor.parity_loading_assets')),
                }}
                .canUndo=${(editorState.history?.past || []).length > 0}
                .canRedo=${(editorState.history?.future || []).length > 0}
                .canPublish=${blocking.length === 0}
                @target-change=${this._toolbar}
                @viewport-change=${this._toolbar}
                @zoom-change=${this._toolbar}
                @grid-toggle=${this._toolbar}
                @baseline-toggle=${this._toolbar}
                @rulers-toggle=${this._toolbar}
                @guides-toggle=${this._toolbar}
                @snap-toggle=${this._toolbar}
                @data-flow-toggle=${this._toolbar}
                @preview-toggle=${this._toolbar}
                @run-toggle=${this._toolbar}
                @open-device=${this._toolbar}
                @templates-open=${this._toolbar}
                @undo=${this._toolbar}
                @redo=${this._toolbar}
            ></flows-interface-toolbar>
            <div class="body">
                <aside class="left">
                    <flows-interface-pages-panel
                        .document=${this.document}
                        @page-select=${this._selectPage}
                        @page-add=${() => this._addPage()}
                        @page-rename=${this._renamePage}
                        @page-duplicate=${this._duplicatePage}
                        @page-delete=${this._deletePage}
                    ></flows-interface-pages-panel>
                    <flows-interface-layers-tree
                        .surface=${this.surface}
                        .selectedIds=${selectedIds}
                        .hoveredId=${editorState.hoveredComponentId}
                        .lockedIds=${editorState.lockedComponentIds}
                        @component-select=${this._selectComponent}
                        @component-hover=${(event) => this._editorState.hoverComponent(event.detail)}
                        @component-rename=${this._renameComponent}
                        @component-visibility=${this._componentVisibility}
                        @component-lock=${(event) => this._editorState.toggleLock(event.detail)}
                        @layers-move=${this._layersMove}
                    ></flows-interface-layers-tree>
                    <flows-interface-palette
                        @component-add=${this._addComponent}
                    ></flows-interface-palette>
                </aside>
                <flows-interface-canvas
                    .document=${this.document}
                    .state=${editorState}
                    .flowId=${this.flowId}
                    .branchId=${this.branchId}
                    @component-select=${this._selectComponent}
                    @component-hover=${(event) => this._editorState.hoverComponent(event.detail)}
                    @canvas-committed=${this._committed}
                    @layout-command=${this._layoutCommand}
                    @component-drop=${this._dropComponent}
                    @component-inline-edit=${this._inlineEdit}
                    @component-duplicate=${(event) => this._duplicateComponent(event.detail.componentId)}
                    @component-copy=${() => this._copySelection()}
                    @component-paste=${(event) => this._pasteClipboard(event.detail.componentId)}
                    @component-wrap=${(event) => this._wrapInSection(event.detail.componentId)}
                    @component-delete-request=${() => this._deleteSelection()}
                    @component-menu-open=${this._openComponentMenu}
                    @guides-change=${(event) => this._editorState.setGuides(event.detail)}
                ></flows-interface-canvas>
                <aside class="right">
                    <div class="tabs" role="tablist">
                        ${this._tab('properties', 'interface_editor.tab_properties')}
                        ${this._tab('data', 'interface_editor.tab_data')}
                    </div>
                    ${this.rightPanel === 'data'
                        ? html`
                            <flows-interface-contract-panel
                                .flowId=${this.flowId}
                                .document=${this.document}
                                .surfaceId=${this.surface?.surface_id || ''}
                                @component-select=${this._selectComponent}
                            ></flows-interface-contract-panel>
                            <flows-interface-data-model-panel
                                .surface=${this.surface}
                                @data-model-change=${this._dataModel}
                            ></flows-interface-data-model-panel>
                        `
                        : html`<flows-interface-inspector
                            .component=${this.selected}
                            .dataModel=${this.surface?.data_model || null}
                            .pages=${Object.values(this.document.pages || {})}
                            .band=${editorState.editBand || 'wide'}
                            .rootId=${this.surface?.root_component_id || 'root'}
                            .selectionCount=${selectedIds.length}
                            .flowId=${this.flowId}
                            @band-change=${(event) => this._editorState.setEditBand(event.detail)}
                            @property-change=${this._propertyChange}
                            @checks-change=${this._checksChange}
                            @placement-patch=${this._placement}
                            @placement-reset=${this._placementReset}
                            @layout-patch=${this._layout}
                            @binding-change=${this._binding}
                            @binding-remove=${this._bindingRemove}
                            @action-change=${this._action}
                            @component-rename=${this._renameComponent}
                            @component-delete=${this._deleteComponent}
                        ></flows-interface-inspector>`}
                </aside>
            </div>
            ${this._renderComponentMenu(editorState)}
            ${this._renderFooter(problems)}
        `;
    }

    _renderComponentMenu(editorState) {
        const menu = this._componentMenu;
        if (!menu) return nothing;
        const component = this.surface?.components?.[menu.componentId] || null;
        if (!component) return nothing;
        const lockedIds = editorState.lockedComponentIds || [];
        return html`<flows-interface-component-menu
            .x=${menu.x}
            .y=${menu.y}
            .component=${component}
            .rootId=${this.surface?.root_component_id || 'root'}
            .locked=${lockedIds.includes(menu.componentId)}
            .locale=${this._locale()}
            @menu-close=${this._closeComponentMenu}
            @property-change=${this._propertyChange}
            @checks-change=${this._checksChange}
            @component-duplicate=${(event) => this._duplicateComponent(event.detail.componentId)}
            @component-copy=${() => this._copySelection()}
            @component-paste=${(event) => this._pasteClipboard(event.detail.componentId)}
            @component-wrap=${(event) => this._wrapInSection(event.detail.componentId)}
            @component-delete-request=${() => this._deleteSelection()}
            @component-visibility=${this._componentVisibility}
            @component-lock=${(event) => this._editorState.toggleLock(event.detail)}
        ></flows-interface-component-menu>`;
    }
}

if (!customElements.get('flows-interface-editor')) {
    customElements.define('flows-interface-editor', FlowsInterfaceEditor);
}

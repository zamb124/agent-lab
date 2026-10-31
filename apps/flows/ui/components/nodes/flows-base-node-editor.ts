/**
 * flows-base-node-editor — общая обёртка редакторов нод.
 *
 * Master-detail layout: sidebar (basic/resources/state) + main (settings/mapping).
 * «Запустить» монтируется в шапку `flows-floating-panel` или `flows-embedded-tool-config-modal`,
 * иначе fallback в `.panel-main`.
 *
 * Эмитит наружу:
 *   - change { nodeId, patch } — patch с top-level полями NodeConfig
 *     (description/tags/incoming_policy/exception_as_response/exception_allow_types/files/resources). Специфичные для типа
 *     патчи приходят через slot='settings' (дочерний редактор сам диспатчит
 *     change на хосте).
 *
 * Секция «Закреплённые ресурсы» не показывается для ноды `resource`: на графе это
 * уже ресурс, вложенные закрепления с той же ноды не редактируются.
 */

import type { OpController, ResourceController, SliceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '../editors/flows-state-mapping-editor.js';
import '@platform/lib/components/platform-json-editor.js';
import { FlowsNodeRunControl } from '../flows-node-run-control.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/fields/platform-field-shell.js';
import '@platform/lib/components/platform-empty-state.js';
import { fieldPillStyles } from '@platform/lib/styles/shared/field-pill.styles.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import {
    nextTestRunClientId,
} from '../../_helpers/flows-test-run-gate.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    findNodeTestRunHandlers,
    listNodeTestRunHandlers,
    resolveNodeTestRunHandler,
} from '../../_helpers/node-test-run-registry.js';
import { uniquePinnedResourceType } from '../../_helpers/flows-branch-resource.js';
import { buildFlowAssetFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

function pinnedResourceId(ref: unknown, key: string): string {
    if (isPlainObject(ref) && typeof ref.resource_id === 'string') return ref.resource_id;
    return key;
}

function llmOverrideRecord(value: unknown): Record<string, unknown> {
    return isPlainObject(value) ? { ...value } : {};
}

type HelpHintElement = HTMLElement & {
    size: string;
    label: string;
    text: string;
};

function isHelpHintElement(value: HTMLElement): value is HelpHintElement {
    return 'size' in value && 'label' in value && 'text' in value;
}

function recordText(row: Record<string, unknown>, key: string): string {
    const value = row[key];
    return typeof value === 'string' ? value : '';
}

function mappingSource(row: Record<string, unknown>): string {
    const sourcePath = recordText(row, 'source_path');
    if (sourcePath.length > 0) return sourcePath;
    return recordText(row, 'source');
}

function catalogRow(catalog: readonly unknown[], resourceId: string): Record<string, unknown> | null {
    for (const row of catalog) {
        if (!isPlainObject(row)) continue;
        if (row.resource_id === resourceId) return row;
    }
    return null;
}

export class FlowsBaseNodeEditor extends PlatformElement {
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
        /** Редактирование вложенного tool: без смены node id */
        embedded: { type: Boolean, reflect: true },
        /** Agent Focus Studio: full-bleed секции без floating chrome */
        focusMode: { type: Boolean, reflect: true },
        /** Секция studio: prompt | model | skills_tools | advanced */
        focusSection: { type: String },
        _stateDraft: { state: true },
        _mappingTab: { state: true },
        _mappingSyncNonce: { state: true },
        _addResourcePick: { state: true },
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
    declare focusMode: boolean;
    declare focusSection: string;
    declare _stateDraft: string | null;
    declare _mappingTab: string;
    declare _mappingSyncNonce: number;
    declare _addResourcePick: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        fieldPillStyles,
        panelShellStyles,
        css`
            :host {
                display: block;
                color: var(--text-primary);
                height: 100%;
                min-height: 0;
                box-sizing: border-box;
            }

            .panel-layout {
                display: grid;
                grid-template-columns: 320px 1fr;
                gap: 0;
                height: 100%;
                min-height: 0;
            }
            :host([focusMode]) .panel-layout.focus-single {
                grid-template-columns: minmax(0, 1fr);
            }
            :host([focusMode]) .panel-layout.focus-advanced {
                grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
            }
            :host([focusMode]) .panel-main.focus-main {
                padding: 0;
            }
            :host([focusMode]) .panel-main.focus-main .section {
                height: 100%;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            :host([focusMode]) .panel-main.focus-main .section slot,
            :host([focusMode]) .panel-main.focus-main ::slotted([slot='settings']) {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .panel-sidebar {
                overflow: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
            }
            .panel-main {
                overflow: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
                min-height: 0;
            }
            :host([focusMode]) .panel-main {
                overflow: visible;
            }
            :host([focusMode]) .panel-main.focus-main {
                overflow: auto;
                padding-bottom: var(--space-8);
            }
            .panel-main > .section {
                flex-shrink: 0;
            }

            /* Секции */
            .section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
            .panel-run-fallback:empty { display: none; }
            .panel-run-fallback:not(:empty) {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                padding-bottom: var(--space-2);
                margin-bottom: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }
            /* form fields */
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }
            .field-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .exception-response-head {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .exception-response-head platform-switch {
                margin-left: auto;
            }
            .field-pill-file-ref-open {
                min-width: 0;
                flex: 1 1 auto;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border: 0;
                background: transparent;
                padding: 0;
                color: inherit;
                font: inherit;
                text-align: left;
                cursor: pointer;
            }

            /* Списки файлов и ресурсов */
            .item-list {
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .item-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
            }
            .item-row .grow {
                flex: 1; min-width: 0;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .item-row .meta {
                color: var(--text-tertiary); font-size: var(--text-xs);
            }
            input[type="file"] { display: none; }

            .mapping-tabs {
                display: flex; gap: var(--space-1); margin-bottom: var(--space-2);
            }
            .dataflow-mapping-shell {
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
            }
            .dataflow-mapping-shell .section-title {
                margin-bottom: var(--space-2);
            }
            .dataflow-mapping-grid {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .dataflow-mapping-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .dataflow-mapping-head .section-title {
                margin-bottom: 0;
            }
            .dataflow-mapping-head .mapping-tabs {
                margin-bottom: 0;
            }
            .dataflow-mapping-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding-top: var(--space-1);
                border-top: 1px solid var(--border-subtle);
            }
            .dataflow-lanes {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: var(--space-2);
            }
            .dataflow-lane {
                min-width: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: var(--bg-elevated);
                padding: var(--space-2);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .dataflow-lane-title {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .dataflow-list {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }
            .dataflow-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
                align-items: center;
                gap: 6px;
                min-width: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                animation: dataflow-chip-in 160ms var(--easing-smooth, ease-out) both;
            }
            .dataflow-row .arrow {
                color: var(--text-tertiary);
            }
            .dataflow-chip {
                min-width: 0;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                max-width: 100%;
                padding: 3px 7px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                line-height: 1.2;
                animation: dataflow-chip-in 160ms var(--easing-smooth, ease-out) both;
            }
            article.dataflow-chip {
                appearance: none;
                font: inherit;
                text-align: left;
                cursor: pointer;
                margin: 0;
            }
            article.dataflow-chip:hover,
            article.dataflow-chip:focus-visible {
                color: var(--accent);
                border-color: color-mix(in oklab, var(--accent) 34%, var(--border-subtle));
                background: var(--accent-subtle);
                outline: none;
            }
            .dataflow-chip .label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .dataflow-chip .type {
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            .dataflow-chip[data-status="missing"],
            .dataflow-chip[data-severity="error"] {
                color: var(--error);
                border-color: color-mix(in oklab, var(--error) 36%, var(--border-subtle));
                background: color-mix(in oklab, var(--error) 10%, var(--glass-solid-subtle));
            }
            .dataflow-chip[data-severity="warning"] {
                color: var(--warning);
                border-color: color-mix(in oklab, var(--warning) 36%, var(--border-subtle));
                background: color-mix(in oklab, var(--warning) 10%, var(--glass-solid-subtle));
            }
            .dataflow-empty {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.35;
            }
            .dataflow-issues {
                display: flex;
                flex-direction: column;
                gap: 6px;
                margin-top: var(--space-1);
            }
            .dataflow-issue {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.35;
                padding-left: var(--space-2);
                border-left: 2px solid var(--border-subtle);
            }
            .dataflow-issue[data-severity="warning"] {
                border-left-color: var(--warning);
            }
            .dataflow-issue[data-severity="error"] {
                border-left-color: var(--error);
            }
            @keyframes dataflow-chip-in {
                from {
                    opacity: 0;
                    transform: translateY(3px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            @media (prefers-reduced-motion: reduce) {
                .dataflow-row,
                .dataflow-chip {
                    animation: none;
                }
            }
            @media (max-width: 720px) {
                .dataflow-lanes {
                    grid-template-columns: minmax(0, 1fr);
                }
            }

        `,
    ];
    private _fileUpload: OpController;
    private _ragNodeTest: ControllerFor<'flows/rag_node_test'> | null;
    private _exceptionAbsorbAllowNamesOp: OpController;
    private _executionLimitsOp: OpController;
    private _resources: ResourceController;
    private _flowEditor: OpController;
    private _testRunOps: Map<string, OpController>;
    private _nodeRunControlEl: FlowsNodeRunControl | null;
    private _panelHeaderHintEl: HelpHintElement | null;
    private _onNodeRunFired: () => void;
    private _onNodeRunOpenFullEvent: (event: Event) => void;
    private _testRunClientId: string;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.flowNodeType = '';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this.focusMode = false;
        this.focusSection = 'prompt';
        this._mappingTab = 'input';
        this._mappingSyncNonce = 0;
        this._stateDraft = null;
        this._addResourcePick = '';
        this._fileUpload = this.useOp('platform/file_create');
        this._testRunOps = new Map();
        this._ragNodeTest = null;
        for (const handler of listNodeTestRunHandlers()) {
            if (!this._testRunOps.has(handler.opName)) {
                this._testRunOps.set(handler.opName, this.useOp(handler.opName));
            }
        }
        if (this._testRunOps.has('rag/search')) {
            this._ragNodeTest = this.useSlice('flows/rag_node_test');
        }
        this._exceptionAbsorbAllowNamesOp = this.useOp('flows/exception_absorb_allow_names');
        this._executionLimitsOp = this.useOp('flows/execution_limits');
        this._testRunClientId = nextTestRunClientId();
        this._resources = this.useResource('flows/resources', { autoload: true });
        this._flowEditor = this.useOp('flows/editor');
        this._nodeRunControlEl = null;
        this._panelHeaderHintEl = null;
        this._onNodeRunFired = () => { void this._runNodeTest(); };
        this._onNodeRunOpenFullEvent = (event: Event) => { this._onOpenExecuteFull(event); };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._exceptionAbsorbAllowNamesOp.run({});
        void this._executionLimitsOp.run({});
        queueMicrotask(() => this._placeNodeRunControl());
        requestAnimationFrame(() => this._placeNodeRunControl());
    }

    override disconnectedCallback(): void {
        if (this._nodeRunControlEl) {
            this._nodeRunControlEl.removeEventListener('run', this._onNodeRunFired);
            this._nodeRunControlEl.removeEventListener('open-full', this._onNodeRunOpenFullEvent);
            this._nodeRunControlEl.remove();
            this._nodeRunControlEl = null;
        }
        if (this._panelHeaderHintEl) {
            this._panelHeaderHintEl.remove();
            this._panelHeaderHintEl = null;
        }
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        this._placeNodeRunControl();
    }

    _ensureNodeRunControl() {
        if (this._nodeRunControlEl) {
            return this._nodeRunControlEl;
        }
        const el = document.createElement('flows-node-run-control');
        if (!(el instanceof FlowsNodeRunControl)) {
            throw new Error('flows-base-node-editor: flows-node-run-control is not registered');
        }
        el.requestClientId = this._testRunClientId;
        el.addEventListener('run', this._onNodeRunFired);
        el.addEventListener('open-full', this._onNodeRunOpenFullEvent);
        this._nodeRunControlEl = el;
        return el;
    }

    _ensurePanelHeaderHint() {
        if (this._panelHeaderHintEl) {
            return this._panelHeaderHintEl;
        }
        const hint = document.createElement('platform-help-hint');
        if (!isHelpHintElement(hint)) {
            throw new Error('flows-base-node-editor: platform-help-hint required');
        }
        this._panelHeaderHintEl = hint;
        return hint;
    }

    _syncPanelHeaderHintProps() {
        const hint = this._panelHeaderHintEl;
        if (!hint) {
            return;
        }
        if (this.flowNodeType === 'resource') {
            hint.size = '';
            hint.label = this.t('resource_node_editor.help_label');
            hint.text = this.t('resource_node_editor.help_body');
            return;
        }
        if (this.flowNodeType === 'external_api') {
            hint.size = 'md';
            hint.label = this.t('external_api_editor.help_label');
            hint.text = this.t('external_api_editor.contract_hint');
            return;
        }
        throw new Error(`flows-base-node-editor: panel header hint only for resource or external_api, got "${this.flowNodeType}"`);
    }

    _testRunMatchCtx() {
        const nodeType = typeof this.flowNodeType === 'string' ? this.flowNodeType : '';
        if (nodeType.length === 0) {
            return null;
        }
        const editorState = this._flowEditor.state;
        const catalogItems = this._resources.items;
        if (!Array.isArray(catalogItems)) {
            throw new Error('flows-base-node-editor: resources.items array required');
        }
        const resourceType = nodeType === 'resource' && isPlainObject(editorState)
            ? uniquePinnedResourceType(this.nodeConfig, editorState, catalogItems)
            : null;
        return { nodeType, resourceType, editorState, catalogItems };
    }

    _syncNodeRunControlProps() {
        const el = this._nodeRunControlEl;
        if (!el) {
            return;
        }
        el.requestClientId = this._testRunClientId;
        const matchCtx = this._testRunMatchCtx();
        if (matchCtx === null) {
            el.viewModel = null;
            el.busy = false;
            return;
        }
        const matches = findNodeTestRunHandlers(matchCtx);
        if (matches.length === 0) {
            el.viewModel = null;
            el.busy = false;
            return;
        }
        if (matches.length !== 1) {
            throw new Error(
                `flows-base-node-editor: expected 0 or 1 test-run handler, got ${matches.length}`,
            );
        }
        const handler = matches[0];
        const op = this._testRunOps.get(handler.opName);
        if (!op) {
            throw new Error(`flows-base-node-editor: op ${handler.opName} not bound in constructor`);
        }
        el.viewModel = handler.formatViewModel({
            op,
            nodeId: this.nodeId,
            nodeTest: this._ragNodeTest === null ? null : this._ragNodeTest.value,
            t: (key: string, vars?: Record<string, string | number>) => this.t(key, vars),
        });
        el.busy = handler.busyOf(op);
    }

    /**
     * `closest` не везде поднимается сквозь границы вложенных shadow root; до flows-floating-panel
     * идём вручную: parent, либо ShadowRoot -> host.
     */
    _ancestorNamed(name: string): Element | null {
        let current: Node | null = this;
        for (let depth = 0; depth < 128; depth += 1) {
            if (current === null) return null;
            if (current instanceof Element && current.nodeName === name) return current;
            const parent: Node | null = current.parentNode;
            if (parent instanceof ShadowRoot) {
                current = parent.host;
            } else {
                current = parent;
            }
        }
        return null;
    }

    _findFlowsFloatingPanel() {
        return this._ancestorNamed('FLOWS-FLOATING-PANEL');
    }

    _floatingPanelHeaderRunHost(panel: Element) {
        const root = panel.shadowRoot;
        if (root === null) return null;
        return root.querySelector('.header-actions-host');
    }

    /**
     * Редактор вложенного tool (модалка с canvas): play в шапке модалки, не в теле редактора.
     */
    _findEmbeddedToolConfigModal() {
        return this._ancestorNamed('FLOWS-EMBEDDED-TOOL-CONFIG-MODAL');
    }

    _embeddedToolModalHeaderRunHost(modal: Element) {
        const root = modal.shadowRoot;
        if (root === null) return null;
        return root.querySelector('.embedded-tool-run-host');
    }

    /**
     * Agent Focus Studio: play в chrome studio, не в теле редактора.
     */
    _findAgentFocusStudio() {
        return this._ancestorNamed('FLOWS-AGENT-FOCUS-STUDIO');
    }

    _agentFocusStudioRunHost(studio: Element) {
        const root = studio.shadowRoot;
        if (root === null) return null;
        return root.querySelector('.studio-run-host');
    }

    _placeNodeRunControl() {
        if (!this.nodeConfig) {
            return;
        }
        if (!this.isConnected) {
            return;
        }
        const el = this._ensureNodeRunControl();
        this._syncNodeRunControlProps();
        const panel = this._findFlowsFloatingPanel();
        const embeddedModal = this._findEmbeddedToolConfigModal();
        const studio = this._findAgentFocusStudio();
        const hostFromPanel = panel ? this._floatingPanelHeaderRunHost(panel) : null;
        const hostFromEmbedded = embeddedModal ? this._embeddedToolModalHeaderRunHost(embeddedModal) : null;
        const hostFromStudio = studio ? this._agentFocusStudioRunHost(studio) : null;
        let target = null;
        if (hostFromStudio) {
            target = hostFromStudio;
        } else if (hostFromPanel) {
            target = hostFromPanel;
        } else if (hostFromEmbedded) {
            target = hostFromEmbedded;
        } else {
            const root = this.renderRoot;
            target = root === undefined || root === null || typeof root.querySelector !== 'function'
                ? null
                : root.querySelector('[data-node-run-fallback="panel-main"]');
        }
        if (!target) {
            if (this._panelHeaderHintEl) {
                this._panelHeaderHintEl.remove();
                this._panelHeaderHintEl = null;
            }
            return;
        }
        if (el.parentElement !== target) {
            target.appendChild(el);
        }
        if (this.flowNodeType === 'resource' || this.flowNodeType === 'external_api') {
            const hint = this._ensurePanelHeaderHint();
            this._syncPanelHeaderHintProps();
            target.insertBefore(hint, el);
        } else if (this._panelHeaderHintEl) {
            this._panelHeaderHintEl.remove();
            this._panelHeaderHintEl = null;
        }
    }

    _nodeConfigForPayload() {
        const cfg: Record<string, unknown> = { ...asObject(this.nodeConfig) };
        if (isPlainObject(cfg.llm_override)) {
            cfg.llm = { ...cfg.llm_override };
        }
        delete cfg.llm_override;
        return cfg;
    }

    async _runNodeTest() {
        const matchCtx = this._testRunMatchCtx();
        if (matchCtx === null) {
            throw new Error('flows-base-node-editor: nodeType required for test-run');
        }
        const handler = resolveNodeTestRunHandler(matchCtx);
        const op = this._testRunOps.get(handler.opName);
        if (!op) {
            throw new Error(`flows-base-node-editor: op ${handler.opName} not bound in constructor`);
        }
        await handler.run({
            host: this,
            op,
            requestClientId: this._testRunClientId,
            matchCtx,
        });
    }

    _onOpenExecuteFull(event: Event) {
        if (!(event instanceof CustomEvent)) {
            throw new Error('flows-base-node-editor: open-full event requires CustomEvent');
        }
        const d = event.detail;
        if (!d || typeof d.value !== 'object' || d.value === null) {
            throw new Error('flows-base-node-editor: open-full event requires detail.value object');
        }
        this.openModal('flows.raw_json', { value: d.value });
    }

    _emitPatch(patch: Record<string, unknown>) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _stringArrayFromChangeDetail(event: CustomEvent, ctx: string) {
        const d = event.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`${ctx}: change detail object required`);
        }
        if (!('value' in d)) {
            throw new Error(`${ctx}: detail.value required`);
        }
        if (!Array.isArray(d.value)) {
            throw new Error(`${ctx}: detail.value must be array`);
        }
        const out = [];
        for (let i = 0; i < d.value.length; i += 1) {
            if (typeof d.value[i] !== 'string') {
                throw new Error(`${ctx}: detail.value[${i}] must be string`);
            }
            out.push(d.value[i]);
        }
        return out;
    }

    _onDescription(e: CustomEvent) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._emitPatch({ description: v });
    }

    _onName(e: CustomEvent) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value.trim() : '';
        if (v.length === 0) {
            this.requestUpdate();
            return;
        }
        this._emitPatch({ name: v });
    }
    _onTags(e: CustomEvent) {
        this._emitPatch({ tags: this._stringArrayFromChangeDetail(e, 'flows-base-node-editor:tags') });
    }
    _onPolicy(e: CustomEvent) {
        const raw = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        const v = raw === 'all' ? 'all' : 'any';
        this._emitPatch({ incoming_policy: v });
    }

    _onNodeTimeout(e: CustomEvent) {
        let raw = '';
        const dv = e.detail ? e.detail.value : undefined;
        if (typeof dv === 'number' && Number.isFinite(dv)) {
            raw = String(Math.trunc(dv));
        } else if (typeof dv === 'string') {
            raw = dv.trim();
        }
        if (raw === '') {
            this._emitPatch({ node_timeout_seconds: null });
            return;
        }
        const n = parseInt(raw, 10);
        if (!Number.isFinite(n) || n < 1) {
            return;
        }
        this._emitPatch({ node_timeout_seconds: Math.min(n, 3600) });
    }

    _graphMaxIterationsCap() {
        const op = this._executionLimitsOp;
        const raw = op.lastResult;
        if (raw === null) {
            return null;
        }
        if (!isPlainObject(raw) || typeof raw.graph_max_iterations !== 'number') {
            throw new Error('flows-base-node-editor: execution limits response invalid');
        }
        return raw.graph_max_iterations;
    }

    _onMaxVisitsPerRun(e: CustomEvent) {
        const cap = this._graphMaxIterationsCap();
        if (cap === null) {
            return;
        }
        let raw = '';
        const dv = e.detail ? e.detail.value : undefined;
        if (typeof dv === 'number' && Number.isFinite(dv)) {
            raw = String(Math.trunc(dv));
        } else if (typeof dv === 'string') {
            raw = dv.trim();
        }
        if (raw === '') {
            this._emitPatch({ max_visits_per_run: null });
            return;
        }
        const n = parseInt(raw, 10);
        if (!Number.isFinite(n) || n < 1) {
            return;
        }
        this._emitPatch({ max_visits_per_run: Math.min(n, cap) });
    }

    _onExceptionAsResponse(e: CustomEvent) {
        const v = e.detail && typeof e.detail === 'object' && 'value' in e.detail ? e.detail.value : undefined;
        if (typeof v !== 'boolean') {
            throw new Error('flows-base-node-editor: platform-switch must emit detail.value boolean');
        }
        if (v) {
            this._emitPatch({ exception_as_response: true });
            return;
        }
        this._emitPatch({ exception_as_response: false, exception_allow_types: [] });
    }

    _exceptionAbsorbAllowNamesList() {
        const op = this._exceptionAbsorbAllowNamesOp;
        const raw = op.lastResult;
        if (raw === null) {
            return null;
        }
        if (!isPlainObject(raw) || !Array.isArray(raw.items)) {
            throw new Error('flows-base-node-editor: exception-absorb-allow-names lastResult.items must be an array');
        }
        if (raw.items.length === 0) {
            throw new Error('flows-base-node-editor: exception-absorb-allow-names must be non-empty');
        }
        const names: string[] = [];
        for (const item of raw.items) {
            if (typeof item !== 'string') {
                throw new Error('flows-base-node-editor: exception-absorb-allow-names item must be a string');
            }
            names.push(item);
        }
        return names;
    }

    _renderExceptionAllowTypesControls(cfg: Record<string, unknown>) {
        const op = this._exceptionAbsorbAllowNamesOp;
        const allowNames = this._exceptionAbsorbAllowNamesList();
        if (allowNames === null) {
            if (typeof op.error === 'string' && op.error.length > 0) {
                return html`<div class="field-hint">${op.error}</div>`;
            }
            return html`<platform-spinner></platform-spinner>`;
        }
        return html`
            <platform-field
                type="array"
                mode="edit"
                .label=${this.t('base_node_editor.exception_allow_types')}
                .hint=${this.t('base_node_editor.exception_allow_types_hint')}
                .value=${Array.isArray(cfg?.exception_allow_types) ? cfg.exception_allow_types : []}
                .config=${{ allowed_values: allowNames }}
                .placeholder=${this.t('base_node_editor.exception_allow_types_placeholder')}
                @change=${this._onExceptionAllowTypes}
            ></platform-field>
        `;
    }

    _onExceptionAllowTypes(e: CustomEvent) {
        this._emitPatch({
            exception_allow_types: this._stringArrayFromChangeDetail(e, 'flows-base-node-editor:exception_allow_types'),
        });
    }
    _onMapping(field: string, event: CustomEvent) {
        const detail = event.detail;
        // platform-field внутри mapping-editor тоже шлёт bubbled `change` с detail.value —
        // реагируем только на emit редактора { mapping }.
        if (!isPlainObject(detail) || !Object.prototype.hasOwnProperty.call(detail, 'mapping')) {
            return;
        }
        event.stopPropagation();
        const mapping = detail.mapping;
        this._emitPatch({ [field]: isPlainObject(mapping) ? mapping : {} });
    }

    async _onUploadFile(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement)) return;
        const file = input.files?.[0];
        if (!file) return;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            throw new Error('flows-base-node-editor: flowId required for file upload');
        }
        const spec = buildFlowAssetFileCreateSpecJson({ flowId: this.flowId });
        const result = await this._fileUpload.run({ file, spec });
        if (!isPlainObject(result) || typeof result.file_id !== 'string') {
            throw new Error('flows-base-node-editor: platform/file_create must return result.file_id');
        }
        if (typeof result.original_name !== 'string' || result.original_name === '') {
            throw new Error('flows-base-node-editor: platform/file_create must return result.original_name');
        }
        if (typeof result.content_type !== 'string' || result.content_type === '') {
            throw new Error('flows-base-node-editor: platform/file_create must return result.content_type');
        }
        if (typeof result.file_size !== 'number') {
            throw new Error('flows-base-node-editor: platform/file_create must return result.file_size');
        }
        if (typeof result.url !== 'string' || result.url === '') {
            throw new Error('flows-base-node-editor: platform/file_create must return result.url');
        }
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        const next = [...files, {
            file_id: result.file_id,
            original_name: result.original_name,
            url: result.url,
            content_type: result.content_type,
            file_size: result.file_size,
        }];
        this._emitPatch({ files: next });
        input.value = '';
    }

    _onRemoveFile(idx: number) {
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        this._emitPatch({ files: files.filter((_, i) => i !== idx) });
    }

    _flowBranchResources() {
        const st = asObject(this._flowEditor.state);
        const bd = st.branchData;
        if (!isPlainObject(bd) || !isPlainObject(bd.resources)) {
            return {};
        }
        return bd.resources;
    }

    /**
     * @param {object | null} refRaw
     * @param {{ resource_id?: string, name?: string, type?: string }[]} catalog
     */
    _branchRefIsLlm(refRaw: unknown, catalog: readonly unknown[]) {
        if (!isPlainObject(refRaw)) {
            return false;
        }
        const inlineType = typeof refRaw.type === 'string' ? refRaw.type.trim() : '';
        if (inlineType === 'llm') {
            return true;
        }
        const rid = typeof refRaw.resource_id === 'string' ? refRaw.resource_id.trim() : '';
        if (rid.length === 0) {
            return false;
        }
        const def = catalogRow(catalog, rid);
        return def !== null && def.type === 'llm';
    }

    /**
     * @param {string} key
     * @param {object} refRaw
     * @param {{ resource_id?: string, name?: string, type?: string }[]} catalog
     */
    _branchRefAttachLabel(key: string, refRaw: unknown, catalog: readonly unknown[]) {
        if (!isPlainObject(refRaw)) {
            return key;
        }
        const rid = typeof refRaw.resource_id === 'string' ? refRaw.resource_id.trim() : '';
        let title = '';
        if (rid.length > 0) {
            const def = catalogRow(catalog, rid);
            title = def && typeof def.name === 'string' && def.name.length > 0 ? def.name.trim() : rid;
        } else {
            const inlineName = typeof refRaw.name === 'string' ? refRaw.name.trim() : '';
            title = inlineName.length > 0 ? inlineName : '';
        }
        const typePart = 'llm';
        const redundantTitle = !title
            || title === key
            || title.toLowerCase() === typePart;
        if (redundantTitle) {
            return `${key} · ${typePart}`;
        }
        return `${title} · ${typePart} · ${key}`;
    }

    /**
     * @param {Record<string, object>} flowRes
     * @param {Record<string, object>} resources
     * @param {string} presetKey
     * @param {{ resource_id?: string, name?: string, type?: string }[]} catalog
     * @returns {{ value: string, label: string }[]}
     */
    _llmBranchAttachOptions(flowRes: Record<string, unknown>, resources: Record<string, unknown>, presetKey: unknown, catalog: readonly unknown[]) {
        /** @type {{ value: string, label: string }[]} */
        const out = [];
        const pk = typeof presetKey === 'string' ? presetKey.trim() : '';
        for (const [key, refRaw] of Object.entries(flowRes)) {
            if (typeof key !== 'string' || key.length === 0) {
                continue;
            }
            if (!this._branchRefIsLlm(refRaw, catalog)) {
                continue;
            }
            if (pk.length > 0 && pk === key) {
                continue;
            }
            if (Object.prototype.hasOwnProperty.call(resources, key)) {
                continue;
            }
            out.push({
                value: key,
                label: this._branchRefAttachLabel(key, refRaw, catalog),
            });
        }
        return out;
    }

    _onAddResource(e: CustomEvent) {
        const resourceId = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._addResourcePick = '';
        if (resourceId.length === 0) return;
        const resourceBag = this.nodeConfig?.resources;
        const resources: Record<string, unknown> = isPlainObject(resourceBag) ? { ...resourceBag } : {};
        if (resources[resourceId] !== undefined) return;
        const catalog = Array.isArray(this._resources.items) ? this._resources.items : [];
        const flowRes = this._flowBranchResources();
        const patch: Record<string, unknown> = {};
        const dropPinnedLlm = (next: Record<string, unknown>) => {
            for (const [key, ref] of Object.entries(next)) {
                const rid = pinnedResourceId(ref, key);
                const row = catalogRow(catalog, rid);
                if (row !== null && row.type === 'llm') delete next[key];
            }
        };

        if (
            this.flowNodeType === 'llm_node'
            && Object.prototype.hasOwnProperty.call(flowRes, resourceId)
            && this._branchRefIsLlm(flowRes[resourceId], catalog)
        ) {
            const next = { ...resources };
            dropPinnedLlm(next);
            patch.resources = next;
            const ov = llmOverrideRecord(
                this.nodeConfig?.llm && typeof this.nodeConfig.llm === 'object'
                    ? this.nodeConfig.llm
                    : this.nodeConfig?.llm_override,
            );
            ov.llm_resource_key = resourceId;
            patch.llm = ov;
            this._emitPatch(patch);
            return;
        }

        const def = catalogRow(catalog, resourceId);

        if (this.flowNodeType === 'llm_node' && def !== null && def.type === 'llm') {
            const next = { ...resources };
            dropPinnedLlm(next);
            next[resourceId] = { resource_id: resourceId };
            patch.resources = next;
            const ov = llmOverrideRecord(
                this.nodeConfig?.llm && typeof this.nodeConfig.llm === 'object'
                    ? this.nodeConfig.llm
                    : this.nodeConfig?.llm_override,
            );
            ov.llm_resource_key = resourceId;
            patch.llm = ov;
        } else {
            patch.resources = { ...resources, [resourceId]: { resource_id: resourceId } };
        }
        this._emitPatch(patch);
    }

    _onRemoveResource(key: string) {
        const resourceBag = this.nodeConfig?.resources;
        const resources: Record<string, unknown> = isPlainObject(resourceBag) ? { ...resourceBag } : {};
        const next = { ...resources };
        delete next[key];
        const patch: Record<string, unknown> = { resources: next };
        const ov = llmOverrideRecord(
            this.nodeConfig?.llm && typeof this.nodeConfig.llm === 'object'
                ? this.nodeConfig.llm
                : this.nodeConfig?.llm_override,
        );
        const presetRaw = ov.llm_resource_key;
        const presetKey = typeof presetRaw === 'string' ? presetRaw.trim() : '';
        if (presetKey === key) {
            delete ov.llm_resource_key;
            patch.llm = Object.keys(ov).length > 0 ? ov : null;
        }
        const contextPreset = typeof this.nodeConfig?.llm_context_resource_key === 'string'
            ? this.nodeConfig.llm_context_resource_key.trim()
            : '';
        if (contextPreset === key) {
            patch.llm_context_resource_key = null;
        }
        this._emitPatch(patch);
    }

    _incomingPolicyEnumConfig() {
        return {
            values: [
                { value: 'any', label: this.t('base_node_editor.incoming_policy_any') },
                { value: 'all', label: this.t('base_node_editor.incoming_policy_all') },
            ],
        };
    }

    _resourceAddEnumConfig(availableResources: unknown, branchAttachOptions: unknown) {
        const values = [{ value: '', label: this.t('base_node_editor.resources_add_pick') }];
        if (!Array.isArray(availableResources)) {
            throw new Error('flows-base-node-editor: _resourceAddEnumConfig expects array');
        }
        const branchByValue = new Map();
        if (Array.isArray(branchAttachOptions)) {
            for (const o of branchAttachOptions) {
                if (!o || typeof o.value !== 'string' || o.value.length === 0 || typeof o.label !== 'string') {
                    throw new Error('flows-base-node-editor: invalid branch attach option');
                }
                branchByValue.set(o.value, o);
            }
        }
        for (const r of availableResources) {
            if (!r || typeof r.resource_id !== 'string' || r.resource_id.length === 0) {
                throw new Error('flows-base-node-editor: invalid resource item');
            }
            if (branchByValue.has(r.resource_id)) {
                continue;
            }
            const nm = typeof r.name === 'string' ? r.name : r.resource_id;
            const tp = typeof r.type === 'string' ? r.type : '';
            values.push({
                value: r.resource_id,
                label: `${nm} · ${tp}`,
            });
        }
        if (branchByValue.size > 0) {
            for (const o of branchByValue.values()) {
                values.push({ value: o.value, label: o.label });
            }
        }
        return { values };
    }

    _stateValue() {
        if (typeof this._stateDraft === 'string') return this._stateDraft;
        const preview = this.previewExecutionState;
        if (!preview) return '{}';
        return formatJsonPretty(preview);
    }

    _onStateChange(e: CustomEvent) {
        const v = e.detail?.value;
        if (typeof v === 'string') this._stateDraft = v;
    }

    _onStateReset() {
        this._stateDraft = null;
        this.requestUpdate();
    }

    _renderBasic() {
        const cfg = this.nodeConfig;
        const description = typeof cfg?.description === 'string' ? cfg.description : '';
        const tags = Array.isArray(cfg?.tags) ? cfg.tags : [];
        const policy = cfg?.incoming_policy === 'all' ? 'all' : 'any';
        const files = Array.isArray(cfg?.files) ? cfg.files : [];
        const visitsCap = this._graphMaxIterationsCap();
        const idLabel = this.t('base_node_editor.node_id');
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_basic')}</div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="view"
                        .label=${idLabel}
                        .hint=${this.t('base_node_editor.node_id_hint')}
                        .value=${this.nodeId}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('base_node_editor.name')}
                        .hint=${this.t('base_node_editor.name_hint')}
                        .placeholder=${this.t('base_node_editor.name_placeholder')}
                        .value=${typeof cfg?.name === 'string' ? cfg.name : ''}
                        @change=${this._onName}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('base_node_editor.description')}
                        .hint=${this.t('base_node_editor.description_help')}
                        .placeholder=${this.t('base_node_editor.description_hint')}
                        .value=${description}
                        @change=${this._onDescription}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="array"
                        mode="edit"
                        .label=${this.t('base_node_editor.tags')}
                        .hint=${this.t('base_node_editor.tags_hint')}
                        .placeholder=${this.t('tag_input.placeholder')}
                        .value=${tags}
                        .config=${{ preserve_case: true }}
                        @change=${this._onTags}
                    ></platform-field>
                </div>
                ${this.flowNodeType === 'resource' ? nothing : html`
                <div class="field">
                    <platform-field-shell
                        .label=${this.t('base_node_editor.files_section')}
                        .hint=${this.t('base_node_editor.files_section_hint')}
                        floated
                    >
                        <div class="field-pill-file-refs-body">
                            ${files.length === 0
                                ? html`<p class="field-pill-empty">${this.t('base_node_editor.files_empty')}</p>`
                                : files.map((f, i) => {
                                    const fname = typeof f.original_name === 'string' && f.original_name !== '' ? f.original_name : f.file_id;
                                    const fmime = typeof f.content_type === 'string' ? f.content_type : '';
                                    const fsize = formatFileSize(f.file_size);
                                    return html`
                                        <div class="field-pill-file-ref-row">
                                            <article
                                                class="field-pill-file-ref-open"
                                                tabindex="0"
                                                role="button"
                                                @click=${() => this.openFile({
                                                    file_id: f.file_id,
                                                    original_name: fname,
                                                    content_type: fmime,
                                                    file_size: f.file_size,
                                                    url: typeof f.url === 'string' ? f.url : '',
                                                }, { source: 'flows_node_file_ref' })}
                                                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this.openFile({
                                                    file_id: f.file_id,
                                                    original_name: fname,
                                                    content_type: fmime,
                                                    file_size: f.file_size,
                                                    url: typeof f.url === 'string' ? f.url : '',
                                                }, { source: 'flows_node_file_ref' }))}
                                            >
                                                <platform-icon
                                                    class="field-pill-file-ref-icon"
                                                    file-icon
                                                    name=${resolveFileIconKey(fname, fmime)}
                                                    size="22"
                                                ></platform-icon>
                                                <div class="field-pill-file-ref-info">
                                                    <span class="field-pill-file-ref-line" title=${fname}>
                                                        <span class="field-pill-file-ref-name">${fname}</span>
                                                        ${fsize
                                                            ? html`
                                                                <span class="field-pill-file-ref-sep">\u00a0\u00b7\u00a0</span>
                                                                <span class="field-pill-file-ref-meta">${fsize}</span>
                                                              `
                                                            : ''}
                                                    </span>
                                                </div>
                                            </article>
                                            <platform-button
                                                class="field-pill-file-ref-remove"
                                                variant="ghost"
                                                icon-only
                                                density="dense"
                                                aria-label=${this.t('base_node_editor.files_remove')}
                                                title=${this.t('base_node_editor.files_remove')}
                                                @click=${() => this._onRemoveFile(i)}
                                            >
                                                <platform-icon name="x" size="16"></platform-icon>
                                            </platform-button>
                                        </div>
                                    `;
                                })}
                            <div class="field-pill-file-refs-attach">
                                <label class="field-pill-file-refs-attach-btn" title=${this.t('base_node_editor.files_section')}>
                                    <platform-icon name="paperclip" size="18"></platform-icon>
                                    <input type="file" @change=${this._onUploadFile} ?disabled=${this._fileUpload.busy} />
                                </label>
                            </div>
                        </div>
                    </platform-field-shell>
                </div>
                `}
                ${this.flowNodeType === 'resource' ? nothing : html`
                <div class="field">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('base_node_editor.incoming_policy')}
                        .hint=${this.t('base_node_editor.incoming_policy_hint')}
                        .value=${policy}
                        .config=${this._incomingPolicyEnumConfig()}
                        @change=${this._onPolicy}
                    ></platform-field>
                </div>
                `}
                <div class="field">
                    <platform-field
                        type="integer"
                        mode="edit"
                        .label=${this.t('base_node_editor.node_timeout_seconds')}
                        .hint=${this.t('base_node_editor.node_timeout_hint')}
                        .value=${typeof cfg?.node_timeout_seconds === 'number' ? cfg.node_timeout_seconds : null}
                        @change=${this._onNodeTimeout}
                    ></platform-field>
                </div>
                ${visitsCap === null ? html`
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.max_visits_per_run')}</span>
                    ${typeof this._executionLimitsOp.error === 'string' && this._executionLimitsOp.error.length > 0
                        ? html`<div class="field-hint">${this._executionLimitsOp.error}</div>`
                        : html`<platform-spinner></platform-spinner>`}
                </div>
                ` : html`
                <div class="field">
                    <platform-field
                        type="integer"
                        mode="edit"
                        .label=${this.t('base_node_editor.max_visits_per_run')}
                        .hint=${this.t('base_node_editor.max_visits_per_run_hint')}
                        .value=${typeof cfg?.max_visits_per_run === 'number' ? cfg.max_visits_per_run : null}
                        @change=${this._onMaxVisitsPerRun}
                    ></platform-field>
                </div>
                `}
                <div class="field">
                    <div class="exception-response-head">
                        <span class="field-label">${this.t('base_node_editor.exception_as_response')}</span>
                        <platform-help-hint
                            label=${this.t('base_node_editor.exception_as_response_help_label')}
                            text=${this.t('base_node_editor.exception_as_response_hint')}
                        ></platform-help-hint>
                        <platform-switch
                            size="sm"
                            ?checked=${cfg?.exception_as_response === true}
                            @change=${this._onExceptionAsResponse}
                        ></platform-switch>
                    </div>
                </div>
                ${cfg?.exception_as_response === true ? html`
                <div class="field">
                    ${this._renderExceptionAllowTypesControls(cfg)}
                </div>
                ` : ''}
            </div>
        `;
    }

    _shouldShowPinnedResourcesSection() {
        return this.flowNodeType !== 'resource';
    }

    _renderResources() {
        const cfg = this.nodeConfig;
        const resources = isPlainObject(cfg?.resources) ? cfg.resources : {};
        const resourceIds = Object.keys(resources);
        const allResources = Array.isArray(this._resources.items) ? this._resources.items : [];
        const availableResources = allResources.filter((row) => {
            if (!isPlainObject(row) || typeof row.resource_id !== 'string' || row.resource_id.length === 0) {
                throw new Error('flows-base-node-editor: invalid resource item');
            }
            return resources[row.resource_id] === undefined;
        });
        const flowRes = this._flowBranchResources();
        const ov = llmOverrideRecord(cfg?.llm && typeof cfg.llm === 'object' ? cfg.llm : cfg?.llm_override);
        const presetRaw = ov.llm_resource_key;
        const presetKey = typeof presetRaw === 'string' ? presetRaw.trim() : '';
        const catalog = allResources;
        const showBranchPresetRow = this.flowNodeType === 'llm_node'
            && presetKey.length > 0
            && Object.prototype.hasOwnProperty.call(flowRes, presetKey)
            && this._branchRefIsLlm(flowRes[presetKey], catalog)
            && !Object.prototype.hasOwnProperty.call(resources, presetKey);
        const branchAttachOptions = this.flowNodeType === 'llm_node'
            ? this._llmBranchAttachOptions(flowRes, resources, presetKey, catalog)
            : [];
        const resourcesAttachHintParts = [];
        if (resourceIds.length === 0 && !showBranchPresetRow) {
            resourcesAttachHintParts.push(this.t('base_node_editor.resources_empty'));
        }
        if (this.flowNodeType === 'llm_node') {
            resourcesAttachHintParts.push(this.t('base_node_editor.resources_section_llm_node_hint'));
        }
        const resourcesAttachHint = resourcesAttachHintParts.join(' ');
        const rem = this.t('base_node_editor.resources_remove');
        const branchRowTitle = showBranchPresetRow
            ? this._branchRefAttachLabel(presetKey, flowRes[presetKey], catalog)
            : '';
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_resources')}</div>
                ${typeof this._resources.error === 'string' && this._resources.error.length > 0
            ? html`<div class="field-hint">${this._resources.error}</div>`
            : nothing}
                ${resourceIds.length === 0 && !showBranchPresetRow
                    ? nothing
                    : html`<div class="item-list">
                        ${showBranchPresetRow ? html`
                            <div class="item-row">
                                <span class="grow">${branchRowTitle}</span>
                                <span class="meta">${presetKey}</span>
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="compact"
                                    title=${rem}
                                    aria-label=${rem}
                                    @click=${() => this._onRemoveResource(presetKey)}
                                >
                                    <platform-icon name="trash" size="14"></platform-icon>
                                </platform-button>
                            </div>
                        ` : nothing}
                        ${Object.entries(resources).map(([key, ref]) => {
                            const resourceId = isPlainObject(ref) && typeof ref.resource_id === 'string' ? ref.resource_id : key;
                            const def = catalogRow(allResources, resourceId);
                            return html`
                                <div class="item-row">
                                    <span class="grow">${def ? def.name : key}</span>
                                    <span class="meta">${def ? def.type : ''}</span>
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="compact"
                                        title=${rem}
                                        aria-label=${rem}
                                        @click=${() => this._onRemoveResource(key)}
                                    >
                                        <platform-icon name="trash" size="14"></platform-icon>
                                    </platform-button>
                                </div>
                            `;
                        })}
                    </div>`}
                <div class="add-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('base_node_editor.resources_add_field')}
                        .hint=${resourcesAttachHint}
                        .value=${this._addResourcePick}
                        .config=${this._resourceAddEnumConfig(availableResources, branchAttachOptions)}
                        @change=${this._onAddResource}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _dataflowLabel(value: unknown) {
        if (typeof value !== 'string' || value.length === 0) {
            return '—';
        }
        return value;
    }

    _dataflowType(value: unknown) {
        return typeof value === 'string' && value.length > 0 ? value : 'any';
    }

    _dataflowActionTitle(value: unknown, actionKey: string) {
        const label = this._dataflowLabel(value);
        const action = this.t(actionKey);
        return `${label} · ${action}`;
    }

    _stateSourceFromPath(path: string) {
        const raw = typeof path === 'string' ? path.trim() : '';
        if (raw.startsWith('@var:')) {
            return { sourceType: 'var', sourcePath: raw.slice(5) };
        }
        if (raw.startsWith('@state:')) {
            return { sourceType: 'state', sourcePath: raw.slice(7) };
        }
        if (raw.startsWith('variables.')) {
            return { sourceType: 'var', sourcePath: raw.slice('variables.'.length) };
        }
        return { sourceType: 'state', sourcePath: raw };
    }

    _pathLeaf(path: string, fallback = 'value') {
        const raw = typeof path === 'string' ? path.trim() : '';
        const source = raw.length > 0 ? raw : fallback;
        const parts = source.replace(/\]/g, '').split(/[.[\s]+/).filter(Boolean);
        const last = parts.length > 0 ? parts[parts.length - 1]! : fallback;
        const safe = last.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^_+|_+$/g, '');
        return safe.length > 0 ? safe : fallback;
    }

    _uniqueMappingKey(base: string, mapping: Record<string, unknown>) {
        const safeBase = this._pathLeaf(base, 'value');
        if (!Object.prototype.hasOwnProperty.call(mapping, safeBase)) {
            return safeBase;
        }
        for (let i = 2; i < 100; i += 1) {
            const candidate = `${safeBase}_${i}`;
            if (!Object.prototype.hasOwnProperty.call(mapping, candidate)) {
                return candidate;
            }
        }
        return `${safeBase}_${Date.now()}`;
    }

    _outputMappingField() {
        return this.flowNodeType === 'mcp' || this.flowNodeType === 'external_api'
            ? 'state_mapping'
            : 'output_mapping';
    }

    _mappingObject(field: string) {
        const cfg = asObject(this.nodeConfig);
        const raw = cfg[field];
        return isPlainObject(raw) ? raw : {};
    }

    _applyMappingFromDataflow(field: string, mapping: Record<string, unknown>, tab: string) {
        this._mappingTab = tab;
        this._emitPatch({ [field]: mapping });
        queueMicrotask(() => {
            this._mappingSyncNonce += 1;
        });
    }

    _onSelectableKeydown(event: KeyboardEvent, handler: () => void) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    _addInputMappingFromPath(path: string) {
        const rawPath = typeof path === 'string' ? path.trim() : '';
        if (rawPath.length === 0) return;
        const { sourceType, sourcePath } = this._stateSourceFromPath(rawPath);
        if (sourcePath.length === 0) return;
        const source = sourceType === 'var' ? `@var:${sourcePath}` : `@state:${sourcePath}`;
        const mapping = this._mappingObject('input_mapping');
        if (Object.values(mapping).some((value) => value === source)) {
            this._mappingTab = 'input';
            return;
        }
        const key = this._uniqueMappingKey(sourcePath, mapping);
        this._applyMappingFromDataflow('input_mapping', { ...mapping, [key]: source }, 'input');
    }

    _resultKeyForStatePath(path: string) {
        const raw = typeof path === 'string' ? path.trim() : '';
        if (raw.length === 0) return '';
        const resultKeys = this._dataflowResultSuggestions();
        if (resultKeys.includes(raw)) return raw;
        const leaf = this._pathLeaf(raw, 'result');
        if (resultKeys.includes(leaf)) return leaf;
        return raw;
    }

    _addOutputMappingFromPath(path: string) {
        const stateField = typeof path === 'string' ? path.trim() : '';
        if (stateField.length === 0) return;
        const field = this._outputMappingField();
        const mapping = this._mappingObject(field);
        if (Object.values(mapping).some((value) => value === stateField)) {
            this._mappingTab = 'output';
            return;
        }
        const desiredKey = this._resultKeyForStatePath(stateField);
        const key = this._uniqueMappingKey(desiredKey, mapping);
        this._applyMappingFromDataflow(field, { ...mapping, [key]: stateField }, 'output');
    }

    _renderDataflowInputRows(rows: Record<string, unknown>[], incoming: unknown) {
        const visible = Array.isArray(incoming)
            ? incoming.filter((item) => item && item.source !== 'system').slice(0, 8)
            : [];
        if (visible.length > 0) {
            const mappedRows = Array.isArray(rows) ? rows.slice(0, 4) : [];
            return html`
                <div class="dataflow-list">
                    ${visible.map((item) => html`
                        <article
                            class="dataflow-chip"
                            tabindex="0"
                            role="button"
                            title=${this._dataflowActionTitle(item.path, 'base_node_editor.dataflow_add_input')}
                            @click=${() => this._addInputMappingFromPath(item.path)}
                            @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._addInputMappingFromPath(item.path))}
                        >
                            <span class="label">${this._dataflowLabel(item.path)}</span>
                            <span class="type">${this._dataflowType(item.type)}</span>
                        </article>
                    `)}
                    ${mappedRows.map((row) => html`
                        <div class="dataflow-row">
                            <article
                                class="dataflow-chip"
                                tabindex="0"
                                role="button"
                                data-status=${row.status === 'missing' ? 'missing' : 'ok'}
                                title=${this._dataflowActionTitle(mappingSource(row), 'base_node_editor.dataflow_add_input')}
                                @click=${() => this._addInputMappingFromPath(mappingSource(row))}
                                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._addInputMappingFromPath(mappingSource(row)))}
                            >
                                <span class="label">${this._dataflowLabel(mappingSource(row))}</span>
                                <span class="type">${this._dataflowType(row.type)}</span>
                            </article>
                            <span class="arrow">→</span>
                            <span class="dataflow-chip" title=${this._dataflowLabel(row.target)}>
                                <span class="label">${this._dataflowLabel(row.target)}</span>
                            </span>
                        </div>
                    `)}
                </div>
            `;
        }
        if (Array.isArray(rows) && rows.length > 0) {
            return html`
                <div class="dataflow-list">
                    ${rows.slice(0, 8).map((row) => html`
                        <div class="dataflow-row">
                            <article
                                class="dataflow-chip"
                                tabindex="0"
                                role="button"
                                data-status=${row.status === 'missing' ? 'missing' : 'ok'}
                                title=${this._dataflowActionTitle(mappingSource(row), 'base_node_editor.dataflow_add_input')}
                                @click=${() => this._addInputMappingFromPath(mappingSource(row))}
                                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._addInputMappingFromPath(mappingSource(row)))}
                            >
                                <span class="label">${this._dataflowLabel(mappingSource(row))}</span>
                                <span class="type">${this._dataflowType(row.type)}</span>
                            </article>
                            <span class="arrow">→</span>
                            <span class="dataflow-chip" title=${this._dataflowLabel(row.target)}>
                                <span class="label">${this._dataflowLabel(row.target)}</span>
                            </span>
                        </div>
                    `)}
                </div>
            `;
        }
        return html`<platform-empty-state title=${this.t('base_node_editor.dataflow_inputs_empty')}></platform-empty-state>`;
    }

    _renderDataflowWrites(writes: unknown) {
        const visible = Array.isArray(writes) ? writes.slice(0, 10) : [];
        if (visible.length === 0) {
            return html`<platform-empty-state title=${this.t('base_node_editor.dataflow_outputs_empty')}></platform-empty-state>`;
        }
        return html`
            <div class="dataflow-list">
                ${visible.map((item) => html`
                    <article
                        class="dataflow-chip"
                        tabindex="0"
                        role="button"
                        data-status=${item.protected ? 'missing' : 'ok'}
                        title=${this._dataflowActionTitle(item.path, 'base_node_editor.dataflow_add_output')}
                        @click=${() => this._addOutputMappingFromPath(item.path)}
                        @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._addOutputMappingFromPath(item.path))}
                    >
                        <span class="label">${this._dataflowLabel(item.path)}</span>
                        <span class="type">${this._dataflowType(item.type)}</span>
                    </article>
                `)}
            </div>
        `;
    }

    _renderDataflowIssues(issues: unknown) {
        const visible = Array.isArray(issues)
            ? issues.filter((issue) => issue && issue.severity !== 'info').slice(0, 4)
            : [];
        if (visible.length === 0) return '';
        return html`
            <div class="dataflow-issues">
                ${visible.map((issue) => html`
                    <div class="dataflow-issue" data-severity=${this._dataflowLabel(issue.severity)}>
                        ${this._dataflowLabel(issue.message)}
                    </div>
                `)}
            </div>
        `;
    }

    _renderDataflowLanes() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        if (!df) return '';
        const inputs = Array.isArray(df.input_mapping) ? [...df.input_mapping] : [];
        if (Array.isArray(df.reads)) {
            for (const read of df.reads) {
                inputs.push({
                    target: read.config_path,
                    source: read.source_kind && read.source_path ? `@${read.source_kind}:${read.source_path}` : read.source_path,
                    source_path: read.source_path,
                    status: read.status,
                    type: read.type,
                });
            }
        }
        const incoming = Array.isArray(df.incoming_state) ? df.incoming_state : [];
        const writes = Array.isArray(df.writes) ? df.writes : [];
        const issues = Array.isArray(df.issues) ? df.issues : [];
        return html`
            <div class="dataflow-lanes">
                <div class="dataflow-lane">
                    <div class="dataflow-lane-title">${this.t('base_node_editor.dataflow_inputs')}</div>
                    ${this._renderDataflowInputRows(inputs, incoming)}
                </div>
                <div class="dataflow-lane">
                    <div class="dataflow-lane-title">${this.t('base_node_editor.dataflow_outputs')}</div>
                    ${this._renderDataflowWrites(writes)}
                </div>
            </div>
            ${this._renderDataflowIssues(issues)}
        `;
    }

    _dataflowStateSuggestions() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        const rows = df && Array.isArray(df.incoming_state) ? df.incoming_state : [];
        const writes = df && Array.isArray(df.writes) ? df.writes : [];
        const paths = [];
        for (const item of [...rows, ...writes]) {
            if (!item || typeof item.path !== 'string' || item.path.length === 0) continue;
            if (item.path.startsWith('variables.')) continue;
            paths.push(item.path);
        }
        return Array.from(new Set(paths));
    }

    _dataflowVarSuggestions() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        const rows = df && Array.isArray(df.incoming_state) ? df.incoming_state : [];
        const vars = [];
        for (const item of rows) {
            if (!item || typeof item.path !== 'string') continue;
            if (item.path.startsWith('variables.')) vars.push(item.path.slice('variables.'.length));
        }
        const fv = this.flowVariables && typeof this.flowVariables === 'object' ? this.flowVariables : {};
        for (const key of Object.keys(fv)) {
            vars.push(key);
        }
        return Array.from(new Set(vars));
    }

    _dataflowResultSuggestions() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        if (df && Array.isArray(df.result_keys)) {
            return df.result_keys.filter((item) => typeof item === 'string' && item.length > 0);
        }
        return [];
    }

    _renderInputState() {
        const value = this._stateValue();
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_input_state')}</div>
                <platform-json-editor validate-json show-toolbar="false"
                    .value=${value}
                    @change=${this._onStateChange}
                ></platform-json-editor>
                <platform-button variant="ghost" density="compact" @click=${this._onStateReset}>
                    ${this.t('base_node_editor.input_state_reset')}
                </platform-button>
            </div>
        `;
    }

    _renderMappingContent() {
        const cfg = asObject(this.nodeConfig);
        const tab = this._mappingTab;
        const isMcp = this.flowNodeType === 'mcp';
        const isExternalApi = this.flowNodeType === 'external_api';
        const useStateMappingOnOutput = isMcp || isExternalApi;
        let rawMapping;
        let field;
        if (tab === 'input') {
            rawMapping = cfg.input_mapping;
            field = 'input_mapping';
        } else if (useStateMappingOnOutput) {
            rawMapping = cfg.state_mapping;
            field = 'state_mapping';
        } else {
            rawMapping = cfg.output_mapping;
            field = 'output_mapping';
        }
        const mapping = isPlainObject(rawMapping) ? rawMapping : {};
        const syncSegment = isMcp ? 'mcp-' : isExternalApi ? 'extapi-' : '';
        const flowKey = this.flowId === undefined || this.flowId === null ? '' : String(this.flowId);
        const nodeKey = this.nodeId === undefined || this.nodeId === null ? '' : String(this.nodeId);
        const syncKey = `${flowKey}--${nodeKey}--imap--${syncSegment}${tab}--${this._mappingSyncNonce}`;
        return html`
            <div class="dataflow-mapping-head">
                <div class="section-title">${this.t('base_node_editor.section_mapping')}</div>
                <div class="mapping-tabs">
                    <platform-segmented-control
                        full-width
                        density="compact"
                        .value=${tab}
                        .items=${[
                            { value: 'input', label: this.t('base_node_editor.tab_input') },
                            { value: 'output', label: this.t('base_node_editor.tab_output') },
                        ]}
                        aria-label=${this.t('base_node_editor.section_mapping')}
                        @change=${(e: CustomEvent) => { this._mappingTab = e.detail.value; }}
                    ></platform-segmented-control>
                </div>
            </div>
            <flows-state-mapping-editor
                syncKey=${syncKey}
                kind=${tab === 'input' ? 'input' : 'output'}
                .mapping=${mapping}
                .stateSuggestions=${this._dataflowStateSuggestions()}
                .varSuggestions=${this._dataflowVarSuggestions()}
                .resultSuggestions=${this._dataflowResultSuggestions()}
                @change=${(e: CustomEvent) => this._onMapping(field, e)}
            ></flows-state-mapping-editor>
        `;
    }

    _renderMapping() {
        return html`
            <div class="section">
                ${this._renderMappingContent()}
            </div>
        `;
    }

    _renderDataflowMapping() {
        return html`
            <div class="section dataflow-mapping-shell">
                <div class="section-title">${this.t('base_node_editor.section_dataflow')}</div>
                <div class="dataflow-mapping-grid">
                    ${this._renderDataflowLanes()}
                    <div class="dataflow-mapping-body">
                        ${this._renderMappingContent()}
                    </div>
                </div>
            </div>
        `;
    }

    _renderSettingsSlot() {
        return html`
            <div class="section">
                <slot name="settings"></slot>
            </div>
        `;
    }

    override render(): TemplateResult {
        if (!this.nodeConfig) return html`<div>${this.t('property_panel.select_node')}</div>`;
        if (this.focusMode === true) {
            const section = typeof this.focusSection === 'string' && this.focusSection.length > 0
                ? this.focusSection
                : 'prompt';
            if (section === 'advanced') {
                return html`
                    <div class="panel-layout focus-advanced">
                        <div class="panel-sidebar content-panel">
                            ${this._renderBasic()}
                            ${this._shouldShowPinnedResourcesSection() ? this._renderResources() : nothing}
                            ${this._renderInputState()}
                        </div>
                        <div class="panel-main">
                            <div class="panel-run-fallback" data-node-run-fallback="panel-main"></div>
                            ${this._renderSettingsSlot()}
                            ${this.flowNodeType === 'resource' ? nothing : this._renderDataflowMapping()}
                        </div>
                    </div>
                `;
            }
            return html`
                <div class="panel-layout focus-single">
                    <div class="panel-main focus-main">
                        <div class="panel-run-fallback" data-node-run-fallback="panel-main"></div>
                        ${this._renderSettingsSlot()}
                    </div>
                </div>
            `;
        }
        return html`
            <div class="panel-layout">
                <div class="panel-sidebar content-panel">
                    ${this._renderBasic()}
                    ${this._shouldShowPinnedResourcesSection() ? this._renderResources() : nothing}
                    ${this._renderInputState()}
                </div>
                <div class="panel-main">
                    <div class="panel-run-fallback" data-node-run-fallback="panel-main"></div>
                    ${this._renderSettingsSlot()}
                    ${this.flowNodeType === 'resource' ? nothing : this._renderDataflowMapping()}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-base-node-editor', FlowsBaseNodeEditor);

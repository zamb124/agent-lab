/**
 * flows-base-node-editor — общая обёртка редакторов нод.
 *
 * Два режима рендера, выбираются атрибутом `expanded`:
 *
 * 1. compact: header (только слот Run) → «Запустить» в шапке `flows-floating-panel`; заголовок панели — `cfg.name` или id;
 *    хост панели ищется обходом DOM ShadowRoot→host, иначе fallback. Для `nodeType === 'resource'` рядом с Run монтируется `platform-help-hint` (ресурсы на графе).
 * 2. модалка «Инструмент» в LLM: `.embedded-tool-run-host` в шапке `flows-embedded-tool-config-modal`.
 * 3. expanded: .panel-main — fallback для Run без floating-panel и без этой модалки.
 * Запуск: `useOp('flows/code_execute')`, UI — `flows-node-run-control` (imperative mount).
 *
 * Эмитит наружу:
 *   - change { nodeId, patch } — patch с top-level полями NodeConfig
 *     (description/tags/incoming_policy/exception_as_response/exception_allow_types/files/resources). Type-specific
 *     патчи приходят через slot='settings' (дочерний редактор сам диспатчит
 *     change на хосте).
 *
 * Секция «Закреплённые ресурсы» не показывается для ноды `resource`: на графе это
 * уже ресурс, вложенные закрепления с той же ноды не редактируются.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '../editors/flows-state-mapping-editor.js';
import '../editors/flows-json-field-editor.js';
import '../flows-node-run-control.js';
import '@platform/lib/components/fields/platform-field.js';
import { fieldPillStyles } from '@platform/lib/styles/shared/field-pill.styles.js';
import {
    nextCodeExecuteClientId,
    setCodeExecuteRequestClientId,
} from '../../_helpers/flows-code-execute-run-gate.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { formatExecuteViewModel } from '../../_helpers/flows-execute-preview.js';

export class FlowsBaseNodeEditor extends PlatformElement {
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
        expanded: { type: Boolean, reflect: true },
        /** Редактирование вложенного tool: без смены node id */
        embedded: { type: Boolean, reflect: true },
        _stateDraft: { state: true },
        _mappingTab: { state: true },
        _addResourcePick: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        fieldPillStyles,
        css`
            :host {
                display: block;
                color: var(--text-primary);
                height: 100%;
                min-height: 0;
                box-sizing: border-box;
            }
            :host(:not([expanded])) {
                padding: var(--space-3);
                overflow: auto;
            }

            /* Compact layout: stacked */
            .compact {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            /* Expanded layout: master-detail */
            .panel-layout {
                display: grid;
                grid-template-columns: 320px 1fr;
                gap: 0;
                height: 100%;
                min-height: 0;
            }
            .panel-sidebar {
                overflow: auto;
                padding: var(--space-4);
                border-right: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
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
            }

            /* Sections */
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
            /* header */
            .header {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            .header-run-fallback:empty { display: none; }
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
            .field-pill-file-refs-shell {
                gap: var(--field-pill-gap);
            }

            glass-button {
                flex-shrink: 0;
            }

            /* File and resource lists */
            .item-list {
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .item-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
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
            .item-row .remove {
                background: none; border: none; padding: 0; cursor: pointer;
                color: var(--text-tertiary);
                display: inline-flex; align-items: center;
            }
            .item-row .remove:hover { color: var(--error); }

            input[type="file"] { display: none; }

            .mapping-tabs {
                display: flex; gap: var(--space-1); margin-bottom: var(--space-2);
            }
            .mapping-tab {
                padding: 4px 12px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .mapping-tab[active] {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent-subtle);
            }

            .reset-link {
                background: none; border: none; padding: 0;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
                text-decoration: underline;
                align-self: flex-start;
            }
            .reset-link:hover { color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = '';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._mappingTab = 'input';
        this._stateDraft = null;
        this._addResourcePick = '';
        this._fileUpload = this.useOp('flows/file_upload');
        this._nodeExecute = this.useOp('flows/code_execute');
        this._exceptionAbsorbAllowNamesOp = this.useOp('flows/exception_absorb_allow_names');
        this._executionLimitsOp = this.useOp('flows/execution_limits');
        this._codeExecuteClientId = nextCodeExecuteClientId();
        this._resources = this.useResource('flows/resources', { autoload: true });
        this._flowEditor = this.useOp('flows/editor');
        this._nodeRunControlEl = null;
        this._resourceGraphHintEl = null;
        this._onNodeRunFired = () => { void this._runNodeTest(); };
        this._onNodeRunOpenFullEvent = (e) => { this._onOpenExecuteFull(e); };
    }

    connectedCallback() {
        super.connectedCallback();
        void this._exceptionAbsorbAllowNamesOp.run({});
        void this._executionLimitsOp.run({});
        queueMicrotask(() => this._placeNodeRunControl());
        requestAnimationFrame(() => this._placeNodeRunControl());
    }

    disconnectedCallback() {
        if (this._nodeRunControlEl) {
            this._nodeRunControlEl.removeEventListener('run', this._onNodeRunFired);
            this._nodeRunControlEl.removeEventListener('open-full', this._onNodeRunOpenFullEvent);
            this._nodeRunControlEl.remove();
            this._nodeRunControlEl = null;
        }
        if (this._resourceGraphHintEl) {
            this._resourceGraphHintEl.remove();
            this._resourceGraphHintEl = null;
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        this._placeNodeRunControl();
    }

    _ensureNodeRunControl() {
        if (this._nodeRunControlEl) {
            return this._nodeRunControlEl;
        }
        const el = document.createElement('flows-node-run-control');
        el.requestClientId = this._codeExecuteClientId;
        el.addEventListener('run', this._onNodeRunFired);
        el.addEventListener('open-full', this._onNodeRunOpenFullEvent);
        this._nodeRunControlEl = el;
        return el;
    }

    _ensureResourceGraphHint() {
        if (this._resourceGraphHintEl) {
            return this._resourceGraphHintEl;
        }
        const hint = document.createElement('platform-help-hint');
        this._resourceGraphHintEl = hint;
        return hint;
    }

    _syncResourceGraphHintProps() {
        const hint = this._resourceGraphHintEl;
        if (!hint) {
            return;
        }
        hint.label = this.t('resource_node_editor.help_label');
        hint.text = this.t('resource_node_editor.help_body');
    }

    _syncNodeRunControlProps() {
        const el = this._nodeRunControlEl;
        if (!el) {
            return;
        }
        el.requestClientId = this._codeExecuteClientId;
        el.viewModel = this._executeViewModel();
        el.busy = this._nodeExecute.busy;
    }

    /**
     * `closest` не везде поднимается сквозь границы вложенных shadow root; до flows-floating-panel
     * идём вручную: parent, либо ShadowRoot -> host.
     */
    _findFlowsFloatingPanel() {
        let n = this;
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

    _floatingPanelHeaderRunHost(panel) {
        const root = panel.shadowRoot;
        if (!root) {
            return null;
        }
        return root.querySelector('.header-actions-host');
    }

    /**
     * Редактор вложенного tool (модалка с canvas): play в шапке модалки, не в теле редактора.
     */
    _findEmbeddedToolConfigModal() {
        let n = this;
        for (let d = 0; d < 128; d += 1) {
            if (!n) {
                return null;
            }
            if (n.nodeName === 'FLOWS-EMBEDDED-TOOL-CONFIG-MODAL') {
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

    _embeddedToolModalHeaderRunHost(modal) {
        const root = modal.shadowRoot;
        if (!root) {
            return null;
        }
        return root.querySelector('.embedded-tool-run-host');
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
        const hostFromPanel = panel ? this._floatingPanelHeaderRunHost(panel) : null;
        const hostFromEmbedded = embeddedModal ? this._embeddedToolModalHeaderRunHost(embeddedModal) : null;
        let target = null;
        if (hostFromPanel) {
            target = hostFromPanel;
        } else if (hostFromEmbedded) {
            target = hostFromEmbedded;
        } else if (this.expanded) {
            target = this.renderRoot?.querySelector?.('[data-node-run-fallback="expanded"]') ?? null;
        } else {
            target = this.renderRoot?.querySelector?.('[data-node-run-fallback="compact"]') ?? null;
        }
        if (!target) {
            if (this._resourceGraphHintEl) {
                this._resourceGraphHintEl.remove();
            }
            return;
        }
        if (el.parentElement !== target) {
            target.appendChild(el);
        }
        if (this.nodeType === 'resource') {
            const hint = this._ensureResourceGraphHint();
            this._syncResourceGraphHintProps();
            target.insertBefore(hint, el);
        } else if (this._resourceGraphHintEl) {
            this._resourceGraphHintEl.remove();
        }
    }

    _executeViewModel() {
        return formatExecuteViewModel({
            opError: this._nodeExecute.error,
            lastResult: this._nodeExecute.lastResult,
        });
    }

    async _runNodeTest() {
        let state;
        try {
            state = JSON.parse(this._stateValue());
        } catch {
            this.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        if (state === null || typeof state !== 'object' || Array.isArray(state)) {
            this.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        const skill = typeof this.branchId === 'string' && this.branchId.length > 0 ? this.branchId : 'base';
        setCodeExecuteRequestClientId(this._codeExecuteClientId);
        await this._nodeExecute.run({
            node_type: this.nodeType,
            node_config: asObject(this.nodeConfig),
            state,
            flow_id: this.flowId,
            branch_id: skill,
        });
    }

    _onOpenExecuteFull(e) {
        const d = e.detail;
        if (!d || typeof d.value !== 'object' || d.value === null) {
            throw new Error('flows-base-node-editor: open-full event requires detail.value object');
        }
        this.openModal('flows.raw_json', { value: d.value });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _stringArrayFromChangeDetail(e, ctx) {
        const d = e.detail;
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

    _onDescription(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._emitPatch({ description: v });
    }
    _onTags(e) {
        this._emitPatch({ tags: this._stringArrayFromChangeDetail(e, 'flows-base-node-editor:tags') });
    }
    _onPolicy(e) {
        const raw = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        const v = raw === 'all' ? 'all' : 'any';
        this._emitPatch({ incoming_policy: v });
    }

    _onNodeTimeout(e) {
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
        if (typeof raw !== 'object' || raw === null || typeof raw.graph_max_iterations !== 'number') {
            throw new Error('flows-base-node-editor: execution limits response invalid');
        }
        return raw.graph_max_iterations;
    }

    _onMaxVisitsPerRun(e) {
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

    _onExceptionAsResponse(e) {
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
        if (!Array.isArray(raw)) {
            throw new Error('flows-base-node-editor: exception-absorb-allow-names response must be an array');
        }
        if (raw.length === 0) {
            throw new Error('flows-base-node-editor: exception-absorb-allow-names must be non-empty');
        }
        for (let i = 0; i < raw.length; i++) {
            if (typeof raw[i] !== 'string') {
                throw new Error('flows-base-node-editor: exception-absorb-allow-names item must be a string');
            }
        }
        return raw;
    }

    _renderExceptionAllowTypesControls(cfg) {
        const op = this._exceptionAbsorbAllowNamesOp;
        const allowNames = this._exceptionAbsorbAllowNamesList();
        if (allowNames === null) {
            if (typeof op.error === 'string' && op.error.length > 0) {
                return html`<div class="field-hint">${op.error}</div>`;
            }
            return html`<glass-spinner></glass-spinner>`;
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

    _onExceptionAllowTypes(e) {
        this._emitPatch({
            exception_allow_types: this._stringArrayFromChangeDetail(e, 'flows-base-node-editor:exception_allow_types'),
        });
    }
    _onMapping(field, e) {
        const mapping = e.detail?.mapping;
        this._emitPatch({ [field]: isPlainObject(mapping) ? mapping : {} });
    }

    async _onUploadFile(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const input = e.target;
        const result = await this._fileUpload.run({ file });
        if (!result || typeof result.file_id !== 'string') {
            throw new Error('flows-base-node-editor: file_upload op must return result.file_id');
        }
        const name = typeof result.original_name === 'string' && result.original_name !== ''
            ? result.original_name
            : file.name;
        const mimeType = typeof result.content_type === 'string' && result.content_type !== ''
            ? result.content_type
            : file.type;
        const size = typeof result.file_size === 'number' ? result.file_size : file.size;
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        const next = [...files, {
            file_id: result.file_id,
            name,
            mime_type: mimeType,
            size,
        }];
        this._emitPatch({ files: next });
        input.value = '';
    }

    _formatFileSize(bytes) {
        return formatFileSize(bytes);
    }

    _onRemoveFile(idx) {
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
    _branchRefIsLlm(refRaw, catalog) {
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
        const def = catalog.find((r) => r && r.resource_id === rid);
        return Boolean(def && def.type === 'llm');
    }

    /**
     * @param {string} key
     * @param {object} refRaw
     * @param {{ resource_id?: string, name?: string, type?: string }[]} catalog
     */
    _branchRefAttachLabel(key, refRaw, catalog) {
        if (!isPlainObject(refRaw)) {
            return key;
        }
        const rid = typeof refRaw.resource_id === 'string' ? refRaw.resource_id.trim() : '';
        let title = '';
        if (rid.length > 0) {
            const def = catalog.find((r) => r && r.resource_id === rid);
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
    _llmBranchAttachOptions(flowRes, resources, presetKey, catalog) {
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

    _onAddResource(e) {
        const resourceId = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._addResourcePick = '';
        if (!resourceId) return;
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? this.nodeConfig.resources
            : {};
        if (resources[resourceId]) return;
        const catalog = Array.isArray(this._resources.items) ? this._resources.items : [];
        const flowRes = this._flowBranchResources();
        const patch = {};

        if (
            this.nodeType === 'llm_node'
            && Object.prototype.hasOwnProperty.call(flowRes, resourceId)
            && this._branchRefIsLlm(flowRes[resourceId], catalog)
        ) {
            const next = { ...resources };
            for (const [key, ref] of Object.entries(next)) {
                const rid = ref && typeof ref.resource_id === 'string' ? ref.resource_id : key;
                const d = catalog.find((r) => r && r.resource_id === rid);
                if (d && d.type === 'llm') {
                    delete next[key];
                }
            }
            patch.resources = next;
            const ov = this.nodeConfig?.llm_override && typeof this.nodeConfig.llm_override === 'object'
                ? { ...this.nodeConfig.llm_override }
                : {};
            ov.llm_resource_key = resourceId;
            patch.llm_override = ov;
            this._emitPatch(patch);
            return;
        }

        const def = catalog.find((r) => r && r.resource_id === resourceId);

        if (this.nodeType === 'llm_node' && def && def.type === 'llm') {
            const next = { ...resources };
            for (const [key, ref] of Object.entries(next)) {
                const rid = ref && typeof ref.resource_id === 'string' ? ref.resource_id : key;
                const d = catalog.find((r) => r && r.resource_id === rid);
                if (d && d.type === 'llm') {
                    delete next[key];
                }
            }
            next[resourceId] = { resource_id: resourceId };
            patch.resources = next;
            const ov = this.nodeConfig?.llm_override && typeof this.nodeConfig.llm_override === 'object'
                ? { ...this.nodeConfig.llm_override }
                : {};
            ov.llm_resource_key = resourceId;
            patch.llm_override = ov;
        } else {
            patch.resources = { ...resources, [resourceId]: { resource_id: resourceId } };
        }
        this._emitPatch(patch);
    }

    _onRemoveResource(key) {
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? this.nodeConfig.resources
            : {};
        const next = { ...resources };
        delete next[key];
        const patch = { resources: next };
        const ov = this.nodeConfig?.llm_override && typeof this.nodeConfig.llm_override === 'object'
            ? { ...this.nodeConfig.llm_override }
            : {};
        const presetKey = typeof ov.llm_resource_key === 'string' ? ov.llm_resource_key.trim() : '';
        if (presetKey === key) {
            delete ov.llm_resource_key;
            patch.llm_override = Object.keys(ov).length > 0 ? ov : null;
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

    _resourceAddEnumConfig(availableResources, branchAttachOptions) {
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
        return JSON.stringify(preview, null, 2);
    }

    _onStateChange(e) {
        const v = e.detail?.value;
        if (typeof v === 'string') this._stateDraft = v;
    }

    _onStateReset() {
        this._stateDraft = null;
        this.requestUpdate();
    }

    _renderHeader() {
        return html`
            <div class="header">
                <div class="header-run-fallback" data-node-run-fallback="compact"></div>
            </div>
        `;
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
                        .value=${this.nodeId}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('base_node_editor.description')}
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
                        .placeholder=${this.t('tag_input.placeholder')}
                        .value=${tags}
                        .config=${{ preserve_case: true }}
                        @change=${this._onTags}
                    ></platform-field>
                </div>
                <div class="field">
                    <div class="field-pill field-pill-file-refs-shell">
                        <div class="field-pill-head">
                            <span class="field-pill-label">${this.t('base_node_editor.files_section')}</span>
                        </div>
                        <div class="field-pill-file-refs-body">
                            ${files.length === 0
                                ? html`<p class="field-pill-empty">${this.t('base_node_editor.files_empty')}</p>`
                                : files.map((f, i) => {
                                    const fname = typeof f.name === 'string' && f.name !== '' ? f.name : f.file_id;
                                    const fmime = typeof f.mime_type === 'string' ? f.mime_type : '';
                                    const fsize = this._formatFileSize(f.size);
                                    return html`
                                        <div class="field-pill-file-ref-row">
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
                                            <button
                                                class="field-pill-file-ref-remove"
                                                type="button"
                                                aria-label=${this.t('base_node_editor.files_remove')}
                                                title=${this.t('base_node_editor.files_remove')}
                                                @click=${() => this._onRemoveFile(i)}
                                            >
                                                <platform-icon name="x" size="16"></platform-icon>
                                            </button>
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
                    </div>
                </div>
                ${this.nodeType === 'resource' ? nothing : html`
                <div class="field">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('base_node_editor.incoming_policy')}
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
                        : html`<glass-spinner></glass-spinner>`}
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
        return this.nodeType !== 'resource';
    }

    _renderResources() {
        const cfg = this.nodeConfig;
        const resources = cfg?.resources && typeof cfg.resources === 'object' ? cfg.resources : {};
        const resourceIds = Object.keys(resources);
        const allResources = Array.isArray(this._resources.items) ? this._resources.items : [];
        const availableResources = allResources.filter((r) => r && !resources[r.resource_id]);
        const flowRes = this._flowBranchResources();
        const ov = cfg?.llm_override && typeof cfg.llm_override === 'object' ? cfg.llm_override : {};
        const presetRaw = ov.llm_resource_key;
        const presetKey = typeof presetRaw === 'string' ? presetRaw.trim() : '';
        const catalog = allResources;
        const showBranchPresetRow = this.nodeType === 'llm_node'
            && presetKey.length > 0
            && Object.prototype.hasOwnProperty.call(flowRes, presetKey)
            && this._branchRefIsLlm(flowRes[presetKey], catalog)
            && !Object.prototype.hasOwnProperty.call(resources, presetKey);
        const branchAttachOptions = this.nodeType === 'llm_node'
            ? this._llmBranchAttachOptions(flowRes, resources, presetKey, catalog)
            : [];
        const resourcesAttachHintParts = [];
        if (resourceIds.length === 0 && !showBranchPresetRow) {
            resourcesAttachHintParts.push(this.t('base_node_editor.resources_empty'));
        }
        if (this.nodeType === 'llm_node') {
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
                                <button class="remove" type="button" title=${rem} @click=${() => this._onRemoveResource(presetKey)}>
                                    <platform-icon name="trash" size="14"></platform-icon>
                                </button>
                            </div>
                        ` : nothing}
                        ${Object.entries(resources).map(([key, ref]) => {
                            const def = allResources.find((r) => r && r.resource_id === (ref && typeof ref.resource_id === 'string' ? ref.resource_id : key));
                            return html`
                                <div class="item-row">
                                    <span class="grow">${def ? def.name : key}</span>
                                    <span class="meta">${def ? def.type : ''}</span>
                                    <button class="remove" type="button" title=${rem} @click=${() => this._onRemoveResource(key)}>
                                        <platform-icon name="trash" size="14"></platform-icon>
                                    </button>
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

    _renderInputState() {
        const value = this._stateValue();
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_input_state')}</div>
                <flows-json-field-editor
                    .value=${value}
                    @change=${this._onStateChange}
                ></flows-json-field-editor>
                <button class="reset-link" type="button" @click=${this._onStateReset}>
                    ${this.t('base_node_editor.input_state_reset')}
                </button>
            </div>
        `;
    }

    _renderMapping() {
        const cfg = asObject(this.nodeConfig);
        const tab = this._mappingTab;
        const isMcp = this.nodeType === 'mcp';
        let rawMapping;
        let field;
        if (tab === 'input') {
            rawMapping = cfg.input_mapping;
            field = 'input_mapping';
        } else if (isMcp) {
            rawMapping = cfg.state_mapping;
            field = 'state_mapping';
        } else {
            rawMapping = cfg.output_mapping;
            field = 'output_mapping';
        }
        const mapping = isPlainObject(rawMapping) ? rawMapping : {};
        const syncKey = `${String(this.flowId ?? '')}--${String(this.nodeId ?? '')}--imap--${isMcp ? 'mcp-' : ''}${tab}`;
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_mapping')}</div>
                <div class="mapping-tabs">
                    <button class="mapping-tab" type="button" ?active=${tab === 'input'}
                        @click=${() => { this._mappingTab = 'input'; }}>
                        ${this.t('base_node_editor.tab_input')}
                    </button>
                    <button class="mapping-tab" type="button" ?active=${tab === 'output'}
                        @click=${() => { this._mappingTab = 'output'; }}>
                        ${this.t('base_node_editor.tab_output')}
                    </button>
                </div>
                <flows-state-mapping-editor
                    syncKey=${syncKey}
                    kind=${tab === 'input' ? 'input' : 'output'}
                    .mapping=${mapping}
                    @change=${(e) => this._onMapping(field, e)}
                ></flows-state-mapping-editor>
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

    render() {
        if (!this.nodeConfig) return html`<div>${this.t('property_panel.select_node')}</div>`;
        if (this.expanded) {
            return html`
                <div class="panel-layout">
                    <div class="panel-sidebar">
                        ${this._renderBasic()}
                        ${this._shouldShowPinnedResourcesSection() ? this._renderResources() : nothing}
                        ${this._renderInputState()}
                    </div>
                    <div class="panel-main">
                        <div class="panel-run-fallback" data-node-run-fallback="expanded"></div>
                        ${this._renderSettingsSlot()}
                        ${this.nodeType === 'resource' ? nothing : this._renderMapping()}
                    </div>
                </div>
            `;
        }
        return html`
            <div class="compact">
                ${this._renderHeader()}
                ${this._renderBasic()}
                ${this._shouldShowPinnedResourcesSection() ? this._renderResources() : nothing}
                ${this._renderSettingsSlot()}
                ${this.nodeType === 'resource' ? nothing : this._renderMapping()}
                ${this._renderInputState()}
            </div>
        `;
    }
}

customElements.define('flows-base-node-editor', FlowsBaseNodeEditor);

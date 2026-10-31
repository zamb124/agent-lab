/**
 * Полноэкранный инспектор результата ноды: история run_index + master-detail diff.
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-empty-state.js';
import { getBranchNodes, isPlainObject } from '../_helpers/flows-resolvers.js';
import {
    buildNodeRunChangeRows,
    buildNodeRunHeadline,
    countNodeRunDiffChanges,
    findDiffEntryByPath,
    findNodeRunResult,
    isLatestNodeRun,
    nodeRunDiffHasPath,
    pickLatestNodeRunResult,
    resolveInspectValue,
    serializeNodeRunValue,
} from '../_helpers/flows-node-run-result.js';
import '../components/flows-node-run-value-view.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

export class FlowsNodeRunResultModal extends PlatformModal {
    static modalKind = 'flows.node_run_result';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        nodeId: { type: String },
        runIndex: { type: Number },
        selectedPath: { type: String },
        _selectedRunIndex: { state: true },
        _selectedPath: { state: true },
        _diffQuery: { state: true },
        _valueSide: { state: true },
        _followLatest: { state: true },
        _resultsLength: { state: true },
    }
    declare nodeId: string;
    declare runIndex: number;
    declare selectedPath: string;
    declare _selectedRunIndex: number | null;
    declare _selectedPath: string;
    declare _diffQuery: string;
    declare _valueSide: string;
    declare _followLatest: boolean;
    declare _resultsLength: number;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        panelShellStyles,
        css`
            :host .modal.full .modal-content {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }
            .node-run-result-body {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .workspace {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                gap: var(--space-3);
            }
            .runs-rail {
                flex: 0 0 240px;
                min-width: 0;
                min-height: 0;
            }
            .runs-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
            }
            .run-row {
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                cursor: pointer;
                min-width: 0;
            }
            .run-row:hover {
                background: var(--glass-solid-subtle);
            }
            .run-row[data-active='true'] {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .run-row[data-tone='error'] {
                border-color: var(--error-border);
            }
            .run-row-title {
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
            }
            .run-row-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .runs-nav {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            .fields-pane {
                flex: 0 0 280px;
                min-width: 0;
                min-height: 0;
            }
            .fields-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
            }
            .field-row {
                display: grid;
                grid-template-columns: 16px 1fr;
                gap: 4px var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                cursor: pointer;
                min-width: 0;
            }
            .field-row:hover {
                background: var(--glass-solid-subtle);
            }
            .field-row[data-active='true'] {
                background: var(--accent-subtle);
            }
            .field-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 16px;
                height: 16px;
                border-radius: var(--radius-sm);
                font-family: var(--font-mono);
                font-weight: var(--font-bold);
                font-size: 11px;
            }
            .field-row[data-change-type='added'] .field-badge {
                color: var(--success);
                background: var(--success-bg);
                border: 1px solid var(--success-border);
            }
            .field-row[data-change-type='changed'] .field-badge {
                color: var(--warning);
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
            }
            .field-row[data-change-type='removed'] .field-badge {
                color: var(--error);
                background: var(--error-bg);
                border: 1px solid var(--error-border);
            }
            .field-label {
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
                word-break: break-word;
            }
            .field-type {
                font-size: 10px;
                color: var(--text-tertiary);
            }
            .viewer-pane {
                flex: 1 1 auto;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .viewer-toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
            }
            .error-text {
                margin: 0;
                padding: var(--space-4);
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                color: var(--error);
                white-space: pre-wrap;
                word-break: break-word;
            }
            .header-sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-weight: var(--font-normal);
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;

    constructor() {
        super();
        this.size = 'full';
        this.nodeId = '';
        this.runIndex = NaN;
        this.selectedPath = '';
        this._selectedRunIndex = null;
        this._selectedPath = '';
        this._diffQuery = '';
        this._valueSide = 'new';
        this._followLatest = true;
        this._resultsLength = 0;
        this._editor = this.useOp('flows/editor');
    }

    /**
     * @param {KeyboardEvent} event
     * @param {() => void} handler
     */
    _onSelectableKeydown(event: KeyboardEvent, handler: () => void) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    _translate(key: string, params: unknown): string {
        if (params === undefined || params === null) {
            return this.t(key);
        }
        if (!isPlainObject(params)) {
            throw new Error('flows-node-run-result-modal: translation params required');
        }
        const vars: Record<string, string | number> = {};
        for (const [name, value] of Object.entries(params)) {
            if (typeof value !== 'string' && typeof value !== 'number') {
                throw new Error('flows-node-run-result-modal: translation param must be string or number');
            }
            vars[name] = value;
        }
        return this.t(key, vars);
    }

    _requireResults(): unknown[] {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            throw new Error('flows-node-run-result-modal: nodeId is required');
        }
        const resultsMap = this._editor.state.nodeRunResults;
        if (!isPlainObject(resultsMap)) {
            throw new Error(`flows-node-run-result-modal: no runs for node ${this.nodeId}`);
        }
        const results = resultsMap[this.nodeId];
        if (!Array.isArray(results) || results.length === 0) {
            throw new Error(`flows-node-run-result-modal: no runs for node ${this.nodeId}`);
        }
        return results;
    }

    /**
     * @param {Record<string, unknown>} result
     */
    _ensurePathForResult(result: Record<string, unknown>) {
        if (result.kind === 'error') {
            this._selectedPath = '';
            return;
        }
        const rows = buildNodeRunChangeRows(result, (key: string, params: unknown) => this._translate(key, params));
        if (this._selectedPath.length > 0 && nodeRunDiffHasPath(result, this._selectedPath)) {
            return;
        }
        if (typeof this.selectedPath === 'string' && this.selectedPath.length > 0 && nodeRunDiffHasPath(result, this.selectedPath)) {
            this._selectedPath = this.selectedPath;
            return;
        }
        const firstRow = rows[0];
        if (rows.length > 0 && firstRow === undefined) {
            throw new Error('flows-node-run-result-modal: change row missing');
        }
        this._selectedPath = firstRow === undefined ? '' : firstRow.path;
    }

    /**
     * @param {unknown[]} results
     * @param {boolean} forceInit
     */
    _syncRuns(results: unknown[], forceInit: boolean) {
        if (forceInit || this._selectedRunIndex === null) {
            if (typeof this.runIndex === 'number' && Number.isFinite(this.runIndex)) {
                this._selectedRunIndex = Math.floor(this.runIndex);
                findNodeRunResult(results, this._selectedRunIndex);
            } else {
                const latest = pickLatestNodeRunResult(results);
                if (latest === null) {
                    throw new Error(`flows-node-run-result-modal: no runs for node ${this.nodeId}`);
                }
                if (typeof latest.run_index !== 'number' || !Number.isFinite(latest.run_index)) {
                    throw new Error('flows-node-run-result-modal: run_index is required');
                }
                this._selectedRunIndex = Math.floor(latest.run_index);
            }
            this._followLatest = isLatestNodeRun(results, this._selectedRunIndex);
            this._resultsLength = results.length;
            this._ensurePathForResult(findNodeRunResult(results, this._selectedRunIndex));
            return;
        }
        if (results.length === this._resultsLength) {
            return;
        }
        if (this._followLatest) {
            const latest = pickLatestNodeRunResult(results);
            if (latest === null) {
                throw new Error(`flows-node-run-result-modal: no runs for node ${this.nodeId}`);
            }
            if (typeof latest.run_index !== 'number' || !Number.isFinite(latest.run_index)) {
                throw new Error('flows-node-run-result-modal: run_index is required');
            }
            this._selectedRunIndex = Math.floor(latest.run_index);
        } else {
            findNodeRunResult(results, this._selectedRunIndex);
        }
        this._resultsLength = results.length;
        this._followLatest = isLatestNodeRun(results, this._selectedRunIndex);
        this._ensurePathForResult(findNodeRunResult(results, this._selectedRunIndex));
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate?.(changed);
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            return;
        }
        const results = this._requireResults();
        const forceInit = changed.has('nodeId') || changed.has('runIndex');
        this._syncRuns(results, forceInit === true);
    }

    /**
     * @param {number} runIndex
     */
    _selectRun(runIndex: number) {
        const results = this._requireResults();
        findNodeRunResult(results, runIndex);
        this._selectedRunIndex = runIndex;
        this._followLatest = isLatestNodeRun(results, runIndex);
        this._ensurePathForResult(findNodeRunResult(results, runIndex));
        this._valueSide = 'new';
    }

    /**
     * @param {unknown[]} results
     * @param {number} delta
     */
    _stepRun(results: readonly unknown[], delta: number) {
        if (this._selectedRunIndex === null) {
            throw new Error('flows-node-run-result-modal: run is not selected');
        }
        let current = -1;
        for (let i = 0; i < results.length; i += 1) {
            const item = results[i];
            if (!isPlainObject(item)) {
                throw new Error('flows-node-run-result-modal: result must be an object');
            }
            if (item.run_index === this._selectedRunIndex) {
                current = i;
                break;
            }
        }
        if (current < 0) {
            throw new Error('flows-node-run-result-modal: selected run_index is missing');
        }
        const next = current + delta;
        if (next < 0 || next >= results.length) {
            return;
        }
        const nextItem = results[next];
        if (!isPlainObject(nextItem) || typeof nextItem.run_index !== 'number' || !Number.isFinite(nextItem.run_index)) {
            throw new Error('flows-node-run-result-modal: run_index is required');
        }
        this._selectRun(Math.floor(nextItem.run_index));
    }

    /**
     * @param {string} path
     */
    _selectPath(path: string) {
        this._selectedPath = path;
        this._valueSide = 'new';
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} event
     */
    _onSearchChange(event: CustomEvent) {
        const raw = event.detail && event.detail.value;
        if (typeof raw !== 'string') {
            throw new TypeError('flows-node-run-result-modal: search change expects string detail.value');
        }
        this._diffQuery = raw;
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} event
     */
    _onSideChange(event: CustomEvent) {
        const next = event.detail && event.detail.value;
        if (next !== 'new' && next !== 'old') {
            throw new Error('flows-node-run-result-modal: value side must be new or old');
        }
        this._valueSide = next;
    }

    _copySelected() {
        const results = this._requireResults();
        if (this._selectedRunIndex === null) {
            throw new Error('flows-node-run-result-modal: run is not selected');
        }
        const result = findNodeRunResult(results, this._selectedRunIndex);
        let text = '';
        if (result.kind === 'error') {
            if (typeof result.error !== 'string') {
                throw new Error('flows-node-run-result-modal: error text is required');
            }
            text = result.error;
        } else {
            if (this._selectedPath.length === 0) {
                throw new Error('flows-node-run-result-modal: no field selected');
            }
            const entry = findDiffEntryByPath(result, this._selectedPath);
            const inspectValue = resolveInspectValue(entry, this._valueSide);
            text = serializeNodeRunValue(inspectValue);
        }
        this.copyToClipboard(text, {
            success_i18n_key: 'flows:node_run_result_modal.toast_copied',
            error_i18n_key: 'flows:node_run_result_modal.toast_copy_failed',
        });
    }

    _nodeTitle(result: Record<string, unknown>) {
        const nodes = getBranchNodes(this._editor.state);
        const node = nodes[this.nodeId];
        if (isPlainObject(node) && typeof node.name === 'string' && node.name.length > 0) {
            return node.name;
        }
        if (typeof result.node_id === 'string' && result.node_id.length > 0) {
            return result.node_id;
        }
        return this.nodeId;
    }

    override renderHeader() {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0 || this._selectedRunIndex === null) {
            return this.t('node_run_result_modal.title');
        }
        const result = findNodeRunResult(this._requireResults(), this._selectedRunIndex);
        const typeLabel = typeof result.node_type === 'string' && result.node_type.length > 0
            ? result.node_type
            : '';
        return html`${this._nodeTitle(result)}${typeLabel.length > 0 ? html`<span class="header-sub"> · ${typeLabel}</span>` : nothing}`;
    }

    override renderHeaderActions() {
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                title=${this.t('node_run_result_modal.copy')}
                aria-label=${this.t('node_run_result_modal.copy_aria')}
                @click=${() => this._copySelected()}
            >
                <platform-icon name="copy" size="16"></platform-icon>
            </platform-button>
        `;
    }

    /**
     * @param {unknown[]} results
     */
    _renderRunsRail(results: readonly unknown[]) {
        if (results.length < 2) {
            return '';
        }
        return html`
            <div class="content-panel runs-rail">
                <div class="content-panel-head">
                    <span>${this.t('node_run_result_modal.runs_title')}</span>
                    <div class="runs-nav">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('node_run_result_modal.run_prev')}
                            @click=${() => this._stepRun(results, -1)}
                        >
                            <platform-icon name="chevron-left" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('node_run_result_modal.run_next')}
                            @click=${() => this._stepRun(results, 1)}
                        >
                            <platform-icon name="chevron-right" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="content-panel-body">
                    <div class="runs-list">
                        ${results.map((item, index) => {
                            if (!isPlainObject(item)) {
                                throw new Error('flows-node-run-result-modal: result must be an object');
                            }
                            const runIndex = item.run_index;
                            if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
                                throw new Error('flows-node-run-result-modal: run_index is required');
                            }
                            const active = runIndex === this._selectedRunIndex;
                            const tone = item.kind === 'error' ? 'error' : 'ok';
                            const headline = buildNodeRunHeadline(item, (key: string, params: unknown) => this._translate(key, params));
                            const durationMs = item.duration_ms;
                            const meta = [];
                            meta.push(this.t('node_run_result_modal.run_label', {
                                n: String(index + 1),
                                total: String(results.length),
                            }));
                            if (typeof durationMs === 'number' && Number.isFinite(durationMs)) {
                                meta.push(this.t('canvas_run_result.duration_ms', {
                                    ms: String(Math.round(durationMs)),
                                }));
                            }
                            return html`
                                <article
                                    class="run-row"
                                    role="button"
                                    tabindex="0"
                                    data-run-index=${String(Math.floor(runIndex))}
                                    data-active=${active ? 'true' : 'false'}
                                    data-tone=${tone}
                                    @click=${() => this._selectRun(Math.floor(runIndex))}
                                    @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._selectRun(Math.floor(runIndex)))}
                                >
                                    <span class="run-row-title">${headline.length > 0 ? headline : this.t('canvas_run_result.empty')}</span>
                                    <span class="run-row-meta">${meta.join(' · ')}</span>
                                </article>
                            `;
                        })}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * @param {Record<string, unknown>} result
     */
    _renderFields(result: Record<string, unknown>) {
        const rows = buildNodeRunChangeRows(result, (key: string, params: unknown) => this._translate(key, params));
        const query = this._diffQuery.trim().toLowerCase();
        const visible = query.length === 0
            ? rows
            : rows.filter((row) => row.path.toLowerCase().includes(query) || row.label.toLowerCase().includes(query));
        return html`
            <div class="content-panel fields-pane">
                <div class="content-panel-head">
                    <span>${this.t('node_run_result_modal.fields_title')}</span>
                    <platform-modal-search-field
                        layout="toolbar"
                        .value=${this._diffQuery}
                        placeholder=${this.t('node_run_result_modal.search_placeholder')}
                        @change=${this._onSearchChange}
                    ></platform-modal-search-field>
                </div>
                <div class="content-panel-body">
                    ${visible.length === 0 ? html`<platform-empty-state title=${this.t('node_run_result_modal.empty_diff')}></platform-empty-state>` : html`
                        <div class="fields-list">
                            ${visible.map((row) => html`
                                <article
                                    class="field-row"
                                    role="button"
                                    tabindex="0"
                                    data-path=${row.path}
                                    data-change-type=${row.changeType}
                                    data-active=${row.path === this._selectedPath ? 'true' : 'false'}
                                    @click=${() => this._selectPath(row.path)}
                                    @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._selectPath(row.path))}
                                >
                                    <span class="field-badge" title=${row.badgeLabel}>${row.badge}</span>
                                    <div>
                                        <div class="field-label">${row.label}</div>
                                        <div class="field-type">${row.typeLabel}</div>
                                    </div>
                                </article>
                            `)}
                        </div>
                    `}
                </div>
            </div>
        `;
    }

    /**
     * @param {Record<string, unknown>} result
     */
    _renderViewer(result: Record<string, unknown>) {
        if (result.kind === 'error') {
            const errorText = typeof result.error === 'string' ? result.error : '';
            return html`
                <div class="content-panel viewer-pane">
                    <div class="content-panel-head">${this.t('node_run_result_modal.error_title')}</div>
                    <div class="content-panel-body">
                        <pre class="error-text">${errorText}</pre>
                    </div>
                </div>
            `;
        }
        if (this._selectedPath.length === 0) {
            return html`
                <div class="content-panel viewer-pane">
                    <platform-empty-state title=${this.t('node_run_result_modal.no_selection')}></platform-empty-state>
                </div>
            `;
        }
        const entry = findDiffEntryByPath(result, this._selectedPath);
        const changeType = entry.change_type;
        const showSides = changeType === 'changed';
        const inspectValue = resolveInspectValue(entry, this._valueSide);
        return html`
            <div class="content-panel viewer-pane">
                ${showSides ? html`
                    <div class="viewer-toolbar">
                        <platform-segmented-control
                            density="dense"
                            .value=${this._valueSide}
                            .items=${[
                                { value: 'old', label: this.t('node_run_result_modal.value_old') },
                                { value: 'new', label: this.t('node_run_result_modal.value_new') },
                            ]}
                            @change=${this._onSideChange}
                        ></platform-segmented-control>
                    </div>
                ` : nothing}
                <flows-node-run-value-view
                    .value=${inspectValue}
                    .rootPath=${this._selectedPath}
                ></flows-node-run-value-view>
            </div>
        `;
    }

    override renderBody() {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            return html``;
        }
        const results = this._requireResults();
        if (this._selectedRunIndex === null) {
            return html``;
        }
        const result = findNodeRunResult(results, this._selectedRunIndex);
        const runLabel = this.t('node_run_result_modal.run_label', {
            n: String(this._runPosition(results) + 1),
            total: String(results.length),
        });
        return html`
            <div class="node-run-result-body">
                <div class="run-row-meta">${runLabel}${typeof result.duration_ms === 'number' && Number.isFinite(result.duration_ms)
                    ? ` · ${this.t('canvas_run_result.duration_ms', { ms: String(Math.round(result.duration_ms)) })}`
                    : ''}${result.kind === 'ok' ? ` · ${this.t('canvas_run_result.changes_count', { count: String(countNodeRunDiffChanges(result)) })}` : ''}</div>
                <div class="workspace">
                    ${this._renderRunsRail(results)}
                    ${result.kind === 'error' ? nothing : this._renderFields(result)}
                    ${this._renderViewer(result)}
                </div>
            </div>
        `;
    }

    /**
     * @param {unknown[]} results
     */
    _runPosition(results: readonly unknown[]) {
        for (let i = 0; i < results.length; i += 1) {
            const item = results[i];
            if (isPlainObject(item) && item.run_index === this._selectedRunIndex) {
                return i;
            }
        }
        throw new Error('flows-node-run-result-modal: selected run_index is missing');
    }
}

customElements.define('flows-node-run-result-modal', FlowsNodeRunResultModal);
registerModalKind(FlowsNodeRunResultModal.modalKind, 'flows-node-run-result-modal');

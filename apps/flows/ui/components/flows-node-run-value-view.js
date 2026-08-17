/**
 * Типизированный просмотр значения результата ноды.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-code-editor.js';
import '@platform/lib/components/platform-json-editor.js';
import '@platform/lib/components/platform-markdown-editor.js';
import '@platform/lib/components/platform-segmented-control.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import {
    classifyNodeRunValue,
    serializeNodeRunValue,
} from '../_helpers/flows-node-run-result.js';
import './flows-json-tree.js';

export class FlowsNodeRunValueView extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        value: { attribute: false },
        rootPath: { type: String, attribute: 'root-path' },
        _structureView: { state: true },
        _treePath: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-width: 0;
                min-height: 0;
                flex: 1;
            }
            .empty {
                margin: 0;
                padding: var(--space-6);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }
            .scalar {
                margin: 0;
                padding: var(--space-6);
                font-family: var(--font-mono);
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                word-break: break-word;
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .viewer {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: auto;
            }
            .status-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
            }
            .status-card {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }
            .status-card[data-ok='true'] {
                border-color: var(--success-border);
                background: var(--success-bg);
            }
            .status-card[data-ok='false'] {
                border-color: var(--error-border);
                background: var(--error-bg);
            }
            .status-key {
                font-weight: var(--font-semibold);
                min-width: 0;
                word-break: break-word;
            }
            .status-state {
                margin-left: auto;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }
            .status-latency {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            platform-markdown-editor,
            platform-code-editor,
            platform-json-editor,
            flows-json-tree {
                flex: 1 1 auto;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.rootPath = '';
        this._structureView = 'tree';
        this._treePath = '';
    }

    /**
     * @param {CustomEvent<{ path?: unknown, value?: unknown }>} event
     */
    _onTreeSelect(event) {
        const detail = event.detail;
        if (detail === null || typeof detail !== 'object' || typeof detail.path !== 'string') {
            throw new Error('flows-node-run-value-view: tree select requires detail.path');
        }
        this._treePath = detail.path;
        this.emit('select', { path: detail.path, value: detail.value });
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} event
     */
    _onStructureChange(event) {
        const next = event.detail && event.detail.value;
        if (next !== 'tree' && next !== 'json') {
            throw new Error('flows-node-run-value-view: structure view must be tree or json');
        }
        this._structureView = next;
    }

    /**
     * @param {unknown} parsed
     */
    _renderStructure(parsed) {
        const rootPath = typeof this.rootPath === 'string' ? this.rootPath : '';
        return html`
            <div class="toolbar">
                <platform-segmented-control
                    density="dense"
                    .value=${this._structureView}
                    .items=${[
                        { value: 'tree', label: this.t('node_run_result_modal.view_tree') },
                        { value: 'json', label: this.t('node_run_result_modal.view_json') },
                    ]}
                    @change=${this._onStructureChange}
                ></platform-segmented-control>
            </div>
            <div class="viewer">
                ${this._structureView === 'json' ? html`
                    <platform-json-editor
                        readonly
                        fill-parent
                        .showToolbar=${false}
                        .value=${formatJsonPretty(parsed)}
                    ></platform-json-editor>
                ` : html`
                    <flows-json-tree
                        .value=${parsed}
                        .rootPath=${rootPath}
                        .selectedPath=${this._treePath}
                        @select=${this._onTreeSelect}
                    ></flows-json-tree>
                `}
            </div>
        `;
    }

    /**
     * @param {Record<string, unknown>} value
     */
    _renderStatusMap(value) {
        const entries = Object.entries(value);
        return html`
            <div class="status-list">
                ${entries.map(([key, entry]) => {
                    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
                        throw new Error('flows-node-run-value-view: status entry must be an object');
                    }
                    const ok = entry.ok === true;
                    const latencyMs = entry.latency_ms;
                    return html`
                        <div class="status-card" data-ok=${ok ? 'true' : 'false'}>
                            <span class="status-key">${key}</span>
                            <span class="status-state">${ok
                                ? this.t('node_run_result_modal.status_ok')
                                : this.t('node_run_result_modal.status_fail')}</span>
                            ${typeof latencyMs === 'number' && Number.isFinite(latencyMs) ? html`
                                <span class="status-latency">${this.t('canvas_run_result.duration_ms', {
                                    ms: String(Math.round(latencyMs)),
                                })}</span>
                            ` : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        const classified = classifyNodeRunValue(this.value);
        if (classified.kind === 'null' || classified.kind === 'empty') {
            return html`<p class="empty">${this.t('node_run_result_modal.empty_value')}</p>`;
        }
        if (classified.kind === 'boolean') {
            const text = classified.parsed === true
                ? this.t('canvas_run_result.value_true')
                : this.t('canvas_run_result.value_false');
            return html`<p class="scalar">${text}</p>`;
        }
        if (classified.kind === 'number') {
            return html`<p class="scalar">${serializeNodeRunValue(this.value)}</p>`;
        }
        if (classified.kind === 'string') {
            return html`
                <platform-code-editor
                    language="text"
                    readonly
                    fill-parent
                    .value=${classified.parsed}
                ></platform-code-editor>
            `;
        }
        if (classified.kind === 'markdown') {
            if (typeof classified.parsed !== 'string') {
                throw new Error('flows-node-run-value-view: markdown requires string parsed');
            }
            return html`
                <platform-markdown-editor
                    readonly
                    view-mode="preview"
                    .showHeader=${false}
                    .showHint=${false}
                    .value=${classified.parsed}
                ></platform-markdown-editor>
            `;
        }
        if (classified.kind === 'status_map') {
            return this._renderStatusMap(/** @type {Record<string, unknown>} */ (classified.parsed));
        }
        if (classified.kind === 'json_string' || classified.kind === 'array' || classified.kind === 'object') {
            return this._renderStructure(classified.parsed);
        }
        throw new Error(`flows-node-run-value-view: unsupported kind ${classified.kind}`);
    }
}

customElements.define('flows-node-run-value-view', FlowsNodeRunValueView);

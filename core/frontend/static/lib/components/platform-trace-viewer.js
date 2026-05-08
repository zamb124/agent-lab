/**
 * Универсальный просмотр дерева trace: режимы tree / timeline, поиск, выбор span.
 * Данные: массив корневых узлов в форме ответа API (после build_span_tree).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import {
    normalizeTraceRoots,
    computeTraceTimeRangeMs,
    flattenTimelineRows,
    pruneTraceViewNodes,
    collectMatchingSpanIds,
    buildParentMap,
    ancestorIdsForMatches,
    spanMatchesQuery,
    serviceHueCssVar,
    treeDurationBarPct,
} from '../utils/trace-view-model.js';

export class PlatformTraceViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        roots: { type: Array },
        displayMode: { type: String },
        _search: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .mode-group {
                display: inline-flex;
                gap: var(--space-1);
            }
            .mode-btn {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 50%);
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
                color: var(--text-secondary);
                cursor: pointer;
                transition:
                    background var(--duration-fast, 0.2s) ease,
                    color var(--duration-fast, 0.2s) ease,
                    transform var(--duration-fast, 0.2s) ease;
                flex-shrink: 0;
            }
            .mode-btn:hover:not(:disabled) {
                background: var(--glass-tint-strong, rgba(255, 255, 255, 0.08));
                color: var(--text-primary);
                transform: scale(1.06);
            }
            .mode-btn--active {
                background: var(--accent);
                color: var(--platform-btn-primary-text, #fff);
            }
            .mode-btn--active:hover:not(:disabled) {
                background: var(--platform-btn-primary-hover, var(--accent));
                color: var(--platform-btn-primary-text, #fff);
            }
            .mode-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                transform: none;
            }
            .mode-btn platform-icon {
                display: flex;
            }
            .search-wrap {
                flex: 1;
                min-width: 160px;
            }
            .timeline-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                width: 100%;
            }
            .empty {
                padding: var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .tree {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .row {
                display: grid;
                grid-template-columns: 22px minmax(0, 1fr) 56px;
                gap: var(--space-1) var(--space-2);
                align-items: center;
                padding: var(--space-2) var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }
            .row:last-child {
                border-bottom: none;
            }
            .row[data-match='1'] {
                outline: 1px solid var(--accent);
                outline-offset: -1px;
            }
            .row[data-error='1'] .title {
                color: var(--error);
            }
            .toggle {
                width: 22px;
                height: 22px;
                padding: 0;
                border: none;
                background: transparent;
                cursor: pointer;
                color: var(--text-secondary);
                font-size: 10px;
                line-height: 1;
            }
            .toggle:disabled {
                visibility: hidden;
            }
            .main {
                min-width: 0;
            }
            .title-row {
                display: flex;
                align-items: baseline;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .title {
                font-weight: var(--font-medium);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
            }
            .title:hover {
                color: var(--accent);
            }
            .badge {
                font-size: var(--text-xs);
                padding: 1px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }
            .bar-cell {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 2px;
            }
            .bar-track {
                height: 5px;
                background: var(--glass-border-subtle);
                border-radius: 2px;
                overflow: hidden;
            }
            .bar-fill {
                height: 100%;
                border-radius: 2px;
                min-width: 2px;
            }
            .dur {
                font-size: 10px;
                color: var(--text-tertiary);
                text-align: right;
            }
            .timeline {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .tl-row {
                display: grid;
                grid-template-columns: minmax(120px, 1fr) minmax(0, 3fr);
                gap: var(--space-2);
                align-items: center;
                padding: var(--space-1) var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }
            .tl-row:last-child {
                border-bottom: none;
            }
            .tl-label {
                font-size: var(--text-xs);
                color: var(--text-primary);
                padding-left: var(--depth-pad, 0);
                cursor: pointer;
            }
            .tl-label:hover {
                color: var(--accent);
            }
            .tl-track {
                position: relative;
                height: 18px;
                background: var(--glass-border-subtle);
                border-radius: var(--radius-sm);
            }
            .tl-bar {
                position: absolute;
                top: 4px;
                height: 10px;
                border-radius: 2px;
                min-width: 3px;
            }
        `,
    ];

    constructor() {
        super();
        this.roots = [];
        this.displayMode = 'tree';
        this._search = '';
        /** @type {Set<string>} */
        this._collapsed = new Set();
    }

    /**
     * @param {import('../utils/trace-view-model.js').TraceViewNode} node
     * @param {import('../utils/trace-view-model.js').TraceViewNode|null} parent
     * @param {number} depth
     * @param {number|null} traceSpanMs
     * @param {Set<string>} matchedIds
     */
    _renderTreeNode(node, parent, depth, traceSpanMs, matchedIds) {
        const hasKids = node.childCount > 0;
        const collapsed = hasKids && this._collapsed.has(node.id);
        const q = this._search;
        const isMatch = q.length > 0 && matchedIds.has(node.id);
        const barPct = treeDurationBarPct(node, parent, traceSpanMs);
        const barColor = serviceHueCssVar(node.serviceKey);
        const dur =
            node.durationMs != null
                ? html`<span class="dur">${node.durationMs} ms</span>`
                : html`<span class="dur"></span>`;

        const rows = [
            html`
                <div
                    class="row"
                    style="padding-left: ${depth * 12}px"
                    data-match=${isMatch ? '1' : '0'}
                    data-error=${node.hasError ? '1' : '0'}
                >
                    <button
                        type="button"
                        class="toggle"
                        ?disabled=${!hasKids}
                        @click=${() => this._toggleCollapse(node.id)}
                    >
                        ${hasKids ? (collapsed ? '+' : '-') : ''}
                    </button>
                    <div class="main">
                        <div class="title-row">
                            <span class="title" @click=${() => this._select(node.raw)}>${node.title}</span>
                            <span class="badge">${this.t(`trace_viewer.kind_${node.uiKind}`)}</span>
                        </div>
                        ${node.subtitle.length > 0 ? html`<div class="meta">${node.subtitle}</div>` : nothing}
                    </div>
                    <div class="bar-cell">
                        <div class="bar-track">
                            <div
                                class="bar-fill"
                                style="width:${barPct}%; background:${barColor};"
                            ></div>
                        </div>
                        ${dur}
                    </div>
                </div>
            `,
        ];
        if (!collapsed) {
            for (const c of node.children) {
                rows.push(...this._renderTreeNode(c, node, depth + 1, traceSpanMs, matchedIds));
            }
        }
        return rows;
    }

    /** @param {string} id */
    _toggleCollapse(id) {
        if (this._collapsed.has(id)) {
            this._collapsed.delete(id);
        } else {
            this._collapsed.add(id);
        }
        this.requestUpdate();
    }

    /** @param {import('../utils/trace-view-model.js').TraceSpanRaw} span */
    _select(span) {
        this.emit('trace-span-select', { span });
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('roots')) {
            const roots = Array.isArray(this.roots) ? this.roots : [];
            if (this.displayMode === 'timeline' && computeTraceTimeRangeMs(roots) == null) {
                this.displayMode = 'tree';
            }
        }
    }

    /** @param {CustomEvent<{ value?: string }>} e */
    _onSearchInput(e) {
        const d = e.detail;
        if (d == null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('platform-trace-viewer: platform-field must emit detail.value');
        }
        this._search = d.value.trim().toLowerCase();
        this._applySearchExpand();
        this.requestUpdate();
    }

    _applySearchExpand() {
        const q = this._search;
        const roots = this.roots;
        if (!Array.isArray(roots) || roots.length === 0 || q.length === 0) {
            return;
        }
        const parentMap = buildParentMap(
            roots.map((r) => {
                if (typeof r !== 'object' || r === null || typeof r.span_id !== 'string') {
                    throw new Error('platform-trace-viewer: invalid root span');
                }
                return /** @type {import('../utils/trace-view-model.js').TraceSpanRaw} */ (r);
            }),
        );
        const matched = collectMatchingSpanIds(
            roots.map((r) => /** @type {import('../utils/trace-view-model.js').TraceSpanRaw} */ (r)),
            (r) => spanMatchesQuery(r, q),
        );
        const anc = ancestorIdsForMatches(matched, parentMap);
        for (const id of anc) {
            this._collapsed.delete(id);
        }
    }

    render() {
        const roots = Array.isArray(this.roots) ? this.roots : [];
        if (roots.length === 0) {
            return html`<div class="empty">${this.t('trace_viewer.empty')}</div>`;
        }

        const normalized = normalizeTraceRoots(roots);
        const q = this._search;
        let matchedIds = new Set();
        let visible = normalized;
        if (q.length > 0) {
            matchedIds = collectMatchingSpanIds(
                roots.map((r) => /** @type {import('../utils/trace-view-model.js').TraceSpanRaw} */ (r)),
                (r) => spanMatchesQuery(r, q),
            );
            visible = pruneTraceViewNodes(normalized, matchedIds);
        }

        const timeRange = computeTraceTimeRangeMs(roots);
        const timelineOk = timeRange != null;
        const traceSpanMs = timeRange != null ? timeRange.max - timeRange.min : null;

        const mode =
            this.displayMode === 'timeline' && timelineOk ? 'timeline' : 'tree';

        if (q.length > 0 && visible.length === 0) {
            return html`
                <div class="toolbar">
                    <div class="search-wrap">
                        <platform-field
                            type="string"
                            input-type="search"
                            mode="edit"
                            .placeholder=${this.t('trace_viewer.search_placeholder')}
                            .value=${this._search}
                            @change=${this._onSearchInput}
                        ></platform-field>
                    </div>
                </div>
                <div class="empty">${this.t('trace_viewer.search_no_results')}</div>
            `;
        }

        return html`
            <div class="toolbar">
                <div class="mode-group" role="group" aria-label=${this.t('trace_viewer.mode_group_label')}>
                    <button
                        type="button"
                        class="mode-btn ${mode === 'tree' ? 'mode-btn--active' : ''}"
                        title=${this.t('trace_viewer.mode_tree')}
                        aria-label=${this.t('trace_viewer.mode_tree')}
                        aria-pressed=${mode === 'tree' ? 'true' : 'false'}
                        @click=${() => {
                            this.displayMode = 'tree';
                            this.requestUpdate();
                        }}
                    >
                        <platform-icon name="trace-tree" size="18"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="mode-btn ${mode === 'timeline' ? 'mode-btn--active' : ''}"
                        title=${this.t('trace_viewer.mode_timeline')}
                        aria-label=${this.t('trace_viewer.mode_timeline')}
                        aria-pressed=${mode === 'timeline' ? 'true' : 'false'}
                        ?disabled=${!timelineOk}
                        @click=${() => {
                            if (timelineOk) {
                                this.displayMode = 'timeline';
                                this.requestUpdate();
                            }
                        }}
                    >
                        <platform-icon name="trace-timeline" size="18"></platform-icon>
                    </button>
                </div>
                <div class="search-wrap">
                    <platform-field
                        type="string"
                        input-type="search"
                        mode="edit"
                        .placeholder=${this.t('trace_viewer.search_placeholder')}
                        .value=${this._search}
                        @change=${this._onSearchInput}
                    ></platform-field>
                </div>
                ${!timelineOk
                    ? html`<div class="timeline-hint">${this.t('trace_viewer.timeline_unavailable')}</div>`
                    : nothing}
            </div>
            ${mode === 'tree'
                ? html`
                      <div class="tree">
                          ${visible.flatMap((n) =>
                              this._renderTreeNode(n, null, 0, traceSpanMs, matchedIds),
                          )}
                      </div>
                  `
                : this._renderTimeline(visible, timeRange, matchedIds)}
        `;
    }

    /**
     * @param {import('../utils/trace-view-model.js').TraceViewNode[]} visibleRoots
     * @param {{ min: number, max: number }|null} timeRange
     * @param {Set<string>} matchedIds
     */
    _renderTimeline(visibleRoots, timeRange, matchedIds) {
        if (timeRange == null) {
            return nothing;
        }
        const { min, max } = timeRange;
        const q = this._search;
        /** @type {Array<{ node: import('../utils/trace-view-model.js').TraceViewNode, depth: number, leftPct: number, widthPct: number }>} */
        const rows = [];
        for (const root of visibleRoots) {
            rows.push(...flattenTimelineRows(root, min, max, 0));
        }
        return html`
            <div class="timeline">
                ${rows.map((r) => {
                    const isMatch = q.length > 0 && matchedIds.has(r.node.id);
                    const color = serviceHueCssVar(r.node.serviceKey);
                    return html`
                        <div class="tl-row" data-match=${isMatch ? '1' : '0'}>
                            <div
                                class="tl-label"
                                style="--depth-pad: ${r.depth * 10}px"
                                @click=${() => this._select(r.node.raw)}
                            >
                                ${r.node.title}
                            </div>
                            <div class="tl-track">
                                <div
                                    class="tl-bar"
                                    style="left:${r.leftPct}%; width:${r.widthPct}%; background:${color};"
                                ></div>
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('platform-trace-viewer', PlatformTraceViewer);

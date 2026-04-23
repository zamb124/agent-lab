/**
 * Единая модалка библиотеки: выбор tool/flow (LLM, дроп subflow) и шаблонов code-ноды.
 * Различается только источником данных и фильтрами (`_modalKind` из стека модалок).
 *
 * kinds: `flows.tool_picker` | `flows.code_node_templates` → один tagName.
 */

import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import { embedAssistantMarkdownToHtml } from '@platform/lib/embed-chat/embed-chat-markdown.js';
import { registryItemIconName, registryItemTitle } from '../_helpers/flows-registry-item-icon.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import { getNodeTypeMeta } from '../constants/node-icons.js';

function _templatesFromResult(result) {
    if (result && typeof result === 'object' && Array.isArray(result.templates)) {
        return result.templates;
    }
    return [];
}

function _lower(s) {
    if (typeof s === 'string' && s.length > 0) {
        return s.toLowerCase();
    }
    return '';
}

function _tagsFromItem(t) {
    if (t && Array.isArray(t.tags)) {
        return t.tags.filter((x) => typeof x === 'string' && x.length > 0);
    }
    return [];
}

export class FlowsLibraryPickerModal extends PlatformModal {
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        onPick: { type: Object, attribute: false },
        onCommit: { type: Object, attribute: false },
        pickMode: { type: String, attribute: 'pick-mode' },
        _search: { state: true },
        _sourceTab: { state: true },
        _activeTag: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .bar {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            .tag-strip {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                flex: 1 1 200px;
                min-width: 0;
            }
            .tag-strip--filler {
                flex: 1 1 200px;
                min-width: 0;
                min-height: 0;
            }
            .tag {
                font-size: var(--text-xs);
                padding: 4px 8px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .tag.is-on {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            .search-wrap {
                flex: 0 1 240px;
                min-width: 160px;
            }
            .tabs {
                display: flex;
                gap: var(--space-1);
                margin-bottom: var(--space-3);
            }
            .tab {
                padding: 6px 12px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .tab.is-on {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent-subtle);
            }
            .lib-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
                min-height: 200px;
            }
            .lib-card {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                text-align: left;
                padding: var(--space-3);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast),
                    transform var(--duration-fast);
                box-sizing: border-box;
            }
            .lib-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                transform: translateY(-1px);
            }
            .lib-card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .lib-card-icon-row {
                display: flex;
                justify-content: center;
                margin-bottom: var(--space-2);
            }
            .lib-card-icon {
                width: 48px;
                height: 48px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                flex-shrink: 0;
            }
            .lib-card-icon[data-kind='flow'] {
                background: linear-gradient(135deg, #bb8fce 0%, #8e44ad 100%);
            }
            .lib-card-icon[data-kind='mcp'] {
                background: linear-gradient(135deg, #82e0aa 0%, #58d68d 100%);
            }
            .lib-card-icon[data-kind='code'] {
                background: linear-gradient(135deg, #5dade2 0%, #5499c7 100%);
            }
            .lib-card-title {
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
                color: var(--text-primary);
            }
            .lib-card-desc {
                flex: 1 1 auto;
                min-height: 0;
            }
            .lib-md {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
                text-align: left;
                max-height: calc(1.35em * 4);
                overflow: hidden;
            }
            .lib-md p {
                margin: 0 0 0.35em 0;
            }
            .lib-md p:last-child {
                margin-bottom: 0;
            }
            .lib-md strong {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .lib-md code {
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: 0.92em;
                background: var(--glass-tint-medium);
                padding: 0.1em 0.25em;
                border-radius: var(--radius-sm);
            }
            .lib-md ul,
            .lib-md ol {
                margin: 0.25em 0 0.35em 1em;
                padding: 0;
            }
            .lib-card-meta {
                margin-top: var(--space-2);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .lib-chip {
                font-size: 10px;
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                color: var(--text-tertiary);
                word-break: break-all;
            }
            .lib-empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                padding: var(--space-4);
                text-align: center;
            }
        `,
    ];

    constructor() {
        super();
        this.onPick = null;
        this.onCommit = null;
        this.pickMode = 'all';
        this._search = '';
        this._sourceTab = 'catalog';
        this._activeTag = '';
        this._toolsAll = this.useOp('flows/tools_all');
        this._codeTemplates = this.useOp('flows/code_templates');
    }

    _isCodeNodeTemplates() {
        return this._modalKind === 'flows.code_node_templates';
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._search = '';
            this._activeTag = '';
            this._sourceTab = 'catalog';
            this.size = 'full';
            if (this._isCodeNodeTemplates()) {
                void this._codeTemplates.run({
                    language: 'python',
                    node_type: 'tool',
                });
            }
            void this._toolsAll.run({ limit: 2000, offset: 0 });
        }
    }

    _toolsAllItems() {
        const r = this._toolsAll.lastResult;
        if (!isPlainObject(r) || !Array.isArray(r.items)) {
            return [];
        }
        return r.items.filter((x) => isPlainObject(x));
    }

    _templateListRaw() {
        return _templatesFromResult(this._codeTemplates.lastResult);
    }

    _toolRegistryRows() {
        const list = this._toolsAllItems().filter((t) => t.item_type !== 'flow');
        const tagF = this._activeTag;
        const q = _lower(this._search);
        return list.filter((t) => {
            if (tagF.length > 0) {
                const tags = _tagsFromItem(t);
                if (!tags.includes(tagF)) {
                    return false;
                }
            }
            if (q.length === 0) {
                return true;
            }
            const id = typeof t.tool_id === 'string' ? t.tool_id : '';
            const title = typeof t.title === 'string' ? t.title : '';
            const desc = typeof t.description === 'string' ? t.description : '';
            return _lower(title).indexOf(q) >= 0
                || _lower(desc).indexOf(q) >= 0
                || _lower(id).indexOf(q) >= 0;
        });
    }

    _filterCatalogRows() {
        const list = this._templateListRaw();
        const tagF = this._activeTag;
        const q = _lower(this._search);
        return list.filter((t) => {
            if (!isPlainObject(t)) {
                return false;
            }
            if (tagF.length > 0) {
                const tags = _tagsFromItem(t);
                if (!tags.includes(tagF)) {
                    return false;
                }
            }
            if (q.length === 0) {
                return true;
            }
            const id = typeof t.id === 'string' ? t.id : '';
            const name = typeof t.name === 'string' ? t.name : '';
            const desc = typeof t.description === 'string' ? t.description : '';
            return _lower(name).indexOf(q) >= 0
                || _lower(desc).indexOf(q) >= 0
                || _lower(id).indexOf(q) >= 0;
        });
    }

    _allTagSet() {
        const s = new Set();
        for (const t of this._templateListRaw()) {
            if (isPlainObject(t)) {
                for (const x of _tagsFromItem(t)) {
                    s.add(x);
                }
            }
        }
        for (const t of this._toolsAllItems()) {
            if (isPlainObject(t) && t.item_type !== 'flow') {
                for (const x of _tagsFromItem(t)) {
                    s.add(x);
                }
            }
        }
        return Array.from(s).sort((a, b) => a.localeCompare(b));
    }

    _pickModeRows() {
        const list = this._toolsAllItems();
        const mode = this.pickMode;
        let rows = list;
        if (mode === 'flow_only') {
            rows = rows.filter((t) => t.item_type === 'flow');
        }
        const q = _lower(this._search);
        if (q.length === 0) {
            return rows;
        }
        return rows.filter((t) => {
            const id = typeof t.tool_id === 'string' ? t.tool_id : '';
            const title = typeof t.title === 'string' ? t.title : '';
            const desc = typeof t.description === 'string' ? t.description : '';
            return _lower(id).indexOf(q) >= 0
                || _lower(title).indexOf(q) >= 0
                || _lower(desc).indexOf(q) >= 0;
        });
    }

    _onSearchInput(e) {
        const v = e.target;
        this._search = typeof v.value === 'string' ? v.value : '';
    }

    _setTag(t) {
        if (this._activeTag === t) {
            this._activeTag = '';
        } else {
            this._activeTag = t;
        }
    }

    _iconKindAttr(item) {
        if (item.item_type === 'flow') {
            return 'flow';
        }
        if (typeof item.mcp_server_id === 'string' && item.mcp_server_id.length > 0) {
            return 'mcp';
        }
        return 'code';
    }

    /**
     * Описания в Markdown. `marked` по сырой строке (см. `index.html`); иначе кавычки в JSON/примерах
     * уезжают в `&quot;` из-за `escapeHtml` в `embedAssistantMarkdownToHtml`. Fallback — embed-хелпер.
     */
    _mdDescription(text) {
        if (typeof text !== 'string' || text.length === 0) {
            return nothing;
        }
        const marked = globalThis.marked;
        if (marked && typeof marked.parse === 'function') {
            return html`<div class="lib-md">${unsafeHTML(
                marked.parse(text, { breaks: true, gfm: true }),
            )}</div>`;
        }
        const htmlStr = embedAssistantMarkdownToHtml(text);
        if (htmlStr.length === 0) {
            return nothing;
        }
        return html`<div class="lib-md">${unsafeHTML(htmlStr)}</div>`;
    }

    _renderFilterBar() {
        const isCode = this._isCodeNodeTemplates();
        const tagRow = isCode
            ? html`
                <div
                    class="tag-strip"
                    role="group"
                    aria-label=${this.t('code_node_templates_modal.tags_aria')}
                >
                    ${this._allTagSet().map(
                        (tag) => html`
                            <button
                                type="button"
                                class="tag ${this._activeTag === tag ? 'is-on' : ''}"
                                @click=${() => this._setTag(tag)}
                            >#${tag}</button>
                        `,
                    )}
                </div>
            `
            : html`<div class="tag-strip tag-strip--filler" role="presentation" aria-hidden="true"></div>`;
        return html`
            <div class="bar">
                ${tagRow}
                <div class="search-wrap">
                    <glass-input
                        type="search"
                        .value=${this._search}
                        @input=${this._onSearchInput}
                        placeholder=${this.t('tool_picker_modal.search_placeholder')}
                    ></glass-input>
                </div>
            </div>
        `;
    }

    _renderRegistryCard(t, { onSelect }) {
        const icon = registryItemIconName(t);
        const kindAttr = this._iconKindAttr(t);
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? t.description : '';
        const id = typeof t.tool_id === 'string' ? t.tool_id : '';
        return html`
            <button type="button" class="lib-card" @click=${onSelect}>
                <div class="lib-card-icon-row">
                    <div class="lib-card-icon" data-kind=${kindAttr}>
                        <platform-icon name=${icon} size="26"></platform-icon>
                    </div>
                </div>
                <div class="lib-card-title">${title}</div>
                <div class="lib-card-desc">${this._mdDescription(desc)}</div>
                <div class="lib-card-meta">
                    ${id.length > 0 ? html`<span class="lib-chip">${id}</span>` : null}
                    ${_tagsFromItem(t).map((g) => html`<span class="lib-chip">${g}</span>`)}
                </div>
            </button>
        `;
    }

    _pickToolLike(t) {
        const fn = this.onPick;
        this.close();
        if (typeof fn !== 'function') {
            return;
        }
        if (!isPlainObject(t) || typeof t.tool_id !== 'string' || t.tool_id.length === 0) {
            return;
        }
        const kind = t.item_type === 'flow' ? 'flow' : 'tool';
        queueMicrotask(() => {
            fn({
                kind,
                tool_id: t.tool_id,
                item: t,
            });
        });
    }

    _commitTemplate(t) {
        if (!isPlainObject(t) || typeof t.code !== 'string' || t.code.length === 0) {
            return;
        }
        const fn = this.onCommit;
        this.close();
        if (typeof fn === 'function') {
            const cfg = {
                code: t.code,
                language: typeof t.language === 'string' && t.language.length > 0 ? t.language : 'python',
            };
            const nodeName = typeof t.name === 'string' && t.name.length > 0
                ? t.name
                : (typeof t.id === 'string' ? t.id : 'code');
            queueMicrotask(() => {
                fn({ config: cfg, nodeName });
            });
        }
    }

    _commitTool(t) {
        if (!isPlainObject(t) || typeof t.tool_id !== 'string' || t.tool_id.length === 0) {
            return;
        }
        if (typeof t.code !== 'string' || t.code.length === 0) {
            this.toast('flows:code_node_templates_modal.toast_no_code', { type: 'error' });
            return;
        }
        const fn = this.onCommit;
        this.close();
        if (typeof fn === 'function') {
            const cfg = {
                tool_id: t.tool_id,
                code: t.code,
                language: 'python',
            };
            if (t.args_schema && typeof t.args_schema === 'object') {
                cfg.args_schema = t.args_schema;
            }
            if (t.parameters_schema && typeof t.parameters_schema === 'object') {
                cfg.parameters_schema = t.parameters_schema;
            }
            const nodeName = typeof t.title === 'string' && t.title.length > 0
                ? t.title
                : t.tool_id;
            queueMicrotask(() => {
                fn({ config: cfg, nodeName });
            });
        }
    }

    _catalogIconName() {
        return getNodeTypeMeta('code').icon;
    }

    _renderBodyToolPick() {
        const busy = this._toolsAll.busy;
        const rows = this._pickModeRows();
        if (busy && this._toolsAllItems().length === 0) {
            return html`${this._renderFilterBar()}<glass-spinner></glass-spinner>`;
        }
        if (rows.length === 0) {
            return html`
                ${this._renderFilterBar()}
                <div class="lib-empty">${this.t('tool_picker_modal.empty')}</div>
            `;
        }
        return html`
            ${this._renderFilterBar()}
            <div class="lib-grid" role="list">
                ${rows.map((t) => this._renderRegistryCard(t, { onSelect: () => this._pickToolLike(t) }))}
            </div>
        `;
    }

    _renderBodyCodeNode() {
        const rowCatalog = this._filterCatalogRows();
        const rowTools = this._toolRegistryRows();
        return html`
            ${this._renderFilterBar()}
            <div class="tabs">
                <button
                    type="button"
                    class="tab ${this._sourceTab === 'catalog' ? 'is-on' : ''}"
                    @click=${() => { this._sourceTab = 'catalog'; }}
                >${this.t('code_node_templates_modal.tab_catalog')}</button>
                <button
                    type="button"
                    class="tab ${this._sourceTab === 'registry' ? 'is-on' : ''}"
                    @click=${() => { this._sourceTab = 'registry'; }}
                >${this.t('code_node_templates_modal.tab_registry')}</button>
            </div>
            ${this._sourceTab === 'catalog' ? this._renderCatalogBlock(rowCatalog) : this._renderCodeRegistryBlock(rowTools)}
        `;
    }

    _renderCatalogBlock(rows) {
        if (this._codeTemplates.busy && this._templateListRaw().length === 0) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (rows.length === 0) {
            return html`<div class="lib-empty">${this.t('code_node_templates_modal.empty')}</div>`;
        }
        const icon = this._catalogIconName();
        return html`
            <div class="lib-grid">
                ${rows.map((t) => html`
                    <button type="button" class="lib-card" @click=${() => this._commitTemplate(t)}>
                        <div class="lib-card-icon-row">
                            <div class="lib-card-icon" data-kind="code">
                                <platform-icon name=${icon} size="26"></platform-icon>
                            </div>
                        </div>
                        <div class="lib-card-title">${typeof t.name === 'string' ? t.name : t.id}</div>
                        <div class="lib-card-desc">${this._mdDescription(
                            typeof t.description === 'string' ? t.description : '',
                        )}</div>
                        <div class="lib-card-meta">
                            ${typeof t.id === 'string' && t.id.length > 0
                                ? html`<span class="lib-chip">${t.id}</span>`
                                : nothing}
                            ${(Array.isArray(t.tags) ? t.tags : [])
                                .filter((g) => typeof g === 'string' && g.length > 0)
                                .map((g) => html`<span class="lib-chip">${g}</span>`)}
                        </div>
                    </button>
                `)}
            </div>
        `;
    }

    _renderCodeRegistryBlock(rows) {
        if (this._toolsAll.busy && this._toolsAllItems().filter((x) => x.item_type !== 'flow').length === 0) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (rows.length === 0) {
            return html`<div class="lib-empty">${this.t('code_node_templates_modal.empty_registry')}</div>`;
        }
        return html`
            <div class="lib-grid">
                ${rows.map((t) => this._renderRegistryCard(t, { onSelect: () => this._commitTool(t) }))}
            </div>
        `;
    }

    renderHeader() {
        if (this._isCodeNodeTemplates()) {
            return this.t('code_node_templates_modal.title');
        }
        if (this.pickMode === 'flow_only') {
            return this.t('tool_picker_modal.title_flow');
        }
        return this.t('tool_picker_modal.title');
    }

    renderBody() {
        if (this._isCodeNodeTemplates()) {
            return this._renderBodyCodeNode();
        }
        return this._renderBodyToolPick();
    }
}

const LIB_TAG = 'flows-library-picker-modal';

customElements.define(LIB_TAG, FlowsLibraryPickerModal);
registerModalKind('flows.tool_picker', LIB_TAG);
registerModalKind('flows.code_node_templates', LIB_TAG);

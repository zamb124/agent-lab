/**
 * Единая модалка библиотеки: выбор tool/flow (LLM, дроп subflow/MCP) и шаблонов code-ноды.
 * Различается только источником данных и фильтрами (`_modalKind` из стека модалок).
 *
 * kinds: `flows.tool_picker` | `flows.code_node_templates` → один tagName.
 * `flows.tool_picker`: `pickMode` = `all` | `flow_only` | `mcp_only`; при `all` — вкладки
 * Все / Code / Flows / MCP (фильтр по `flows/tools_all` без лишних запросов).
 */

import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '../components/common/flows-code-language-icon.js';
import { embedAssistantMarkdownToHtml } from '@platform/lib/embed-chat/embed-chat-markdown.js';
import { registryItemIconName, registryItemTitle } from '../_helpers/flows-registry-item-icon.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import { isMcpToolRegistryItem } from '../_helpers/flows-mcp-tool-registry.js';
import {
    FLOW_CODE_LANGUAGES,
    flowCodeLanguageLabel,
    normalizeFlowCodeLanguage,
} from '../_helpers/flows-code-languages.js';

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

function _hasInlineCode(t) {
    return t && typeof t.code === 'string' && t.code.trim().length > 0;
}

const PYTHON_KEYWORDS = new Set([
    'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
    'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import',
    'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while',
    'with', 'yield',
]);

function _sdkMethodName(raw) {
    let name = String(raw || '')
        .replace(/[^0-9A-Za-z_]/g, '_')
        .replace(/^_+|_+$/g, '');
    if (name.length === 0) {
        name = 'tool';
    }
    if (/^[0-9]/.test(name)) {
        name = `tool_${name}`;
    }
    if (name === 'call' || name === 'then') {
        name = `tool_${name}`;
    }
    return name;
}

function _exportedMethodName(raw) {
    const parts = String(raw || '').match(/[0-9A-Za-z]+/g) || [];
    if (parts.length === 0) {
        return 'Call';
    }
    let name = parts.map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`).join('');
    if (/^[0-9]/.test(name)) {
        name = `Call${name}`;
    }
    return name;
}

function _jsonString(value) {
    return JSON.stringify(String(value));
}

function _schemaType(prop) {
    if (!isPlainObject(prop)) {
        return 'string';
    }
    const t = prop.type;
    if (typeof t === 'string' && t.length > 0) {
        return t;
    }
    if (Array.isArray(t)) {
        const item = t.find((x) => typeof x === 'string' && x !== 'null');
        if (item) {
            return item;
        }
    }
    if (isPlainObject(prop.properties)) {
        return 'object';
    }
    if ('items' in prop) {
        return 'array';
    }
    return 'string';
}

function _schemaProperties(schema) {
    if (!isPlainObject(schema) || !isPlainObject(schema.properties)) {
        return {};
    }
    const out = {};
    for (const [name, prop] of Object.entries(schema.properties)) {
        if (isPlainObject(prop)) {
            out[name] = prop;
        }
    }
    return out;
}

function _argsSchemaFromParametersSchema(schema) {
    const properties = _schemaProperties(schema);
    const requiredRaw = isPlainObject(schema) && Array.isArray(schema.required) ? schema.required : [];
    const required = new Set(requiredRaw.filter((x) => typeof x === 'string'));
    const out = {};
    for (const [name, prop] of Object.entries(properties)) {
        const item = {
            type: _schemaType(prop),
            description: typeof prop.description === 'string' ? prop.description : '',
            required: required.has(name),
        };
        if ('default' in prop) {
            item.default = prop.default;
        }
        out[name] = item;
    }
    return out;
}

function _toolCallCode(language, toolId, parametersSchema) {
    const lang = normalizeFlowCodeLanguage(language);
    const method = _sdkMethodName(toolId);
    const exported = _exportedMethodName(method);
    const argNames = Object.keys(_schemaProperties(parametersSchema));
    if (lang === 'python') {
        const direct = argNames.length > 0
            && argNames.every((name) => /^[A-Za-z_][0-9A-Za-z_]*$/.test(name) && !PYTHON_KEYWORDS.has(name));
        if (direct) {
            const kwargs = argNames.map((name) => `        ${name}=args[${_jsonString(name)}]`).join(',\n');
            return `async def run(args, state):\n    result = await tools.${method}(\n${kwargs},\n    )\n    return {"result": result}\n`;
        }
        if (argNames.length > 0) {
            const entries = argNames.map((name) => `        ${_jsonString(name)}: args[${_jsonString(name)}],`).join('\n');
            return `async def run(args, state):\n    result = await tools.call(${_jsonString(toolId)}, **{\n${entries}\n    })\n    return {"result": result}\n`;
        }
        return `async def run(args, state):\n    result = await tools.${method}()\n    return {"result": result}\n`;
    }
    if (lang === 'javascript' || lang === 'typescript') {
        const payload = argNames.length > 0
            ? `{\n${argNames.map((name) => `    ${_jsonString(name)}: args[${_jsonString(name)}],`).join('\n')}\n  }`
            : '{}';
        return `async function run(args, state) {\n  const result = await tools.${method}(${payload});\n  return {result};\n}\n`;
    }
    if (lang === 'go') {
        const payload = argNames.length > 0
            ? `map[string]any{\n${argNames.map((name) => `        ${_jsonString(name)}: args[${_jsonString(name)}],`).join('\n')}\n    }`
            : 'map[string]any{}';
        return `package main\n\nfunc run(args map[string]any, state map[string]any) (any, error) {\n    result, err := tools.${exported}(${payload})\n    if err != nil {\n        return nil, err\n    }\n    return map[string]any{"result": result}, nil\n}\n`;
    }
    const payload = argNames.length > 0
        ? `new Dictionary<string, object?> {\n${argNames.map((name) => `        [${_jsonString(name)}] = args[${_jsonString(name)}],`).join('\n')}\n    }`
        : 'new Dictionary<string, object?>()';
    return `using System.Collections.Generic;\nusing System.Threading.Tasks;\n\nasync Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n{\n    var result = await tools.${exported}(${payload});\n    return new Dictionary<string, object?> { ["result"] = result };\n}\n`;
}

function _generatedToolConfig(t, language) {
    const parametersSchema = isPlainObject(t.parameters_schema) ? t.parameters_schema : {};
    const cfg = {
        tool_id: t.tool_id,
        code: _toolCallCode(language, t.tool_id, parametersSchema),
        language: normalizeFlowCodeLanguage(language),
    };
    const argsSchema = _argsSchemaFromParametersSchema(parametersSchema);
    if (Object.keys(argsSchema).length > 0) {
        cfg.args_schema = argsSchema;
    }
    if (Object.keys(parametersSchema).length > 0) {
        cfg.parameters_schema = parametersSchema;
    }
    return cfg;
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
        _toolCategoryTab: { state: true },
        _codeLanguage: { state: true },
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
            .code-language-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin: calc(var(--space-2) * -1) 0 var(--space-3);
            }
            .language-segment {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 2px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .language-button {
                width: 36px;
                height: 24px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 0;
                border-radius: calc(var(--radius-md) - 2px);
                background: transparent;
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: var(--font-semibold);
                line-height: 1;
                cursor: pointer;
            }
            .language-button:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            .language-button[active] {
                color: var(--accent);
                background: var(--accent-subtle);
            }
            .language-button:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }
            .language-button flows-code-language-icon {
                pointer-events: none;
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
                box-sizing: border-box;
            }
            .lib-card-icon[data-kind='flow'] {
                background: linear-gradient(135deg, #bb8fce 0%, #8e44ad 100%);
            }
            .lib-card-icon[data-kind='mcp'] {
                background: linear-gradient(135deg, #82e0aa 0%, #58d68d 100%);
            }
            .lib-card-icon[data-kind='code'] {
                background: var(--glass-solid);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
            }
            .lib-card-icon[data-kind='tool'] {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .lib-card-icon[data-kind='code'] flows-code-language-icon {
                width: 38px;
                height: 38px;
            }
            .lib-card-icon platform-icon {
                flex-shrink: 0;
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
        this._toolCategoryTab = 'all';
        this._codeLanguage = 'python';
        this._toolsAll = this.useOp('flows/tools_all');
        this._codeTemplates = this.useOp('flows/code_templates');
        this._codeParseSignature = this.useOp('flows/code_parse_signature');
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
            this._toolCategoryTab = 'all';
            this._codeLanguage = 'python';
            this.size = 'full';
            if (this._isCodeNodeTemplates()) {
                void this._loadCodeTemplates();
            }
            void this._toolsAll.run({ limit: 2000, offset: 0 });
        }
    }

    _loadCodeTemplates() {
        return this._codeTemplates.run({
            language: normalizeFlowCodeLanguage(this._codeLanguage),
            node_type: 'tool',
        });
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
        const list = this._toolsAllItems().filter((t) => {
            if (t.item_type === 'flow') {
                return false;
            }
            return true;
        });
        const tagF = this._activeTag;
        const q = _lower(this._search);
        const wantedLanguage = normalizeFlowCodeLanguage(this._codeLanguage);
        return list.filter((t) => {
            if (
                this._isCodeNodeTemplates()
                && _hasInlineCode(t)
                && normalizeFlowCodeLanguage(t.language) !== wantedLanguage
            ) {
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
        } else if (mode === 'mcp_only') {
            rows = rows.filter((t) => isMcpToolRegistryItem(t));
        } else {
            const tab = this._toolCategoryTab;
            if (tab === 'code') {
                rows = rows.filter(
                    (t) => t.item_type === 'tool' && !isMcpToolRegistryItem(t),
                );
            } else if (tab === 'flow') {
                rows = rows.filter((t) => t.item_type === 'flow');
            } else if (tab === 'mcp') {
                rows = rows.filter((t) => isMcpToolRegistryItem(t));
            }
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
        this._search = typeof e.detail?.value === 'string' ? e.detail.value : '';
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
        if (this._isCodeNodeTemplates()) {
            return 'code';
        }
        if (isMcpToolRegistryItem(item)) {
            return 'mcp';
        }
        if (_hasInlineCode(item)) {
            return 'code';
        }
        return 'tool';
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

    _showToolCategoryTabs() {
        const m = this.pickMode;
        return m !== 'flow_only' && m !== 'mcp_only';
    }

    _renderToolCategoryTabs() {
        if (!this._showToolCategoryTabs()) {
            return nothing;
        }
        const t = this._toolCategoryTab;
        return html`
            <div class="tabs" role="tablist" aria-label=${this.t('tool_picker_modal.tabs_aria')}>
                <button
                    type="button"
                    role="tab"
                    class="tab ${t === 'all' ? 'is-on' : ''}"
                    @click=${() => { this._toolCategoryTab = 'all'; }}
                >${this.t('tool_picker_modal.tab_all')}</button>
                <button
                    type="button"
                    role="tab"
                    class="tab ${t === 'code' ? 'is-on' : ''}"
                    @click=${() => { this._toolCategoryTab = 'code'; }}
                >${this.t('tool_picker_modal.tab_code')}</button>
                <button
                    type="button"
                    role="tab"
                    class="tab ${t === 'flow' ? 'is-on' : ''}"
                    @click=${() => { this._toolCategoryTab = 'flow'; }}
                >${this.t('tool_picker_modal.tab_flows')}</button>
                <button
                    type="button"
                    role="tab"
                    class="tab ${t === 'mcp' ? 'is-on' : ''}"
                    @click=${() => { this._toolCategoryTab = 'mcp'; }}
                >${this.t('tool_picker_modal.tab_mcp')}</button>
            </div>
        `;
    }

    _setCodeLanguage(language) {
        const normalized = normalizeFlowCodeLanguage(language);
        if (this._codeLanguage === normalized) {
            return;
        }
        this._codeLanguage = normalized;
        this._activeTag = '';
        void this._loadCodeTemplates();
    }

    _renderCodeLanguageSegment() {
        if (!this._isCodeNodeTemplates()) {
            return nothing;
        }
        const current = normalizeFlowCodeLanguage(this._codeLanguage);
        return html`
            <div class="code-language-row">
                <div class="language-segment" role="group" aria-label=${this.t('code_workbench.language_aria')}>
                    ${FLOW_CODE_LANGUAGES.map((lang) => html`
                        <button
                            type="button"
                            class="language-button"
                            ?active=${current === lang.value}
                            title=${lang.label}
                            aria-label=${lang.label}
                            @click=${() => this._setCodeLanguage(lang.value)}
                        >
                            <flows-code-language-icon language=${lang.value} size="18"></flows-code-language-icon>
                        </button>
                    `)}
                </div>
            </div>
        `;
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
                    <platform-field
                        type="string"
                        input-type="search"
                        mode="edit"
                        .value=${this._search}
                        .placeholder=${this.t('tool_picker_modal.search_placeholder')}
                        @change=${this._onSearchInput}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _renderRegistryCard(t, { onSelect }) {
        const icon = registryItemIconName(t);
        const kindAttr = this._iconKindAttr(t);
        const cardLanguage = _hasInlineCode(t) ? t.language : this._codeLanguage;
        const cardIcon = kindAttr === 'code'
            ? html`<flows-code-language-icon language=${cardLanguage} size="38"></flows-code-language-icon>`
            : html`<platform-icon name=${icon} size="26"></platform-icon>`;
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? t.description : '';
        const id = typeof t.tool_id === 'string' ? t.tool_id : '';
        return html`
            <button type="button" class="lib-card" @click=${onSelect}>
                <div class="lib-card-icon-row">
                    <div class="lib-card-icon" data-kind=${kindAttr}>
                        ${cardIcon}
                    </div>
                </div>
                <div class="lib-card-title">${title}</div>
                <div class="lib-card-desc">${this._mdDescription(desc)}</div>
                <div class="lib-card-meta">
                    ${id.length > 0 ? html`<span class="lib-chip">${id}</span>` : null}
                    ${kindAttr === 'code'
                        ? html`<span class="lib-chip">${flowCodeLanguageLabel(cardLanguage)}</span>`
                        : nothing}
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

    _templateArgsSchema(t, parsed) {
        if (isPlainObject(t.args_schema)) {
            return t.args_schema;
        }
        if (isPlainObject(parsed) && parsed.success === true && isPlainObject(parsed.args_schema)) {
            return parsed.args_schema;
        }
        return {};
    }

    async _commitTemplate(t) {
        if (!isPlainObject(t) || typeof t.code !== 'string' || t.code.length === 0) {
            return;
        }
        const fn = this.onCommit;
        const language = normalizeFlowCodeLanguage(t.language);
        const parsed = isPlainObject(t.args_schema) || language !== 'python'
            ? null
            : await this._codeParseSignature.run({
                code: t.code,
            });
        this.close();
        if (typeof fn === 'function') {
            const cfg = {
                code: t.code,
                language,
            };
            const argsSchema = this._templateArgsSchema(t, parsed);
            if (Object.keys(argsSchema).length > 0) {
                cfg.args_schema = argsSchema;
            }
            if (isPlainObject(t.parameters_schema)) {
                cfg.parameters_schema = t.parameters_schema;
            }
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
        const generated = _hasInlineCode(t) ? null : _generatedToolConfig(t, this._codeLanguage);
        const fn = this.onCommit;
        this.close();
        if (typeof fn === 'function') {
            const cfg = generated || {
                tool_id: t.tool_id,
                code: t.code,
                language: normalizeFlowCodeLanguage(t.language),
            };
            if (!generated) {
                if (t.args_schema && typeof t.args_schema === 'object') {
                    cfg.args_schema = t.args_schema;
                }
                if (t.parameters_schema && typeof t.parameters_schema === 'object') {
                    cfg.parameters_schema = t.parameters_schema;
                }
            }
            const nodeName = typeof t.title === 'string' && t.title.length > 0
                ? t.title
                : t.tool_id;
            queueMicrotask(() => {
                fn({ config: cfg, nodeName });
            });
        }
    }

    _renderBodyToolPick() {
        const busy = this._toolsAll.busy;
        const rows = this._pickModeRows();
        if (busy && this._toolsAllItems().length === 0) {
            return html`
                ${this._renderFilterBar()}
                ${this._renderToolCategoryTabs()}
                <glass-spinner></glass-spinner>
            `;
        }
        if (rows.length === 0) {
            return html`
                ${this._renderFilterBar()}
                ${this._renderToolCategoryTabs()}
                <div class="lib-empty">${this.t('tool_picker_modal.empty')}</div>
            `;
        }
        return html`
            ${this._renderFilterBar()}
            ${this._renderToolCategoryTabs()}
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
            ${this._renderCodeLanguageSegment()}
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
        return html`
            <div class="lib-grid">
                ${rows.map((t) => html`
                    <button type="button" class="lib-card" @click=${() => this._commitTemplate(t)}>
                        <div class="lib-card-icon-row">
                            <div class="lib-card-icon" data-kind="code">
                                <flows-code-language-icon language=${t.language} size="38"></flows-code-language-icon>
                            </div>
                        </div>
                        <div class="lib-card-title">${typeof t.name === 'string' ? t.name : t.id}</div>
                        <div class="lib-card-desc">${this._mdDescription(
                            typeof t.description === 'string' ? t.description : '',
                        )}</div>
                        <div class="lib-card-meta">
                            ${typeof t.language === 'string' && t.language.length > 0
                                ? html`<span class="lib-chip">${flowCodeLanguageLabel(t.language)}</span>`
                                : nothing}
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
        if (this.pickMode === 'mcp_only') {
            return this.t('tool_picker_modal.title_mcp');
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

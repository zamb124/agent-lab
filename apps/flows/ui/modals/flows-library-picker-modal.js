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
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '../components/common/flows-code-language-icon.js';
import { flowsChatMarkdownToHtml } from '@platform/lib/chat/markdown.js';
import { registryItemIconName, registryItemTitle } from '../_helpers/flows-registry-item-icon.js';
import { renderMcpServerIcon } from '../_helpers/mcp-server-icon.js';
import { asArray, isPlainObject } from '../_helpers/flows-resolvers.js';
import { isMcpToolRegistryItem, parseMcpToolIdToNodeConfig } from '../_helpers/flows-mcp-tool-registry.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
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

function _truncateText(text, maxLen = 180) {
    if (typeof text !== 'string' || text.length === 0) {
        return '';
    }
    if (text.length <= maxLen) {
        return text;
    }
    return `${text.slice(0, maxLen - 1)}…`;
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

function _parametersSchemaObject(schema) {
    if (isPlainObject(schema) && schema.type === 'object' && isPlainObject(schema.properties)) {
        return schema;
    }
    return { type: 'object', properties: {}, required: [] };
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
    const parametersSchema = _parametersSchemaObject(t.parameters_schema);
    const cfg = {
        tool_id: t.tool_id,
        code: _toolCallCode(language, t.tool_id, parametersSchema),
        language: normalizeFlowCodeLanguage(language),
        parameters_schema: parametersSchema,
    };
    return cfg;
}

export class FlowsLibraryPickerModal extends PlatformModal {
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        onPick: { type: Object, attribute: false },
        onPickBatch: { type: Object, attribute: false },
        onCommit: { type: Object, attribute: false },
        pickMode: { type: String, attribute: 'pick-mode' },
        _search: { state: true },
        _sourceTab: { state: true },
        _activeTag: { state: true },
        _toolCategoryTab: { state: true },
        _codeLanguage: { state: true },
        _testFeedback: { state: true },
        _testingServerId: { state: true },
        _syncingServerId: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        panelShellStyles,
        glassStyles,
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
            .search-wrap {
                flex: 0 1 240px;
                min-width: 160px;
            }
            .tool-picker-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                min-width: 0;
            }
            .tool-picker-toolbar .source-segment {
                margin-bottom: 0;
                min-width: 0;
            }
            .tool-picker-toolbar .search-wrap {
                flex: 0 0 auto;
                min-width: 0;
                margin-left: auto;
            }
            .code-language-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin: calc(var(--space-2) * -1) 0 var(--space-3);
            }
            .code-language-row platform-segmented-control {
                flex: 1 1 auto;
                min-width: 0;
            }
            .source-segment {
                margin-bottom: var(--space-3);
            }
            .lib-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
                min-height: 200px;
            }
            platform-picker-card {
                min-width: 0;
            }
            .lib-card-icon {
                width: 48px;
                height: 48px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--flows-avatar-text);
                flex-shrink: 0;
                box-sizing: border-box;
            }
            .lib-card-icon[data-kind='flow'] {
                background: var(--flows-lib-kind-flow-gradient);
            }
            .lib-card-icon[data-kind='mcp'] {
                background: var(--flows-lib-kind-mcp-gradient);
            }
            .lib-card-icon[data-kind='code'] {
                background: var(--glass-solid);
                border: 1px solid var(--border-subtle);
                box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-inverse) 6%, transparent);
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
                font-family: var(--font-mono);
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
            .lib-plain-desc {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
                text-align: left;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 4;
                overflow: hidden;
            }
            .lib-load-error {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-4);
                margin-top: var(--space-3);
            }
            .lib-load-error-detail {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                word-break: break-word;
            }
            @media (max-width: 640px) {
                .tool-picker-toolbar {
                    flex-wrap: wrap;
                    align-items: flex-start;
                }
                .tool-picker-toolbar .search-wrap {
                    flex: 1 1 160px;
                    max-width: 220px;
                }
            }
            .mcp-picker-servers {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-4);
                min-height: 200px;
                align-items: stretch;
            }
            @media (min-width: 960px) {
                .mcp-picker-servers {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (min-width: 1280px) {
                .mcp-picker-servers {
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                }
            }
            .mcp-picker-server {
                gap: 0;
                min-width: 0;
                height: var(--flows-tool-picker-mcp-panel-height);
            }
            .mcp-picker-server .content-panel-body {
                padding: var(--space-4, 1rem);
            }
            .mcp-picker-server-head {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .mcp-picker-server-head-main {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                min-width: 0;
                flex: 1;
            }
            .mcp-picker-server-icon {
                flex-shrink: 0;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
            }
            .mcp-picker-server-icon .mcp-server-icon-img {
                width: 30px;
                height: 30px;
                object-fit: contain;
            }
            .mcp-picker-server-titles h3 {
                margin: 0;
                font-size: var(--text-md);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .mcp-picker-server-titles .sub {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-top: 2px;
            }
            .mcp-picker-server-url {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                word-break: break-all;
                margin-top: var(--space-1);
            }
            .mcp-picker-server-meta {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .mcp-picker-server-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .mcp-picker-chip {
                display: inline-block;
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--info-bg);
                color: var(--info);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .mcp-picker-test-feedback {
                font-size: var(--text-sm);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            .mcp-picker-test-feedback.ok {
                background: var(--success-bg);
                color: var(--success);
            }
            .mcp-picker-test-feedback.err {
                background: var(--error-bg);
                color: var(--error);
            }
            .mcp-picker-tools-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(172px, 1fr));
                gap: var(--space-3);
                align-items: stretch;
            }
            .mcp-picker-tools-grid platform-picker-card {
                display: block;
                min-height: 140px;
                height: 100%;
            }
            .mcp-picker-tool-icon .mcp-server-icon-img {
                width: 18px;
                height: 18px;
                object-fit: contain;
            }
            .mcp-picker-tool-icon {
                width: 36px;
                height: 36px;
                border-radius: var(--radius-md);
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--flows-lib-kind-mcp-gradient);
                color: var(--flows-avatar-text);
            }
            .mcp-picker-tool-title {
                font-weight: var(--font-semibold);
                font-size: var(--text-xs);
                margin-bottom: 2px;
                color: var(--text-primary);
                line-height: 1.3;
            }
            .mcp-picker-tool-desc {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
                word-break: break-word;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 3;
                overflow: hidden;
            }
            .mcp-picker-server-empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                padding: var(--space-2) 0;
            }
            .mcp-picker-tool-server {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin-top: var(--space-1);
            }
            .mcp-picker-flat-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }
            .lib-empty-actions {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.onPick = null;
        this.onPickBatch = null;
        this.onCommit = null;
        this.pickMode = 'all';
        this._search = '';
        this._sourceTab = 'catalog';
        this._activeTag = '';
        this._toolCategoryTab = 'all';
        this._codeLanguage = 'python';
        this._testFeedback = null;
        this._testingServerId = null;
        this._syncingServerId = null;
        this._pickerItemsByCategory = new Map();
        this._pickerErrorByCategory = new Map();
        this._pickerLoadingCategory = null;
        this._toolsAll = this.useOp('flows/tools_all');
        this._codeTemplates = this.useOp('flows/code_templates');
        this._codeParseSignature = this.useOp('flows/code_parse_signature');
        this._mcpServers = this.useResource('flows/mcp_servers', { autoload: false });
        this._syncOp = this.useOp('flows/mcp_server_sync');
        this._testOp = this.useOp('flows/mcp_server_test');
    }

    _isCodeNodeTemplates() {
        return this._modalKind === 'flows.code_node_templates';
    }

    _resetPickerCache() {
        this._pickerItemsByCategory = new Map();
        this._pickerErrorByCategory = new Map();
        this._pickerLoadingCategory = null;
    }

    _currentPickerCategory() {
        if (this._isCodeNodeTemplates()) {
            return 'code';
        }
        if (this.pickMode === 'flow_only') {
            return 'flow';
        }
        if (this.pickMode === 'mcp_only') {
            return 'mcp';
        }
        return this._toolCategoryTab;
    }

    _isPickerCategoryLoading(category) {
        return this._pickerLoadingCategory === category
            || (this._toolsAll.busy && !this._pickerItemsByCategory.has(category));
    }

    _pickerLoadErrorMessage(category) {
        const message = this._pickerErrorByCategory.get(category);
        if (typeof message === 'string' && message.length > 0) {
            return message;
        }
        return null;
    }

    async _ensurePickerCategoryLoaded(category) {
        if (typeof category !== 'string' || category.length === 0) {
            throw new Error('flows-library-picker-modal: picker category required');
        }
        if (this._pickerItemsByCategory.has(category)) {
            return;
        }
        if (this._pickerLoadingCategory === category) {
            return;
        }
        this._pickerLoadingCategory = category;
        this._pickerErrorByCategory.delete(category);
        this.requestUpdate();
        const result = await this._toolsAll.run({
            limit: 2000,
            offset: 0,
            picker_category: category,
        });
        this._pickerLoadingCategory = null;
        if (result !== null && isPlainObject(result) && Array.isArray(result.items)) {
            this._pickerItemsByCategory.set(
                category,
                result.items.filter((x) => isPlainObject(x)),
            );
            this.requestUpdate();
            return;
        }
        const errorMessage = typeof this._toolsAll.error === 'string' && this._toolsAll.error.length > 0
            ? this._toolsAll.error
            : 'flows-library-picker-modal: tools_all failed';
        this._pickerErrorByCategory.set(category, errorMessage);
        this.requestUpdate();
    }

    _onToolCategoryTabChange(nextTab) {
        this._toolCategoryTab = nextTab;
        void this._ensurePickerCategoryLoaded(this._currentPickerCategory());
        if (this._usesMcpGroupedLayout()) {
            void this._mcpServers.load();
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._search = '';
            this._activeTag = '';
            this._sourceTab = 'catalog';
            this._toolCategoryTab = 'all';
            this._codeLanguage = 'python';
            this._testFeedback = null;
            this._testingServerId = null;
            this._syncingServerId = null;
            this._resetPickerCache();
            this.size = 'full';
            if (this._isCodeNodeTemplates()) {
                void this._loadCodeTemplates();
                void this._ensurePickerCategoryLoaded('code');
                return;
            }
            void this._ensurePickerCategoryLoaded(this._currentPickerCategory());
            if (this._usesMcpGroupedLayout()) {
                void this._mcpServers.load();
            }
        }
    }

    _usesMcpGroupedLayout() {
        return this.pickMode === 'mcp_only'
            || (this.pickMode === 'all' && this._toolCategoryTab === 'mcp');
    }

    _loadCodeTemplates() {
        return this._codeTemplates.run({
            language: normalizeFlowCodeLanguage(this._codeLanguage),
            node_type: 'tool',
        });
    }

    _toolsAllItems() {
        const category = this._currentPickerCategory();
        const cached = this._pickerItemsByCategory.get(category);
        if (Array.isArray(cached)) {
            return cached;
        }
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
        const q = _lower(this._search);
        if (q.length === 0) {
            return list;
        }
        return list.filter((t) => {
            const id = typeof t.tool_id === 'string' ? t.tool_id : '';
            const title = typeof t.title === 'string' ? t.title : '';
            const desc = typeof t.description === 'string' ? t.description : '';
            return _lower(id).indexOf(q) >= 0
                || _lower(title).indexOf(q) >= 0
                || _lower(desc).indexOf(q) >= 0;
        });
    }

    _mcpServerIdFromTool(item) {
        if (!isPlainObject(item)) {
            throw new Error('flows-library-picker-modal: MCP tool item required');
        }
        if (typeof item.mcp_server_id === 'string' && item.mcp_server_id.length > 0) {
            return item.mcp_server_id;
        }
        const toolId = typeof item.tool_id === 'string' ? item.tool_id : '';
        if (toolId.startsWith('mcp:')) {
            return parseMcpToolIdToNodeConfig(toolId).server_id;
        }
        throw new Error('flows-library-picker-modal: MCP tool item missing mcp_server_id');
    }

    _mcpToolsBase() {
        return this._toolsAllItems().filter((t) => isMcpToolRegistryItem(t));
    }

    _toolMatchesSearch(t, q) {
        if (q.length === 0) {
            return true;
        }
        const id = typeof t.tool_id === 'string' ? t.tool_id : '';
        const title = typeof t.title === 'string' ? t.title : '';
        const desc = typeof t.description === 'string' ? t.description : '';
        return _lower(id).indexOf(q) >= 0
            || _lower(title).indexOf(q) >= 0
            || _lower(desc).indexOf(q) >= 0;
    }

    _serverRecordMatchesSearch(server, q) {
        if (q.length === 0) {
            return true;
        }
        const serverId = typeof server.server_id === 'string' ? server.server_id : '';
        const name = typeof server.name === 'string' ? server.name : '';
        const url = typeof server.url === 'string' ? server.url : '';
        return _lower(serverId).indexOf(q) >= 0
            || _lower(name).indexOf(q) >= 0
            || _lower(url).indexOf(q) >= 0;
    }

    _buildMcpServerGroups() {
        const q = _lower(this._search);
        const allTools = this._mcpToolsBase();
        const toolsByServerId = new Map();
        for (const tool of allTools) {
            const serverId = this._mcpServerIdFromTool(tool);
            const bucket = toolsByServerId.get(serverId);
            if (bucket) {
                bucket.push(tool);
            } else {
                toolsByServerId.set(serverId, [tool]);
            }
        }

        const activeServers = asArray(this._mcpServers.items)
            .filter((s) => isPlainObject(s) && s.is_active === true)
            .sort((a, b) => {
                const an = typeof a.name === 'string' ? a.name : a.server_id;
                const bn = typeof b.name === 'string' ? b.name : b.server_id;
                return String(an).localeCompare(String(bn));
            });

        const knownServerIds = new Set();
        const groups = [];

        for (const server of activeServers) {
            if (typeof server.server_id !== 'string' || server.server_id.length === 0) {
                continue;
            }
            knownServerIds.add(server.server_id);
            const serverTools = toolsByServerId.get(server.server_id) || [];
            const filteredTools = q.length === 0
                ? serverTools
                : serverTools.filter((t) => this._toolMatchesSearch(t, q));
            const include = q.length === 0
                || this._serverRecordMatchesSearch(server, q)
                || filteredTools.length > 0;
            if (!include) {
                continue;
            }
            groups.push({
                server,
                tools: filteredTools,
            });
        }

        for (const [serverId, serverTools] of toolsByServerId.entries()) {
            if (knownServerIds.has(serverId)) {
                continue;
            }
            const filteredTools = q.length === 0
                ? serverTools
                : serverTools.filter((t) => this._toolMatchesSearch(t, q));
            const synthetic = {
                server_id: serverId,
                name: serverId,
                url: '',
                transport_type: 'http',
                source: 'manual',
            };
            const include = q.length === 0
                || this._serverRecordMatchesSearch(synthetic, q)
                || filteredTools.length > 0;
            if (!include) {
                continue;
            }
            groups.push({
                server: synthetic,
                tools: filteredTools,
            });
        }

        return groups;
    }

    _mcpSearchActive() {
        return _lower(this._search).length > 0;
    }

    /**
     * @returns {Array<{ tool: Record<string, unknown>, server: Record<string, unknown> }>}
     */
    _buildMcpFlatSearchTools() {
        const q = _lower(this._search);
        if (q.length === 0) {
            return [];
        }
        const flat = [];
        for (const tool of this._mcpToolsBase()) {
            if (!this._toolMatchesSearch(tool, q)) {
                continue;
            }
            const serverId = this._mcpServerIdFromTool(tool);
            const server = this._mcpServerById(serverId);
            if (server === null) {
                flat.push({
                    tool,
                    server: {
                        server_id: serverId,
                        name: serverId,
                        url: '',
                        transport_type: 'http',
                        source: 'manual',
                    },
                });
                continue;
            }
            flat.push({ tool, server });
        }
        flat.sort((left, right) => {
            const leftTitle = registryItemTitle(left.tool);
            const rightTitle = registryItemTitle(right.tool);
            const byTitle = leftTitle.localeCompare(rightTitle, undefined, { sensitivity: 'base' });
            if (byTitle !== 0) {
                return byTitle;
            }
            const leftServer = typeof left.server.name === 'string' ? left.server.name : '';
            const rightServer = typeof right.server.name === 'string' ? right.server.name : '';
            return leftServer.localeCompare(rightServer, undefined, { sensitivity: 'base' });
        });
        return flat;
    }

    _renderMcpFlatToolCard(entry) {
        const { tool, server } = entry;
        const title = registryItemTitle(tool);
        const desc = typeof tool.description === 'string' ? _truncateText(tool.description, 120) : '';
        const serverName = typeof server.name === 'string' && server.name.length > 0
            ? server.name
            : server.server_id;
        return html`
            <platform-picker-card
                value=${typeof tool.tool_id === 'string' ? tool.tool_id : title}
                title=${title}
                @select=${() => this._pickToolLike(tool)}
            >
                <div slot="icon">
                    <div class="mcp-picker-tool-icon">
                        ${renderMcpServerIcon(server, 18)}
                    </div>
                </div>
                <div class="mcp-picker-tool-server">
                    ${renderMcpServerIcon(server, 14)}
                    <span>${serverName}</span>
                </div>
                ${desc.length > 0 ? html`<div class="mcp-picker-tool-desc">${desc}</div>` : nothing}
            </platform-picker-card>
        `;
    }

    _renderMcpEmptyState() {
        return html`
            <div class="lib-empty-actions">
                <div>${this.t('tool_picker_modal.empty_mcp')}</div>
                <platform-button variant="primary" density="compact" @click=${() => this.openModal('flows.mcp_servers', {})}>
                    ${this.t('tool_picker_modal.action_manage_mcp')}
                </platform-button>
            </div>
        `;
    }

    _renderMcpFlatSearchBody(showTabs) {
        const flat = this._buildMcpFlatSearchTools();
        if (flat.length === 0) {
            return html`
                ${showTabs ? this._renderToolCategoryTabs() : nothing}
                <div class="lib-empty">${this.t('tool_picker_modal.mcp_empty_search')}</div>
            `;
        }
        return html`
            ${showTabs ? this._renderToolCategoryTabs() : nothing}
            <div class="mcp-picker-flat-hint">${this.t('tool_picker_modal.mcp_flat_search_hint')}</div>
            <div class="mcp-picker-tools-grid" role="list">
                ${flat.map((entry) => this._renderMcpFlatToolCard(entry))}
            </div>
        `;
    }

    _mcpServerById(serverId) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            return null;
        }
        for (const server of asArray(this._mcpServers.items)) {
            if (isPlainObject(server) && server.server_id === serverId) {
                return server;
            }
        }
        return null;
    }

    _mcpTransportLabel(value) {
        if (value === 'http') {
            return this.t('mcp_servers_modal.transport_http');
        }
        if (value === 'sse') {
            return this.t('mcp_servers_modal.transport_sse');
        }
        return this.t('mcp_servers_modal.transport_unknown');
    }

    _mcpSourceLabel(source) {
        if (source === 'platform') {
            return this.t('mcp_servers_modal.source_platform');
        }
        if (source === 'catalog') {
            return this.t('mcp_servers_modal.source_catalog');
        }
        if (source === 'manual') {
            return this.t('mcp_servers_modal.source_manual');
        }
        return this.t('mcp_servers_modal.source_unknown');
    }

    _mcpGroupedInitialBusy() {
        const category = this._currentPickerCategory();
        const toolsEmpty = !this._pickerItemsByCategory.has(category);
        const serversEmpty = asArray(this._mcpServers.items).length === 0;
        return (this._isPickerCategoryLoading(category) && toolsEmpty)
            || (this._mcpServers.loading && serversEmpty);
    }

    async _syncMcpServer(serverId) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            throw new Error('flows-library-picker-modal: serverId required for sync');
        }
        this._syncingServerId = serverId;
        try {
            await this._syncOp.run({ server_id: serverId });
            this._pickerItemsByCategory.delete('mcp');
            await this._ensurePickerCategoryLoaded('mcp');
        } finally {
            this._syncingServerId = null;
        }
    }

    async _runMcpTest(serverId) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            throw new Error('flows-library-picker-modal: serverId required for test');
        }
        this._testingServerId = serverId;
        this._testFeedback = null;
        try {
            const result = await this._testOp.run({ server_id: serverId });
            if (result !== null) {
                if (!isPlainObject(result) || typeof result.tools_count !== 'number') {
                    throw new TypeError('flows-library-picker-modal: MCP test result must include tools_count');
                }
                this._testFeedback = {
                    serverId,
                    ok: true,
                    toolsCount: result.tools_count,
                };
                return;
            }
            if (typeof this._testOp.error !== 'string') {
                throw new Error('flows-library-picker-modal: MCP test failed without error message');
            }
            this._testFeedback = {
                serverId,
                ok: false,
                message: this._testOp.error,
            };
        } finally {
            this._testingServerId = null;
        }
    }

    _renderPickerLoadError(category) {
        const errorMessage = this._pickerLoadErrorMessage(category);
        if (errorMessage === null) {
            return nothing;
        }
        return html`
            <div class="lib-load-error content-panel" role="alert">
                <p>${this.t('tool_picker_modal.load_error')}</p>
                <p class="lib-load-error-detail">${errorMessage}</p>
                <platform-button
                    variant="secondary"
                    @click=${() => {
                        this._pickerItemsByCategory.delete(category);
                        this._pickerErrorByCategory.delete(category);
                        void this._ensurePickerCategoryLoaded(category);
                    }}
                >
                    ${this.t('tool_picker_modal.action_retry')}
                </platform-button>
            </div>
        `;
    }

    _renderMcpTestFeedback(serverId) {
        const fb = this._testFeedback;
        if (!fb || fb.serverId !== serverId) {
            return html``;
        }
        if (fb.ok === true) {
            return html`
                <div class="mcp-picker-test-feedback ok" role="status">
                    ${this.t('mcp_servers_modal.test_result_ok', { n: fb.toolsCount })}
                </div>
            `;
        }
        return html`
            <div class="mcp-picker-test-feedback err" role="alert">
                ${this.t('mcp_servers_modal.test_result_error', { message: fb.message })}
            </div>
        `;
    }

    _renderMcpToolCard(t) {
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? _truncateText(t.description, 120) : '';
        const icon = registryItemIconName(t);
        const mcpServerId = typeof t.mcp_server_id === 'string' ? t.mcp_server_id : '';
        const server = this._mcpServerById(mcpServerId);
        const iconNode = server
            ? renderMcpServerIcon(server, 18)
            : html`<platform-icon name=${icon} size="18"></platform-icon>`;
        return html`
            <platform-picker-card
                value=${typeof t.tool_id === 'string' ? t.tool_id : title}
                title=${title}
                @select=${() => this._pickToolLike(t)}
            >
                <div slot="icon">
                    <div class="mcp-picker-tool-icon">
                        ${iconNode}
                    </div>
                </div>
                ${desc.length > 0 ? html`<div class="mcp-picker-tool-desc">${desc}</div>` : nothing}
            </platform-picker-card>
        `;
    }

    _renderMcpServerSection(group) {
        const server = group.server;
        const serverId = server.server_id;
        const tools = group.tools;
        const transport = typeof server.transport_type === 'string' ? server.transport_type : 'http';
        const source = typeof server.source === 'string' ? server.source : 'manual';
        const isSyncing = this._syncingServerId === serverId;
        const isTesting = this._testingServerId === serverId;
        return html`
            <section class="mcp-picker-server content-panel" aria-labelledby="mcp-server-${serverId}" data-server-id=${serverId}>
                <div class="content-panel-head mcp-picker-server-head">
                    <div class="mcp-picker-server-head-main">
                        <div class="mcp-picker-server-icon glass-subtle">${renderMcpServerIcon(server, 30)}</div>
                        <div class="mcp-picker-server-titles">
                            <h3 id="mcp-server-${serverId}">${server.name}</h3>
                            <div class="sub"><code>${serverId}</code></div>
                            ${typeof server.url === 'string' && server.url.length > 0
                                ? html`<div class="mcp-picker-server-url">${server.url}</div>`
                                : nothing}
                            <div class="mcp-picker-server-meta">
                                <span class="mcp-picker-chip">${this._mcpTransportLabel(transport)}</span>
                                <span class="mcp-picker-chip">${this._mcpSourceLabel(source)}</span>
                                <span>${this.t('tool_picker_modal.mcp_server_tools_count', { n: tools.length })}</span>
                            </div>
                        </div>
                    </div>
                    <div class="mcp-picker-server-actions">
                        ${this._mcpBulkAddEnabled() && tools.length > 0
                            ? html`
                                <platform-button
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    title=${this.t('tool_picker_modal.mcp_add_all_aria')}
                                    aria-label=${this.t('tool_picker_modal.mcp_add_all_aria')}
                                    @click=${(e) => {
                                        e.stopPropagation();
                                        this._pickAllMcpToolsFromServer(tools);
                                    }}
                                >
                                    <platform-icon name="list-checks" size="16"></platform-icon>
                                </platform-button>
                            `
                            : nothing}
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${isSyncing}
                            title=${this.t('mcp_servers_modal.action_sync_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_sync_aria')}
                            @click=${(e) => {
                                e.stopPropagation();
                                void this._syncMcpServer(serverId);
                            }}
                        >
                            ${isSyncing
                                ? html`<glass-spinner size="sm"></glass-spinner>`
                                : html`<platform-icon name="rotate-ccw" size="16"></platform-icon>`}
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${isTesting}
                            title=${this.t('mcp_servers_modal.action_test_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_test_aria')}
                            @click=${(e) => {
                                e.stopPropagation();
                                void this._runMcpTest(serverId);
                            }}
                        >
                            ${isTesting
                                ? html`<glass-spinner size="sm"></glass-spinner>`
                                : html`<platform-icon name="check" size="16"></platform-icon>`}
                        </platform-button>
                    </div>
                </div>
                <div class="content-panel-body">
                    ${this._renderMcpTestFeedback(serverId)}
                    ${tools.length === 0
                        ? html`<div class="mcp-picker-server-empty">${this.t('tool_picker_modal.mcp_server_empty')}</div>`
                        : html`
                            <div class="mcp-picker-tools-grid" role="list">
                                ${tools.map((t) => this._renderMcpToolCard(t))}
                            </div>
                        `}
                </div>
            </section>
        `;
    }

    _renderMcpGroupedBody() {
        const showTabs = this._showToolCategoryTabs();
        const category = this._currentPickerCategory();
        const loadError = this._renderPickerLoadError(category);
        if (loadError !== nothing) {
            return html`
                ${showTabs ? this._renderToolCategoryTabs() : nothing}
                ${loadError}
            `;
        }
        if (this._mcpGroupedInitialBusy()) {
            return html`
                ${showTabs ? this._renderToolCategoryTabs() : nothing}
                <glass-spinner></glass-spinner>
            `;
        }
        if (this._mcpSearchActive()) {
            return this._renderMcpFlatSearchBody(showTabs);
        }
        const groups = this._buildMcpServerGroups();
        if (groups.length === 0) {
            const hasMcpTools = this._mcpToolsBase().length > 0;
            const hasServers = asArray(this._mcpServers.items).length > 0;
            const emptyContent = (!hasMcpTools && !hasServers)
                ? this._renderMcpEmptyState()
                : html`<div class="lib-empty">${this.t('tool_picker_modal.empty')}</div>`;
            return html`
                ${showTabs ? this._renderToolCategoryTabs() : nothing}
                ${emptyContent}
            `;
        }
        return html`
            ${showTabs ? this._renderToolCategoryTabs() : nothing}
            <div class="mcp-picker-servers">
                ${groups.map((group) => this._renderMcpServerSection(group))}
            </div>
        `;
    }

    _renderHeaderSearch() {
        return html`
            <platform-modal-search-field
                layout="header"
                .value=${this._search}
                placeholder=${this.t('tool_picker_modal.search_placeholder')}
                @change=${this._onSearchInput}
            ></platform-modal-search-field>
        `;
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
     * уезжают в `&quot;` из-за `escapeHtml` в `flowsChatMarkdownToHtml`. Fallback — общий flows-chat helper.
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
        const htmlStr = flowsChatMarkdownToHtml(text);
        if (htmlStr.length === 0) {
            return nothing;
        }
        return html`<div class="lib-md">${unsafeHTML(htmlStr)}</div>`;
    }

    _showToolCategoryTabs() {
        const m = this.pickMode;
        return m !== 'flow_only' && m !== 'mcp_only';
    }

    _toolCategoryTabItems() {
        return [
            { value: 'all', label: this.t('tool_picker_modal.tab_all') },
            { value: 'code', label: this.t('tool_picker_modal.tab_code') },
            { value: 'flow', label: this.t('tool_picker_modal.tab_flows') },
            { value: 'mcp', label: this.t('tool_picker_modal.tab_mcp') },
        ];
    }

    _renderToolCategoryTabs() {
        if (!this._showToolCategoryTabs()) {
            return nothing;
        }
        return html`
            <platform-segmented-control
                class="source-segment"
                density="compact"
                .value=${this._toolCategoryTab}
                .items=${this._toolCategoryTabItems()}
                aria-label=${this.t('tool_picker_modal.tabs_aria')}
                @change=${(e) => { this._onToolCategoryTabChange(e.detail.value); }}
            ></platform-segmented-control>
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
                <platform-segmented-control
                    icon-only
                    density="compact"
                    .value=${current}
                    .items=${FLOW_CODE_LANGUAGES.map((lang) => ({
                        value: lang.value,
                        icon: lang.icon,
                        title: lang.label,
                    }))}
                    aria-label=${this.t('code_workbench.language_aria')}
                    @change=${(e) => this._setCodeLanguage(e.detail.value)}
                ></platform-segmented-control>
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
                            <platform-button
                                variant=${this._activeTag === tag ? 'secondary' : 'ghost'}
                                density="dense"
                                @click=${() => this._setTag(tag)}
                            >#${tag}</platform-button>
                        `,
                    )}
                </div>
            `
            : html`<div class="tag-strip tag-strip--filler" role="presentation" aria-hidden="true"></div>`;
        return html`
            <div class="bar">
                ${tagRow}
                <div class="search-wrap">
                    <platform-modal-search-field
                        layout="toolbar"
                        .value=${this._search}
                        placeholder=${this.t('tool_picker_modal.search_placeholder')}
                        @change=${this._onSearchInput}
                    ></platform-modal-search-field>
                </div>
            </div>
        `;
    }

    _renderSearchField(searchWrapClass = '') {
        return html`
            <div class="search-wrap ${searchWrapClass}">
                <platform-modal-search-field
                    layout="toolbar"
                    .value=${this._search}
                    placeholder=${this.t('tool_picker_modal.search_placeholder')}
                    @change=${this._onSearchInput}
                ></platform-modal-search-field>
            </div>
        `;
    }

    _renderToolPickerToolbar() {
        if (this._usesMcpGroupedLayout()) {
            if (!this._showToolCategoryTabs()) {
                return nothing;
            }
            return html`
                <div class="tool-picker-toolbar">
                    ${this._renderToolCategoryTabs()}
                </div>
            `;
        }
        return html`
            <div class="tool-picker-toolbar">
                ${this._renderToolCategoryTabs()}
                ${this._renderSearchField('search-wrap--tool')}
            </div>
        `;
    }

    _renderRegistryCard(t, { onSelect, plainDescription = false }) {
        const icon = registryItemIconName(t);
        const kindAttr = this._iconKindAttr(t);
        const cardLanguage = _hasInlineCode(t) ? t.language : this._codeLanguage;
        const cardIcon = kindAttr === 'code'
            ? html`<flows-code-language-icon language=${cardLanguage} size="38"></flows-code-language-icon>`
            : html`<platform-icon name=${icon} size="26"></platform-icon>`;
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? t.description : '';
        const id = typeof t.tool_id === 'string' ? t.tool_id : '';
        const descriptionNode = plainDescription
            ? (desc.length > 0 ? html`<div class="lib-plain-desc">${_truncateText(desc)}</div>` : nothing)
            : html`<div class="lib-md">${this._mdDescription(desc)}</div>`;
        return html`
            <platform-picker-card
                value=${id.length > 0 ? id : title}
                title=${title}
                @select=${onSelect}
            >
                <div slot="icon">
                    <div class="lib-card-icon" data-kind=${kindAttr}>
                        ${cardIcon}
                    </div>
                </div>
                ${descriptionNode}
                <div class="lib-card-meta">
                    ${id.length > 0 ? html`<span class="lib-chip">${id}</span>` : null}
                    ${kindAttr === 'code'
                        ? html`<span class="lib-chip">${flowCodeLanguageLabel(cardLanguage)}</span>`
                        : nothing}
                    ${_tagsFromItem(t).map((g) => html`<span class="lib-chip">${g}</span>`)}
                </div>
            </platform-picker-card>
        `;
    }

    _mcpBulkAddEnabled() {
        return typeof this.onPickBatch === 'function';
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

    _pickAllMcpToolsFromServer(tools) {
        const fn = this.onPickBatch;
        if (typeof fn !== 'function') {
            return;
        }
        if (!Array.isArray(tools) || tools.length === 0) {
            return;
        }
        const items = tools.filter(
            (t) => isPlainObject(t) && typeof t.tool_id === 'string' && t.tool_id.length > 0,
        );
        if (items.length === 0) {
            return;
        }
        this.close();
        queueMicrotask(() => {
            fn({
                kind: 'tool',
                items,
            });
        });
    }

    _templateParametersSchema(t, parsed) {
        if (isPlainObject(t.parameters_schema)) {
            return _parametersSchemaObject(t.parameters_schema);
        }
        if (isPlainObject(parsed) && parsed.success === true && isPlainObject(parsed.parameters_schema)) {
            return _parametersSchemaObject(parsed.parameters_schema);
        }
        return { type: 'object', properties: {}, required: [] };
    }

    async _commitTemplate(t) {
        if (!isPlainObject(t) || typeof t.code !== 'string' || t.code.length === 0) {
            return;
        }
        const fn = this.onCommit;
        const language = normalizeFlowCodeLanguage(t.language);
        const parsed = isPlainObject(t.parameters_schema) || language !== 'python'
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
            cfg.parameters_schema = this._templateParametersSchema(t, parsed);
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
                parameters_schema: _parametersSchemaObject(t.parameters_schema),
            };
            const nodeName = typeof t.title === 'string' && t.title.length > 0
                ? t.title
                : t.tool_id;
            queueMicrotask(() => {
                fn({ config: cfg, nodeName });
            });
        }
    }

    _renderBodyToolPick() {
        if (this._usesMcpGroupedLayout()) {
            return this._renderMcpGroupedBody();
        }
        const category = this._currentPickerCategory();
        const loadError = this._renderPickerLoadError(category);
        if (loadError !== nothing) {
            return html`
                ${this._renderToolPickerToolbar()}
                ${loadError}
            `;
        }
        const loading = this._isPickerCategoryLoading(category) && !this._pickerItemsByCategory.has(category);
        const rows = this._pickModeRows();
        if (loading) {
            return html`
                ${this._renderToolPickerToolbar()}
                <glass-spinner></glass-spinner>
            `;
        }
        if (rows.length === 0) {
            return html`
                ${this._renderToolPickerToolbar()}
                <div class="lib-empty">${this.t('tool_picker_modal.empty')}</div>
            `;
        }
        return html`
            ${this._renderToolPickerToolbar()}
            <div class="lib-grid" role="list">
                ${rows.map((t) => this._renderRegistryCard(t, {
                    onSelect: () => this._pickToolLike(t),
                    plainDescription: true,
                }))}
            </div>
        `;
    }

    _renderBodyCodeNode() {
        const rowCatalog = this._filterCatalogRows();
        const rowTools = this._toolRegistryRows();
        return html`
            ${this._renderFilterBar()}
            ${this._renderCodeLanguageSegment()}
            <platform-segmented-control
                class="source-segment"
                density="compact"
                .value=${this._sourceTab}
                .items=${[
                    { value: 'catalog', label: this.t('code_node_templates_modal.tab_catalog') },
                    { value: 'registry', label: this.t('code_node_templates_modal.tab_registry') },
                ]}
                aria-label=${this.t('code_node_templates_modal.source_tabs_aria')}
                @change=${(e) => { this._sourceTab = e.detail.value; }}
            ></platform-segmented-control>
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
                    <platform-picker-card
                        value=${typeof t.id === 'string' ? t.id : (typeof t.name === 'string' ? t.name : 'template')}
                        title=${typeof t.name === 'string' ? t.name : t.id}
                        @select=${() => this._commitTemplate(t)}
                    >
                        <div slot="icon">
                            <div class="lib-card-icon" data-kind="code">
                                <flows-code-language-icon language=${t.language} size="38"></flows-code-language-icon>
                            </div>
                        </div>
                        <div class="lib-md">${this._mdDescription(
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
                    </platform-picker-card>
                `)}
            </div>
        `;
    }

    _renderCodeRegistryBlock(rows) {
        const category = this._currentPickerCategory();
        const loadError = this._renderPickerLoadError(category);
        if (loadError !== nothing) {
            return loadError;
        }
        if (this._isPickerCategoryLoading(category) && !this._pickerItemsByCategory.has(category)) {
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

    renderHeaderActions() {
        if (this._isCodeNodeTemplates() || !this._usesMcpGroupedLayout()) {
            return html``;
        }
        return this._renderHeaderSearch();
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

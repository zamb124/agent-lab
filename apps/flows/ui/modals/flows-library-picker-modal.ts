/**
 * Единая модалка библиотеки: tool/flow/MCP (LLM, canvas drop) и шаблоны code-ноды.
 * Один body: tag-groups (`_renderBodyToolPick`) или MCP grouped layout.
 *
 * kinds: `flows.tool_picker` | `flows.code_node_templates` (alias → pickMode code_node).
 * `pickMode`: `all` | `flow_only` | `mcp_only` | `code_node`.
 * При `all` — вкладки Все / Code / Flows / MCP (`flows/tools_all`).
 * При `code_node` — каталог `flows/code_templates` + registry code tools, commit через `onCommit`.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '../components/common/flows-code-language-segment.js';
import '../components/common/flows-code-language-icon.js';
import {
    registryItemLanguage,
    registryItemTitle,
    registryItemVisualKind,
    renderRegistryItemCardIcon,
    tagGroupIconName,
} from '../_helpers/flows-registry-item-icon.js';
import { renderMcpServerIcon } from '../_helpers/mcp-server-icon.js';
import { asArray, isPlainObject } from '../_helpers/flows-resolvers.js';
import { isMcpToolRegistryItem, parseMcpToolIdToNodeConfig } from '../_helpers/flows-mcp-tool-registry.js';
import { buildToolTagGroups } from '../_helpers/flows-tool-tag-groups.js';
import { fetchToolsAllPage, TAG_GROUPS_PAGE_LIMIT, TOOLS_ALL_PAGE_LIMIT } from '../_helpers/flows-tools-all-pages.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { hueFromString } from '@platform/lib/utils/hash-string.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import {
    flowCodeLanguageShortLabel,
    normalizeFlowCodeLanguage,
} from '../_helpers/flows-code-languages.js';

const SEARCH_DEBOUNCE_MS = 280;

function _templatesFromResult(result: any) {
    if (result && typeof result === 'object' && Array.isArray(result.templates)) {
        return result.templates;
    }
    return [];
}

function _lower(s: any) {
    if (typeof s === 'string' && s.length > 0) {
        return s.toLowerCase();
    }
    return '';
}

function _tagsFromItem(t: any) {
    if (t && Array.isArray(t.tags)) {
        return t.tags.filter((x: any) => typeof x === 'string' && x.length > 0);
    }
    return [];
}

function _hasInlineCode(t: any) {
    return t && typeof t.code === 'string' && t.code.trim().length > 0;
}

function _truncateText(text: any, maxLen = 180) {
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

function presentText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function _sdkMethodName(raw: any) {
    let name = presentText(raw)
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

function _exportedMethodName(raw: any) {
    const matched = presentText(raw).match(/[0-9A-Za-z]+/g);
    const parts = matched === null ? [] : matched;
    if (parts.length === 0) {
        return 'Call';
    }
    let name = parts.map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`).join('');
    if (/^[0-9]/.test(name)) {
        name = `Call${name}`;
    }
    return name;
}

function _jsonString(value: unknown) {
    return JSON.stringify(String(value));
}

function _schemaProperties(schema: any) {
    if (!isPlainObject(schema) || !isPlainObject(schema.properties)) {
        return {};
    }
    const out = {};
    for (const [name, prop] of Object.entries(schema.properties)) {
        if (isPlainObject(prop)) {
            (out as any)[name] = prop;
        }
    }
    return out;
}

function _parametersSchemaObject(schema: any) {
    if (isPlainObject(schema) && schema.type === 'object' && isPlainObject(schema.properties)) {
        return schema;
    }
    return { type: 'object', properties: {}, required: [] };
}

function _toolCallCode(language: string, toolId: string, parametersSchema: any) {
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

function _generatedToolConfig(t: any, language: string) {
    const parametersSchema = _parametersSchemaObject(t.parameters_schema);
    const cfg: any = {
        tool_id: t.tool_id,
        code: _toolCallCode(language, t.tool_id, parametersSchema),
        language: normalizeFlowCodeLanguage(language),
        parameters_schema: parametersSchema,
    };
    return cfg;
}

export class FlowsLibraryPickerModal extends PlatformModal {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        onPick: { type: Object, attribute: false },
        onPickBatch: { type: Object, attribute: false },
        onCommit: { type: Object, attribute: false },
        pickMode: { type: String, attribute: 'pick-mode' },
        _search: { state: true },
        _toolCategoryTab: { state: true },
        _codeLanguage: { state: true },
        _testFeedback: { state: true },
        _testingServerId: { state: true },
        _syncingServerId: { state: true },
        _selectedToolIds: { state: true },
        _tagGroupDescriptions: { state: true },
        _collapsedTags: { state: true },
        _pickerLoadingMore: { state: true },
    }
    declare onPick: ((payload: any) => void) | null;
    declare onPickBatch: ((payload: any) => void) | null;
    declare onCommit: ((payload: any) => void) | null;
    declare pickMode: string;
    declare _search: string;
    declare _toolCategoryTab: string;
    declare _codeLanguage: string;
    declare _testFeedback: Record<string, any> | null;
    declare _testingServerId: any;
    declare _syncingServerId: any;
    declare _selectedToolIds: any[];
    declare _tagGroupDescriptions: Record<string, any>;
    declare _collapsedTags: Record<string, any>;
    declare _pickerLoadingMore: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
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
            .code-language-row platform-segmented-control,
            .code-language-row flows-code-language-segment {
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
            .tag-group-tools .lib-card-icon {
                width: 40px;
                height: 40px;
            }
            .tag-group-tools .lib-card-icon[data-kind='code'] flows-code-language-icon {
                width: 30px;
                height: 30px;
            }
            .mcp-picker-tools-grid .lib-card-icon {
                width: 36px;
                height: 36px;
            }
            .mcp-picker-tools-grid .lib-card-icon .mcp-server-icon-img {
                width: 18px;
                height: 18px;
                object-fit: contain;
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
            .tag-groups {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .picker-scroll-sentinel {
                height: 1px;
                width: 100%;
                pointer-events: none;
            }
            .tag-group {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid);
                overflow: hidden;
                box-shadow: var(--shadow-sm);
            }
            .tag-group-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--tag-group-accent, var(--accent)) 8%, var(--glass-solid));
            }
            .tag-group-head-main {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                min-width: 0;
                flex: 1 1 auto;
            }
            .tag-group-icon {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                color: var(--text-inverse);
                background: hsl(var(--tag-group-hue, 210) 42% 42%);
            }
            .tag-group-titles {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .tag-group-titles h3 {
                margin: 0;
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.25;
            }
            .tag-group-blurb {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
            }
            .tag-group-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .tag-group-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .tag-group-tools {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
                padding: var(--space-3);
                align-items: stretch;
            }
            .tag-group-tools platform-picker-card {
                display: block;
                min-height: 148px;
                height: 100%;
                min-width: 0;
            }
            .tag-tool-card-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
                flex: 1 1 auto;
            }
            .tag-tool-desc {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 3;
                overflow: hidden;
                word-break: break-word;
            }
            .tag-tool-meta {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
                margin-top: auto;
            }
            .tag-tool-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                font-size: 10px;
                font-weight: var(--font-medium);
                letter-spacing: 0.02em;
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-tint-medium);
                color: var(--text-tertiary);
                max-width: 100%;
                word-break: break-all;
            }
            .tag-tool-chip[data-kind='code'] {
                color: var(--text-secondary);
            }
            .tag-tool-chip[data-kind='flow'] {
                background: color-mix(in srgb, var(--accent-secondary) 22%, var(--glass-tint-medium));
                color: var(--text-secondary);
            }
            .tag-tool-chip[data-kind='mcp'] {
                background: color-mix(in srgb, var(--success) 18%, var(--glass-tint-medium));
                color: var(--text-secondary);
            }
            .tag-tool-chip[data-kind='tool'] {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .tag-tool-chip[data-kind='effect'] {
                background: color-mix(in srgb, var(--accent) 14%, var(--glass-tint-medium));
                color: var(--text-secondary);
            }
            .tag-tool-chip[data-kind='floor'] {
                background: color-mix(in srgb, var(--warning) 18%, var(--glass-tint-medium));
                color: var(--text-secondary);
            }
            .tag-tool-id {
                font-size: 10px;
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                line-height: 1.3;
                word-break: break-all;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 1;
                overflow: hidden;
            }
            .tag-tool-add-one {
                margin-left: auto;
                opacity: 0.55;
            }
            .tag-group-tools platform-picker-card:hover .tag-tool-add-one,
            .tag-group-tools platform-picker-card:focus-within .tag-tool-add-one {
                opacity: 1;
            }
            @media (max-width: 640px) {
                .tag-group-tools {
                    grid-template-columns: 1fr;
                }
                .tag-tool-add-one {
                    opacity: 0.85;
                }
            }
            .picker-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
            }
            .picker-footer-count {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .picker-footer-actions {
                display: flex;
                gap: var(--space-2);
            }
        `,
    ];
    private _toolsAll: OpController;
    private _toolTagGroups: OpController;
    private _codeTemplates: OpController;
    private _codeParseSignature: OpController;
    private _mcpServers: ResourceController;
    private _syncOp: OpController;
    private _testOp: OpController;
    private _localeSelect: SelectController<any>;
    private _pickerItemsByCategory: Map<any, any>;
    private _pickerNextOffsetByCategory: Map<any, any>;
    private _pickerHasMoreByCategory: Map<any, any>;
    private _pickerErrorByCategory: Map<any, any>;
    private _pickerLoadingCategory: any;
    private _pickerActiveQuery: string;
    private _pickerLoadGeneration: number;
    private _searchDebounceTimer: any;
    private _scrollObserver: any;
    private _observedSentinel: any;

    constructor() {
        super();
        this.onPick = null;
        this.onPickBatch = null;
        this.onCommit = null;
        this.pickMode = 'all';
        this._search = '';
        this._toolCategoryTab = 'all';
        this._codeLanguage = 'python';
        this._testFeedback = null;
        this._testingServerId = null;
        this._syncingServerId = null;
        this._selectedToolIds = [];
        this._tagGroupDescriptions = {};
        this._collapsedTags = {};
        this._pickerItemsByCategory = new Map();
        this._pickerNextOffsetByCategory = new Map();
        this._pickerHasMoreByCategory = new Map();
        this._pickerErrorByCategory = new Map();
        this._pickerLoadingCategory = null;
        this._pickerLoadingMore = false;
        this._pickerActiveQuery = '';
        /** @type {number} инвалидирует in-flight tools/all при смене q / повторном load */
        this._pickerLoadGeneration = 0;
        this._searchDebounceTimer = null;
        this._scrollObserver = null;
        this._observedSentinel = null;
        this._toolsAll = this.useOp('flows/tools_all');
        this._toolTagGroups = this.useOp('flows/tool_tag_groups');
        this._codeTemplates = this.useOp('flows/code_templates');
        this._codeParseSignature = this.useOp('flows/code_parse_signature');
        this._mcpServers = this.useResource('flows/mcp_servers', { autoload: false });
        this._syncOp = this.useOp('flows/mcp_server_sync');
        this._testOp = this.useOp('flows/mcp_server_test');
        this._localeSelect = this.select((s) => (s as any).i18n.locale);
    }

    _isCodeNodeTemplates() {
        return this.pickMode === 'code_node'
            || this._modalKind === 'flows.code_node_templates';
    }

    _resetPickerCache() {
        this._pickerItemsByCategory = new Map();
        this._pickerNextOffsetByCategory = new Map();
        this._pickerHasMoreByCategory = new Map();
        this._pickerErrorByCategory = new Map();
        this._pickerLoadingCategory = null;
        this._pickerLoadingMore = false;
        this._pickerActiveQuery = '';
        this._pickerLoadGeneration += 1;
    }

    _teardownScrollObserver() {
        if (this._scrollObserver !== null) {
            this._scrollObserver.disconnect();
        }
        this._scrollObserver = null;
        this._observedSentinel = null;
    }

    override disconnectedCallback(): void {
        if (this._searchDebounceTimer !== null) {
            clearTimeout(this._searchDebounceTimer);
            this._searchDebounceTimer = null;
        }
        this._teardownScrollObserver();
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        this._syncScrollObserver();
    }

    _syncScrollObserver() {
        if (!this.open) {
            this._teardownScrollObserver();
            return;
        }
        const sentinel = this.renderRoot.querySelector('[data-picker-scroll-sentinel]');
        if (!(sentinel instanceof Element)) {
            this._teardownScrollObserver();
            return;
        }
        if (this._scrollObserver !== null && this._observedSentinel === sentinel) {
            return;
        }
        this._teardownScrollObserver();
        this._scrollObserver = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    void this._loadMorePickerItems();
                }
            },
            { root: null, rootMargin: '120px', threshold: 0 },
        );
        this._scrollObserver.observe(sentinel);
        this._observedSentinel = sentinel;
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

    _isPickerCategoryLoading(category: string) {
        return this._pickerLoadingCategory === category;
    }

    _pickerHasMore(category: string) {
        return this._pickerHasMoreByCategory.get(category) === true;
    }

    _pickerLoadErrorMessage(category: string) {
        const message = this._pickerErrorByCategory.get(category);
        if (typeof message === 'string' && message.length > 0) {
            return message;
        }
        return null;
    }

    _pickerSearchQuery() {
        return typeof this._search === 'string' ? this._search.trim() : '';
    }

    async _ensurePickerCategoryLoaded(category: string, { append = false } = {}) {
        if (typeof category !== 'string' || category.length === 0) {
            throw new Error('flows-library-picker-modal: picker category required');
        }
        const q = this._pickerSearchQuery();
        if (this._pickerActiveQuery !== q) {
            this._pickerItemsByCategory.delete(category);
            this._pickerNextOffsetByCategory.delete(category);
            this._pickerHasMoreByCategory.delete(category);
            this._pickerActiveQuery = q;
            append = false;
            // Смена q отменяет in-flight load предыдущего запроса.
            this._pickerLoadGeneration += 1;
            this._pickerLoadingCategory = null;
            this._pickerLoadingMore = false;
        }
        if (!append && this._pickerItemsByCategory.has(category)) {
            return;
        }
        if (append && this._pickerHasMoreByCategory.get(category) !== true) {
            return;
        }
        if (append) {
            if (this._pickerLoadingMore || this._pickerLoadingCategory === category) {
                return;
            }
            this._pickerLoadingMore = true;
        } else {
            this._pickerLoadingCategory = category;
            this._pickerErrorByCategory.delete(category);
        }
        const loadGeneration = this._pickerLoadGeneration;
        this.requestUpdate();
        const storedOffset = this._pickerNextOffsetByCategory.get(category);
        const offset = append ? (storedOffset === undefined ? 0 : storedOffset) : 0;
        try {
            const page = await fetchToolsAllPage(
                (payload: any) => this._toolsAll.run(payload),
                {
                    offset,
                    picker_category: category,
                    q: q.length > 0 ? q : undefined,
                },
            );
            if (loadGeneration !== this._pickerLoadGeneration) {
                return;
            }
            if (this._pickerSearchQuery() !== q) {
                return;
            }
            const prev = append && Array.isArray(this._pickerItemsByCategory.get(category))
                ? this._pickerItemsByCategory.get(category)
                : [];
            const seen = new Set(
                prev
                    .map((item: any) => (isPlainObject(item) && typeof item.tool_id === 'string' ? item.tool_id : ''))
                    .filter((id: string) => id.length > 0),
            );
            const merged = [...prev];
            for (const item of page.items) {
                const toolId = typeof item.tool_id === 'string' ? item.tool_id : '';
                if (toolId.length > 0 && seen.has(toolId)) {
                    continue;
                }
                if (toolId.length > 0) {
                    seen.add(toolId);
                }
                merged.push(item);
            }
            this._pickerItemsByCategory.set(category, merged);
            this._pickerNextOffsetByCategory.set(category, offset + page.items.length);
            this._pickerHasMoreByCategory.set(category, page.hasMore);
            this._pickerLoadingCategory = null;
            this._pickerLoadingMore = false;
            this.requestUpdate();
        } catch (err) {
            if (loadGeneration !== this._pickerLoadGeneration) {
                return;
            }
            this._pickerLoadingCategory = null;
            this._pickerLoadingMore = false;
            const fromOp = typeof this._toolsAll.error === 'string' && this._toolsAll.error.length > 0
                ? this._toolsAll.error
                : null;
            const fromErr = err instanceof Error && typeof err.message === 'string' && err.message.length > 0
                ? err.message
                : null;
            const errorMessage = fromOp || fromErr || 'flows-library-picker-modal: tools_all failed';
            this._pickerErrorByCategory.set(category, errorMessage);
            this.requestUpdate();
        }
    }

    async _loadMorePickerItems() {
        const category = this._currentPickerCategory();
        await this._ensurePickerCategoryLoaded(category, { append: true });
    }

    _onToolCategoryTabChange(nextTab: any) {
        this._toolCategoryTab = nextTab;
        void this._ensurePickerCategoryLoaded(this._currentPickerCategory());
        if (this._usesMcpGroupedLayout()) {
            void this._mcpServers.load();
        }
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._search = '';
            this._toolCategoryTab = 'all';
            this._codeLanguage = 'python';
            this._testFeedback = null;
            this._testingServerId = null;
            this._syncingServerId = null;
            this._selectedToolIds = [];
            this._collapsedTags = {};
            this._resetPickerCache();
            this.size = 'full';
            if (this._isCodeNodeTemplates()) {
                if (this.pickMode !== 'code_node') {
                    this.pickMode = 'code_node';
                }
                void this._loadCodeTemplates();
                void this._ensurePickerCategoryLoaded('code');
                void this._loadTagGroupDescriptions();
                return;
            }
            void this._ensurePickerCategoryLoaded(this._currentPickerCategory());
            void this._loadTagGroupDescriptions();
            if (this._usesMcpGroupedLayout()) {
                void this._mcpServers.load();
            }
        }
        if (changed.has('open') && !this.open) {
            this._teardownScrollObserver();
            if (this._searchDebounceTimer !== null) {
                clearTimeout(this._searchDebounceTimer);
                this._searchDebounceTimer = null;
            }
        }
    }

    async _loadTagGroupDescriptions() {
        /** @type {Record<string, { description_ru: string, description_en: string }>} */
        const map = {};
        let offset = 0;
        while (true) {
            const result = await this._toolTagGroups.run({
                limit: TAG_GROUPS_PAGE_LIMIT,
                offset,
            });
            if (result === null || !isPlainObject(result)) {
                break;
            }
            const items = result.items;
            if (!Array.isArray(items)) {
                break;
            }
            for (const item of items) {
                if (!isPlainObject(item) || typeof item.tag !== 'string' || item.tag.length === 0) {
                    continue;
                }
                (map as any)[item.tag] = {
                    description_ru: typeof item.description_ru === 'string' ? item.description_ru : '',
                    description_en: typeof item.description_en === 'string' ? item.description_en : '',
                };
            }
            if (items.length < TAG_GROUPS_PAGE_LIMIT) {
                break;
            }
            offset += items.length;
        }
        this._tagGroupDescriptions = map;
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
        if (!isPlainObject(r) || !Array.isArray((r as any).items)) {
            return [];
        }
        return (r as any).items.filter((x: any) => isPlainObject(x));
    }

    _templateListRaw() {
        return _templatesFromResult(this._codeTemplates.lastResult);
    }

    /**
     * Каталожный шаблон → форма registry item для tag-groups.
     * @param {Record<string, unknown>} t
     * @returns {Record<string, unknown> | null}
     */
    _normalizeCatalogTemplate(t: any) {
        if (!isPlainObject(t)) {
            return null;
        }
        const id = typeof t.id === 'string' ? t.id : '';
        if (id.length === 0) {
            return null;
        }
        const name = typeof t.name === 'string' && t.name.length > 0 ? t.name : id;
        return {
            tool_id: id,
            title: name,
            description: typeof t.description === 'string' ? t.description : '',
            tags: _tagsFromItem(t),
            language: t.language,
            code: t.code,
            parameters_schema: t.parameters_schema,
            item_type: 'tool',
            _pickerSource: 'catalog',
            id,
            name,
        };
    }

    /**
     * Объединённый список: каталог code-templates + registry code tools.
     * @returns {Record<string, unknown>[]}
     */
    _codeNodePickRows() {
        const wantedLanguage = normalizeFlowCodeLanguage(this._codeLanguage);
        const catalog: any[] = [];
        for (const raw of this._templateListRaw()) {
            const normalized = this._normalizeCatalogTemplate(raw);
            if (normalized === null) {
                continue;
            }
            if (normalizeFlowCodeLanguage(normalized.language) !== wantedLanguage) {
                continue;
            }
            catalog.push(normalized);
        }
        const registry: any[] = [];
        for (const t of this._toolsAllItems()) {
            if (!isPlainObject(t) || t.item_type === 'flow') {
                continue;
            }
            if (
                _hasInlineCode(t)
                && normalizeFlowCodeLanguage(t.language) !== wantedLanguage
            ) {
                continue;
            }
            registry.push({ ...t, _pickerSource: 'registry' });
        }
        const seen = new Set();
        const rows: any[] = [];
        for (const item of [...catalog, ...registry]) {
            const toolId = typeof item.tool_id === 'string' ? item.tool_id : '';
            if (toolId.length === 0 || seen.has(toolId)) {
                continue;
            }
            seen.add(toolId);
            rows.push(item);
        }
        return rows;
    }

    _pickModeRows() {
        if (this._isCodeNodeTemplates()) {
            const list: any[] = this._codeNodePickRows();
            const q = _lower(this._pickerSearchQuery());
            if (q.length === 0) {
                return list;
            }
            // Каталог шаблонов — client filter; registry уже отфильтрован серверным q.
            return list.filter((t: any) => {
                if (t._pickerSource === 'registry') {
                    return true;
                }
                const id = typeof t.tool_id === 'string' ? t.tool_id : '';
                const title = typeof t.title === 'string' ? t.title : '';
                const desc = typeof t.description === 'string' ? t.description : '';
                return _lower(id).indexOf(q) >= 0
                    || _lower(title).indexOf(q) >= 0
                    || _lower(desc).indexOf(q) >= 0;
            });
        }
        // Server-side q уже применён при загрузке страниц.
        return this._toolsAllItems();
    }

    _mcpServerIdFromTool(item: any) {
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
        return this._toolsAllItems().filter((t: any) => isMcpToolRegistryItem(t));
    }

    _toolMatchesSearch(t: any, q: any) {
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

    _serverRecordMatchesSearch(server: any, q: any) {
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

        // Порядок с API: platform → yaml allowlist → manual → прочий catalog.
        const activeServers = asArray(this._mcpServers.items)
            .filter((s) => isPlainObject(s) && s.is_active === true);

        const knownServerIds = new Set();
        const groups = [];

        for (const server of activeServers) {
            if (typeof server.server_id !== 'string' || server.server_id.length === 0) {
                continue;
            }
            knownServerIds.add(server.server_id);
            const storedTools = toolsByServerId.get(server.server_id);
            const serverTools = storedTools === undefined ? [] : storedTools;
            const filteredTools = q.length === 0
                ? serverTools
                : serverTools.filter((t: any) => this._toolMatchesSearch(t, q));
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
                : serverTools.filter((t: any) => this._toolMatchesSearch(t, q));
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
        const serverOrder = new Map();
        for (const [index, server] of asArray(this._mcpServers.items).entries()) {
            if (typeof server.server_id === 'string' && server.server_id.length > 0) {
                serverOrder.set(server.server_id, index);
            }
        }
        flat.sort((left, right) => {
            const leftServerId = typeof left.server.server_id === 'string' ? left.server.server_id : '';
            const rightServerId = typeof right.server.server_id === 'string' ? right.server.server_id : '';
            const leftOrder = serverOrder.has(leftServerId)
                ? serverOrder.get(leftServerId)
                : Number.MAX_SAFE_INTEGER;
            const rightOrder = serverOrder.has(rightServerId)
                ? serverOrder.get(rightServerId)
                : Number.MAX_SAFE_INTEGER;
            if (leftOrder !== rightOrder) {
                return leftOrder - rightOrder;
            }
            const leftTitle = registryItemTitle(left.tool);
            const rightTitle = registryItemTitle(right.tool);
            return leftTitle.localeCompare(rightTitle, undefined, { sensitivity: 'base' });
        });
        return flat;
    }

    _renderMcpFlatToolCard(entry: any) {
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
                    ${renderRegistryItemCardIcon(tool, { size: 18, server })}
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

    _renderMcpFlatSearchBody(showTabs: any) {
        const flat = this._buildMcpFlatSearchTools();
        if (flat.length === 0) {
            return html`
                ${showTabs ? this._renderToolCategoryTabs() : nothing}
                <div class="lib-empty">${this.t('tool_picker_modal.mcp_empty_search')}</div>
                ${this._pickerHasMore(this._currentPickerCategory())
                    ? html`
                        <div data-picker-scroll-sentinel class="picker-scroll-sentinel" aria-hidden="true"></div>
                        ${this._pickerLoadingMore
                            ? html`<glass-spinner></glass-spinner>`
                            : nothing}
                    `
                    : nothing}
            `;
        }
        return html`
            ${showTabs ? this._renderToolCategoryTabs() : nothing}
            <div class="mcp-picker-flat-hint">${this.t('tool_picker_modal.mcp_flat_search_hint')}</div>
            <div class="mcp-picker-tools-grid" role="list">
                ${flat.map((entry) => this._renderMcpFlatToolCard(entry))}
            </div>
            ${this._pickerHasMore(this._currentPickerCategory())
                ? html`
                    <div data-picker-scroll-sentinel class="picker-scroll-sentinel" aria-hidden="true"></div>
                    ${this._pickerLoadingMore
                        ? html`<glass-spinner></glass-spinner>`
                        : nothing}
                `
                : nothing}
        `;
    }

    _mcpServerById(serverId: any) {
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

    _mcpTransportLabel(value: unknown) {
        if (value === 'http') {
            return this.t('mcp_servers_modal.transport_http');
        }
        if (value === 'sse') {
            return this.t('mcp_servers_modal.transport_sse');
        }
        return this.t('mcp_servers_modal.transport_unknown');
    }

    _mcpSourceLabel(source: any) {
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

    async _syncMcpServer(serverId: any) {
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

    async _runMcpTest(serverId: any) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            throw new Error('flows-library-picker-modal: serverId required for test');
        }
        this._testingServerId = serverId;
        this._testFeedback = null;
        try {
            const result = await this._testOp.run({ server_id: serverId });
            if (result !== null) {
                const toolsCount = isPlainObject(result) ? result.tools_count : undefined;
                if (typeof toolsCount !== 'number') {
                    throw new TypeError('flows-library-picker-modal: MCP test result must include tools_count');
                }
                this._testFeedback = {
                    serverId,
                    ok: true,
                    toolsCount,
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

    _renderPickerLoadError(category: string) {
        const errorMessage = this._pickerLoadErrorMessage(category);
        if (errorMessage === null) {
            return '';
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

    _renderMcpTestFeedback(serverId: any) {
        const fb = this._testFeedback;
        if (fb === null || fb.serverId !== serverId) {
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

    _renderMcpToolCard(t: any) {
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? _truncateText(t.description, 120) : '';
        const mcpServerId = typeof t.mcp_server_id === 'string' ? t.mcp_server_id : '';
        const server = this._mcpServerById(mcpServerId);
        return html`
            <platform-picker-card
                value=${typeof t.tool_id === 'string' ? t.tool_id : title}
                title=${title}
                @select=${() => this._pickToolLike(t)}
            >
                <div slot="icon">
                    ${renderRegistryItemCardIcon(t, { size: 18, server })}
                </div>
                ${desc.length > 0 ? html`<div class="mcp-picker-tool-desc">${desc}</div>` : nothing}
            </platform-picker-card>
        `;
    }

    _renderMcpServerSection(group: any) {
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
                                    @click=${(e: Event) => {
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
                            @click=${(e: Event) => {
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
                            @click=${(e: Event) => {
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
                                ${tools.map((t: any) => this._renderMcpToolCard(t))}
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
        if (loadError !== '') {
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
            ${this._pickerHasMore(this._currentPickerCategory())
                ? html`
                    <div data-picker-scroll-sentinel class="picker-scroll-sentinel" aria-hidden="true"></div>
                    ${this._pickerLoadingMore
                        ? html`<glass-spinner></glass-spinner>`
                        : nothing}
                `
                : nothing}
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

    _onSearchInput(e: CustomEvent) {
        this._search = typeof e.detail?.value === 'string' ? e.detail.value : '';
        if (this._searchDebounceTimer !== null) {
            clearTimeout(this._searchDebounceTimer);
        }
        this._searchDebounceTimer = setTimeout(() => {
            this._searchDebounceTimer = null;
            const category = this._currentPickerCategory();
            this._pickerItemsByCategory.delete(category);
            this._pickerNextOffsetByCategory.delete(category);
            this._pickerHasMoreByCategory.delete(category);
            this._pickerActiveQuery = '';
            void this._ensurePickerCategoryLoaded(category);
        }, SEARCH_DEBOUNCE_MS);
    }

    _showToolCategoryTabs() {
        if (this._isCodeNodeTemplates()) {
            return false;
        }
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
            return '';
        }
        return html`
            <platform-segmented-control
                class="source-segment"
                density="compact"
                .value=${this._toolCategoryTab}
                .items=${this._toolCategoryTabItems()}
                aria-label=${this.t('tool_picker_modal.tabs_aria')}
                @change=${(e: CustomEvent) => { this._onToolCategoryTabChange(e.detail.value); }}
            ></platform-segmented-control>
        `;
    }

    _setCodeLanguage(language: string) {
        const normalized = normalizeFlowCodeLanguage(language);
        if (this._codeLanguage === normalized) {
            return;
        }
        this._codeLanguage = normalized as string;
        void this._loadCodeTemplates();
    }

    _renderCodeLanguageSegment() {
        if (!this._isCodeNodeTemplates()) {
            return '';
        }
        const current = normalizeFlowCodeLanguage(this._codeLanguage);
        return html`
            <flows-code-language-segment
                class="source-segment"
                .value=${current}
                aria-label=${this.t('code_workbench.language_aria')}
                @change=${(e: CustomEvent) => this._setCodeLanguage(e.detail.value)}
            ></flows-code-language-segment>
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
        if (this._isCodeNodeTemplates()) {
            return html`
                <div class="tool-picker-toolbar">
                    ${this._renderCodeLanguageSegment()}
                    ${this._renderSearchField('search-wrap--tool')}
                </div>
            `;
        }
        if (this._usesMcpGroupedLayout()) {
            if (!this._showToolCategoryTabs()) {
                return '';
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

    _mcpBulkAddEnabled() {
        if (this._isCodeNodeTemplates()) {
            return false;
        }
        return typeof this.onPickBatch === 'function';
    }

    _pickToolLike(t: any) {
        if (this._isCodeNodeTemplates()) {
            if (!isPlainObject(t)) {
                return;
            }
            if (t._pickerSource === 'catalog') {
                void this._commitTemplate(t);
                return;
            }
            this._commitTool(t);
            return;
        }
        const fn = this.onPick;
        if (typeof fn !== 'function') {
            this.close();
            return;
        }
        if (!isPlainObject(t) || typeof t.tool_id !== 'string' || t.tool_id.length === 0) {
            this.close();
            return;
        }
        const kind = t.item_type === 'flow' ? 'flow' : 'tool';
        // Dispatch close first, but apply in the same event turn while the
        // opener is still connected. Deferring to a microtask lets the modal
        // state re-render the editor surface and silently loses its `change`.
        this.close();
        fn({
            kind,
            tool_id: t.tool_id,
            item: t,
        });
    }

    _pickAllMcpToolsFromServer(tools: any) {
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

    _templateParametersSchema(t: any, parsed: any) {
        if (isPlainObject(t.parameters_schema)) {
            return _parametersSchemaObject(t.parameters_schema);
        }
        if (isPlainObject(parsed) && parsed.success === true && isPlainObject(parsed.parameters_schema)) {
            return _parametersSchemaObject(parsed.parameters_schema);
        }
        return { type: 'object', properties: {}, required: [] };
    }

    async _commitTemplate(t: any) {
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
            const cfg: any = {
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

    _commitTool(t: any) {
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
        if (loadError !== '') {
            return html`
                ${this._renderToolPickerToolbar()}
                ${loadError}
            `;
        }
        const templatesLoading = this._isCodeNodeTemplates()
            && this._codeTemplates.busy
            && this._templateListRaw().length === 0;
        const toolsLoading = this._isPickerCategoryLoading(category)
            && !this._pickerItemsByCategory.has(category);
        if (templatesLoading || toolsLoading) {
            return html`
                ${this._renderToolPickerToolbar()}
                <glass-spinner></glass-spinner>
            `;
        }
        const rows = this._pickModeRows();
        const emptyKey = this._isCodeNodeTemplates()
            ? 'code_node_templates_modal.empty'
            : 'tool_picker_modal.empty';
        if (rows.length === 0) {
            return html`
                ${this._renderToolPickerToolbar()}
                <div class="lib-empty">${this.t(emptyKey)}</div>
            `;
        }
        const locale = this._pickerLocale();
        const groups = buildToolTagGroups(rows, {
            search: this._search,
            descriptionsByTag: this._tagGroupDescriptions,
            locale,
        });
        if (groups.length === 0) {
            return html`
                ${this._renderToolPickerToolbar()}
                <div class="lib-empty">${this.t(emptyKey)}</div>
            `;
        }
        const searchActive = _lower(this._pickerSearchQuery()).length > 0;
        const hasMore = this._pickerHasMore(category);
        return html`
            ${this._renderToolPickerToolbar()}
            <div class="tag-groups" role="list">
                ${groups.map((group) => this._renderTagGroupCard(group, { forceExpand: searchActive }))}
            </div>
            ${hasMore
                ? html`
                    <div data-picker-scroll-sentinel class="picker-scroll-sentinel" aria-hidden="true"></div>
                    ${this._pickerLoadingMore
                        ? html`<glass-spinner></glass-spinner>`
                        : nothing}
                `
                : nothing}
        `;
    }

    _tagGroupTitle(tag: any) {
        const knownKeys = {
            crm: 'tool_picker_modal.tag_groups.crm',
            documents: 'tool_picker_modal.tag_groups.documents',
            files: 'tool_picker_modal.tag_groups.files',
            sync: 'tool_picker_modal.tag_groups.sync',
            worktracker: 'tool_picker_modal.tag_groups.worktracker',
            web: 'tool_picker_modal.tag_groups.web',
            knowledge: 'tool_picker_modal.tag_groups.knowledge',
            scheduling: 'tool_picker_modal.tag_groups.scheduling',
            google_docs: 'tool_picker_modal.tag_groups.google_docs',
            google_sheets: 'tool_picker_modal.tag_groups.google_sheets',
            viz: 'tool_picker_modal.tag_groups.viz',
            flows: 'tool_picker_modal.tag_groups.flows',
            device: 'tool_picker_modal.tag_groups.device',
            text: 'tool_picker_modal.tag_groups.text',
            misc: 'tool_picker_modal.tag_groups.misc',
            mcp: 'tool_picker_modal.tag_groups.mcp',
            flow: 'tool_picker_modal.tag_groups.flow',
        };
        const key = (knownKeys as any)[tag];
        if (typeof key === 'string') {
            return this.t(key);
        }
        return `#${tag}`;
    }

    _pickerLocale() {
        const locale = this._localeSelect?.value;
        if (typeof locale === 'string' && locale.length > 0) {
            return locale;
        }
        return 'ru';
    }

    _isToolSelected(toolId: string) {
        return (this._selectedToolIds.includes(toolId) as any);
    }

    _toggleToolSelection(toolId: string) {
        if (typeof toolId !== 'string' || toolId.length === 0) {
            return;
        }
        if ((this._selectedToolIds.includes(toolId) as any)) {
            this._selectedToolIds = (this._selectedToolIds.filter as any)((id: string) => id !== toolId);
            return;
        }
        this._selectedToolIds = [...this._selectedToolIds, toolId];
    }

    _toggleGroupSelection(tools: any) {
        const ids = tools
            .map((t: any) => (isPlainObject(t) && typeof t.tool_id === 'string' ? t.tool_id : ''))
            .filter((id: string) => id.length > 0);
        if (ids.length === 0) {
            return;
        }
        const allSelected = ids.every((id: string) => (this._selectedToolIds.includes(id) as any));
        if (allSelected) {
            const remove = new Set(ids);
            this._selectedToolIds = (this._selectedToolIds.filter as any)((id: string) => !remove.has(id));
            return;
        }
        const next = new Set(this._selectedToolIds);
        for (const id of ids) {
            next.add(id);
        }
        this._selectedToolIds = [...next];
    }

    _groupAllSelected(tools: any) {
        const ids = tools
            .map((t: any) => (isPlainObject(t) && typeof t.tool_id === 'string' ? t.tool_id : ''))
            .filter((id: string) => id.length > 0);
        return ids.length > 0 && ids.every((id: string) => (this._selectedToolIds.includes(id) as any));
    }

    _toggleTagCollapsed(tag: any) {
        const next = { ...this._collapsedTags };
        next[tag] = !next[tag];
        this._collapsedTags = next;
    }

    _confirmSelectedTools() {
        const selectedSet = new Set(this._selectedToolIds);
        const items = this._pickModeRows().filter(
            (t: any) => isPlainObject(t) && typeof t.tool_id === 'string' && selectedSet.has(t.tool_id),
        );
        if (items.length === 0) {
            return;
        }
        if (typeof this.onPickBatch === 'function') {
            this.close();
            queueMicrotask(() => {
                this.onPickBatch!({ kind: 'tool', items });
            });
            return;
        }
        if (items.length === 1) {
            this._pickToolLike(items[0]);
        }
    }

    _renderTagGroupCard(group: any, { forceExpand = false } = {}) {
        const tag = group.tag;
        const tools = group.tools;
        const collapsed = forceExpand ? false : (this._collapsedTags as any)[tag] === true;
        const hue = hueFromString(tag);
        const allSelected = this._groupAllSelected(tools);
        const batchEnabled = this._mcpBulkAddEnabled();
        const groupIcon = tagGroupIconName(tag);
        return html`
            <section
                class="tag-group"
                style=${`--tag-group-hue: ${hue}`}
                aria-labelledby=${`tag-group-${tag}`}
                data-tag=${tag}
            >
                <div class="tag-group-head">
                    <div class="tag-group-head-main">
                        <div class="tag-group-icon" aria-hidden="true">
                            <platform-icon name=${groupIcon} size="22"></platform-icon>
                        </div>
                        <div class="tag-group-titles">
                            <h3 id=${`tag-group-${tag}`}>${this._tagGroupTitle(tag)}</h3>
                            ${group.description.length > 0
                                ? html`<p class="tag-group-blurb">${group.description}</p>`
                                : nothing}
                            <div class="tag-group-meta">
                                ${this.t('tool_picker_modal.tag_group_tools_count', { n: tools.length })}
                            </div>
                        </div>
                    </div>
                    <div class="tag-group-actions">
                        ${batchEnabled
                            ? html`
                                <platform-button
                                    variant=${allSelected ? 'secondary' : 'ghost'}
                                    density="dense"
                                    title=${this.t('tool_picker_modal.tag_group_select_all_aria')}
                                    aria-label=${this.t('tool_picker_modal.tag_group_select_all_aria')}
                                    @click=${(e: Event) => {
                                        e.stopPropagation();
                                        this._toggleGroupSelection(tools);
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
                            title=${collapsed
                                ? this.t('tool_picker_modal.tag_group_expand_aria')
                                : this.t('tool_picker_modal.tag_group_collapse_aria')}
                            aria-label=${collapsed
                                ? this.t('tool_picker_modal.tag_group_expand_aria')
                                : this.t('tool_picker_modal.tag_group_collapse_aria')}
                            @click=${(e: Event) => {
                                e.stopPropagation();
                                this._toggleTagCollapsed(tag);
                            }}
                        >
                            <platform-icon name=${collapsed ? 'chevron-down' : 'chevron-up'} size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                ${collapsed
                    ? nothing
                    : html`
                        <div class="tag-group-tools" role="list">
                            ${tools.map((t: any) => this._renderTagToolCard(t, { batchEnabled }))}
                        </div>
                    `}
            </section>
        `;
    }

    _tagToolKindChipLabel(kind: string, language: any) {
        if (kind === 'code' && language.length > 0) {
            return flowCodeLanguageShortLabel(language);
        }
        if (kind === 'flow') {
            return this.t('tool_picker_modal.kind_flow');
        }
        if (kind === 'mcp') {
            return this.t('tool_picker_modal.kind_mcp');
        }
        if (kind === 'code') {
            return this.t('tool_picker_modal.kind_code');
        }
        return this.t('tool_picker_modal.kind_tool');
    }

    _confirmationFloorChipLabel(floor: any) {
        if (floor === 'preview') {
            return this.t('tool_picker_modal.confirmation_preview');
        }
        if (floor === 'approval') {
            return this.t('tool_picker_modal.confirmation_approval');
        }
        return '';
    }

    _renderTagToolCard(t: any, { batchEnabled }: any) {
        const toolId = typeof t.tool_id === 'string' ? t.tool_id : '';
        const title = registryItemTitle(t);
        const desc = typeof t.description === 'string' ? _truncateText(t.description, 140) : '';
        const selected = this._isToolSelected(toolId);
        const kind = registryItemVisualKind(t);
        const language = registryItemLanguage(t);
        const chipLabel = this._tagToolKindChipLabel(kind, language);
        const mcpServerId = typeof t.mcp_server_id === 'string' ? t.mcp_server_id : '';
        const server = mcpServerId.length > 0 ? this._mcpServerById(mcpServerId) : null;
        const effects = Array.isArray(t.effects)
            ? t.effects.filter((effect: any) => typeof effect === 'string')
            : [];
        const confirmationFloor =
            typeof t.confirmation_floor === 'string' ? t.confirmation_floor : '';
        const floorLabel = this._confirmationFloorChipLabel(confirmationFloor);
        return html`
            <platform-picker-card
                value=${toolId.length > 0 ? toolId : title}
                title=${title}
                ?selected=${batchEnabled && selected}
                data-tool-id=${toolId}
                @select=${() => {
                    if (batchEnabled) {
                        this._toggleToolSelection(toolId);
                        return;
                    }
                    this._pickToolLike(t);
                }}
            >
                <div slot="icon">
                    ${renderRegistryItemCardIcon(t, { size: 28, server })}
                </div>
                <div class="tag-tool-card-body">
                    ${toolId.length > 0 && toolId !== title
                        ? html`<span class="tag-tool-id">${toolId}</span>`
                        : nothing}
                    ${desc.length > 0 ? html`<div class="tag-tool-desc">${desc}</div>` : nothing}
                    <div class="tag-tool-meta">
                        <span class="tag-tool-chip" data-kind=${kind}>${chipLabel}</span>
                        ${effects.map(
                            (effect: any) => html`
                                <span class="tag-tool-chip" data-kind="effect">${effect}</span>
                            `,
                        )}
                        ${floorLabel.length > 0
                            ? html`<span class="tag-tool-chip" data-kind="floor">${floorLabel}</span>`
                            : nothing}
                        ${batchEnabled
                            ? html`
                                <platform-button
                                    class="tag-tool-add-one"
                                    variant="ghost"
                                    icon-only
                                    density="dense"
                                    title=${this.t('tool_picker_modal.tag_tool_add_one_aria')}
                                    aria-label=${this.t('tool_picker_modal.tag_tool_add_one_aria')}
                                    @click=${(e: Event) => {
                                        e.stopPropagation();
                                        this._pickToolLike(t);
                                    }}
                                >
                                    <platform-icon name="plus" size="14"></platform-icon>
                                </platform-button>
                            `
                            : nothing}
                    </div>
                </div>
            </platform-picker-card>
        `;
    }

    override renderFooter() {
        if (this._isCodeNodeTemplates() || this._usesMcpGroupedLayout()) {
            return html``;
        }
        if (!this._mcpBulkAddEnabled()) {
            return html``;
        }
        const count = (this._selectedToolIds.length as any);
        return html`
            <div class="picker-footer">
                <span class="picker-footer-count">
                    ${this.t('tool_picker_modal.selected_count', { n: count })}
                </span>
                <div class="picker-footer-actions">
                    <platform-button
                        variant="ghost"
                        density="compact"
                        ?disabled=${count === 0}
                        @click=${() => { this._selectedToolIds = []; }}
                    >${this.t('tool_picker_modal.clear_selection')}</platform-button>
                    <platform-button
                        variant="primary"
                        density="compact"
                        ?disabled=${count === 0}
                        @click=${() => this._confirmSelectedTools()}
                    >${this.t('tool_picker_modal.add_selected')}</platform-button>
                </div>
            </div>
        `;
    }

    override renderHeader() {
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

    override renderHeaderActions() {
        if (this._isCodeNodeTemplates() || !this._usesMcpGroupedLayout()) {
            return html``;
        }
        return this._renderHeaderSearch();
    }

    override renderBody() {
        return this._renderBodyToolPick();
    }
}

const LIB_TAG = 'flows-library-picker-modal';

customElements.define(LIB_TAG, FlowsLibraryPickerModal);
registerModalKind('flows.tool_picker', LIB_TAG);
registerModalKind('flows.code_node_templates', LIB_TAG);

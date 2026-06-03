/**
 * flows-api-console-modal — A2A спецификация и live-run для текущего flow.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/editors/flows-code-editor.js';
import { asObject, isPlainObject } from '../_helpers/flows-resolvers.js';

const TAB_KEYS = Object.freeze(['start', 'examples', 'fields', 'run']);
const LANG_KEYS = Object.freeze(['curl', 'python', 'javascript']);
const MODE_KEYS = Object.freeze(['stream', 'sync', 'async']);
const SYSTEM_VARIABLE_KEYS = Object.freeze([
    'user_id',
    'user_name',
    'user_email',
    'user_first_name',
    'user_last_name',
    'company_id',
    'company_name',
    'active_namespace',
    'user_language',
    'interface_language_code',
    'interface_language_name',
]);
const METHOD_ROWS = Object.freeze([
    ['message/stream', 'api_console.method_stream'],
    ['message/send', 'api_console.method_send'],
    ['tasks/get', 'api_console.method_get'],
    ['tasks/cancel', 'api_console.method_cancel'],
    ['tasks/resubscribe', 'api_console.method_resubscribe'],
    ['agent/getAuthenticatedExtendedCard', 'api_console.method_card'],
    ['tasks/pushNotificationConfig/*', 'api_console.method_push'],
]);
const JSON_RPC_FIELD_ROWS = Object.freeze([
    ['jsonrpc', 'api_console.field_jsonrpc'],
    ['id', 'api_console.field_id'],
    ['method', 'api_console.field_method'],
    ['params', 'api_console.field_params'],
    ['params.message', 'api_console.field_params_message'],
    ['params.message.messageId', 'api_console.field_message_id'],
    ['params.message.role', 'api_console.field_role'],
    ['params.message.parts', 'api_console.field_parts'],
    ['params.message.contextId', 'api_console.field_context_id'],
    ['params.message.taskId', 'api_console.field_task_id'],
    ['params.metadata', 'api_console.field_metadata'],
    ['params.metadata.branch', 'api_console.field_branch'],
    ['params.metadata.variables', 'api_console.field_variables'],
    ['params.metadata.version', 'api_console.field_version'],
    ['params.metadata.breakpoints', 'api_console.field_breakpoints'],
    ['params.metadata.triggers', 'api_console.field_triggers'],
    ['params.metadata.execution_mode', 'api_console.field_execution_mode'],
]);
const VARIABLE_FIELD_ROWS = Object.freeze([
    ['value', 'api_console.var_field_value'],
    ['secret', 'api_console.var_field_secret'],
    ['public', 'api_console.var_field_public'],
    ['title', 'api_console.var_field_title'],
    ['description', 'api_console.var_field_description'],
    ['order', 'api_console.var_field_order'],
]);

function _apiBranchId(branchId) {
    const raw = typeof branchId === 'string' && branchId.trim() !== '' ? branchId.trim() : 'base';
    return raw === 'base' ? 'default' : raw;
}

function _safeToken(value) {
    const raw = typeof value === 'string' && value.trim() !== '' ? value.trim() : 'flow';
    return raw.replace(/[^a-zA-Z0-9_:-]/g, '_');
}

function _sampleContextId(flowId, branchId) {
    return `api_${_safeToken(flowId)}_${_safeToken(_apiBranchId(branchId))}_demo`;
}

function _normalizeVariable(raw) {
    if (raw === null) {
        return { value: '', secret: false, public: false, title: '', description: '', order: null };
    }
    if (raw === undefined) {
        return { value: '', secret: false, public: false, title: '', description: '', order: null };
    }
    if (isPlainObject(raw) && 'value' in raw) {
        return {
            value: raw.value,
            secret: Boolean(raw.secret),
            public: Boolean(raw.public),
            title: typeof raw.title === 'string' ? raw.title : '',
            description: typeof raw.description === 'string' ? raw.description : '',
            order: typeof raw.order === 'number' ? raw.order : null,
        };
    }
    return { value: raw, secret: false, public: false, title: '', description: '', order: null };
}

function _visibleVariableValue(raw) {
    const v = _normalizeVariable(raw);
    if (v.secret) {
        return '***';
    }
    if (typeof v.value === 'string') {
        return v.value;
    }
    return JSON.stringify(v.value);
}

function _publicVariableEntries(variables) {
    const obj = isPlainObject(variables) ? variables : {};
    return Object.entries(obj)
        .map(([key, raw]) => ({ key, ..._normalizeVariable(raw) }))
        .sort((a, b) => {
            const ao = typeof a.order === 'number' ? a.order : 100000;
            const bo = typeof b.order === 'number' ? b.order : 100000;
            if (ao !== bo) {
                return ao - bo;
            }
            return a.key.localeCompare(b.key);
        });
}

function _jsonPretty(value) {
    return JSON.stringify(value, null, 2);
}

function _displayJson(value) {
    if (typeof value === 'string') {
        return value;
    }
    return _jsonPretty(value);
}

function _shellSingleQuote(value) {
    return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function _parseVariablesText(text) {
    const raw = typeof text === 'string' ? text.trim() : '';
    if (raw.length === 0) {
        return {};
    }
    const parsed = JSON.parse(raw);
    if (!isPlainObject(parsed)) {
        throw new Error('metadata.variables must be a JSON object');
    }
    return parsed;
}

function _methodForMode(mode) {
    if (mode === 'stream') {
        return 'message/stream';
    }
    return 'message/send';
}

function _acceptForMode(mode) {
    if (mode === 'stream') {
        return 'text/event-stream';
    }
    return 'application/json';
}

function _terminalStatesText() {
    return 'completed, failed, input-required';
}

function _requestHeadersForMode(mode) {
    return {
        Accept: _acceptForMode(mode),
        'Content-Type': 'application/json',
    };
}

function _resultResponse(result) {
    return isPlainObject(result) && isPlainObject(result.response) ? result.response : null;
}

function _resultRequest(result) {
    return isPlainObject(result) && isPlainObject(result.request) ? result.request : null;
}

function _resultStreamEvents(result) {
    if (isPlainObject(result) && Array.isArray(result.stream_events)) {
        return result.stream_events;
    }
    if (isPlainObject(result) && Array.isArray(result.frames)) {
        return result.frames.map((frame, index) => ({ index, event: 'message', data: frame }));
    }
    return [];
}

function _resultPollExchanges(result) {
    if (isPlainObject(result) && Array.isArray(result.poll_exchanges)) {
        return result.poll_exchanges;
    }
    return [];
}

function _responseBodyForResult(result) {
    const response = _resultResponse(result);
    if (response && 'body' in response) {
        return response.body;
    }
    if (isPlainObject(result) && 'raw' in result) {
        return result.raw;
    }
    return result;
}

function _rawResponseTextForResult(result) {
    const response = _resultResponse(result);
    if (response && typeof response.raw_text === 'string' && response.raw_text.length > 0) {
        return response.raw_text;
    }
    return _displayJson(_responseBodyForResult(result));
}

function _resultHeadersPayload(result) {
    return {
        request: _resultRequest(result),
        response: _resultResponse(result),
    };
}

function _resultViewPayload(result, view) {
    if (view === 'events') {
        return _resultStreamEvents(result);
    }
    if (view === 'headers') {
        return _resultHeadersPayload(result);
    }
    if (view === 'raw') {
        return _rawResponseTextForResult(result);
    }
    if (view === 'polls') {
        return _resultPollExchanges(result);
    }
    if (view === 'full') {
        return result;
    }
    return _responseBodyForResult(result);
}

export class FlowsApiConsoleModal extends PlatformModal {
    static modalKind = 'flows.api_console';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _activeTab: { state: true },
        _language: { state: true },
        _mode: { state: true },
        _messageText: { state: true },
        _contextId: { state: true },
        _variablesText: { state: true },
        _result: { state: true },
        _resultView: { state: true },
        _lastError: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host {
                --modal-width: min(1360px, calc(100vw - 24px));
            }
            .modal.full .modal-content:has(.api-console-shell) {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }
            .api-console-shell {
                min-height: 0;
                flex: 1 1 auto;
                display: grid;
                grid-template-columns: 220px minmax(0, 1fr) minmax(330px, 0.42fr);
                gap: var(--space-3);
                overflow: hidden;
            }
            .api-console-shell.run-focused {
                grid-template-columns: 220px minmax(0, 1fr);
            }
            .api-side,
            .api-main,
            .api-live {
                min-height: 0;
                overflow: auto;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            .api-side {
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .api-main,
            .api-live {
                padding: var(--space-4);
            }
            .api-nav {
                display: grid;
                gap: var(--space-1);
            }
            .api-nav button,
            .lang-tabs button {
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .api-nav button {
                min-height: 40px;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-2);
                text-align: left;
                font-size: var(--text-sm);
            }
            .api-nav button:hover,
            .lang-tabs button:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .api-nav button[active],
            .lang-tabs button[active] {
                background: var(--glass-solid-strong);
                color: var(--accent);
                border-color: var(--border-medium);
            }
            .endpoint-card {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
            }
            .endpoint-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0;
            }
            .endpoint-value {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-primary);
                overflow-wrap: anywhere;
            }
            .hero {
                display: grid;
                gap: var(--space-3);
                padding-bottom: var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-4);
            }
            .hero-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin: 0;
                font-size: var(--text-xl);
                color: var(--text-primary);
            }
            .hero-sub {
                margin: 0;
                color: var(--text-secondary);
                line-height: 1.5;
                max-width: 920px;
            }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .metric {
                padding: var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                min-width: 0;
            }
            .metric span {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: 3px;
            }
            .metric code {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-primary);
                overflow-wrap: anywhere;
            }
            .section {
                display: grid;
                gap: var(--space-3);
                margin-bottom: var(--space-5);
            }
            .section-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin: 0;
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
            }
            .section-copy {
                margin: 0;
                color: var(--text-secondary);
                line-height: 1.55;
                font-size: var(--text-sm);
            }
            .steps {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .step {
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                display: grid;
                gap: var(--space-2);
            }
            .step b {
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .step p {
                margin: 0;
                color: var(--text-secondary);
                line-height: 1.45;
                font-size: var(--text-sm);
            }
            .code-head,
            .run-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .lang-tabs {
                display: inline-flex;
                gap: 2px;
                padding: 3px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            .lang-tabs button {
                min-height: 30px;
                padding: 0 var(--space-2);
                font-size: var(--text-xs);
            }
            .mode-tabs {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 2px;
                padding: 3px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            .mode-tabs button {
                min-height: 34px;
                padding: 0 var(--space-2);
                border: 1px solid transparent;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                transition: var(--motion-transition-interactive);
            }
            .mode-tabs button:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .mode-tabs button[active] {
                background: var(--glass-solid-strong);
                color: var(--accent);
                border-color: var(--border-medium);
            }
            .mode-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .mode-card {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                display: grid;
                gap: var(--space-2);
            }
            .mode-card[active] {
                border-color: var(--accent);
                background: var(--glass-solid-strong);
            }
            .mode-card b {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .mode-card code {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--accent);
            }
            .mode-card p {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.45;
            }
            .copy-btn,
            .ghost-btn {
                min-height: 30px;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 0 var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                font-size: var(--text-xs);
            }
            .copy-btn:hover,
            .ghost-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-strong);
            }
            pre {
                margin: 0;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                border: 1px solid var(--border-subtle);
                color: var(--text-primary);
                overflow: auto;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.55;
                max-height: 420px;
            }
            .table-wrap {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                background: var(--glass-solid-medium);
            }
            table {
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
            }
            th,
            td {
                padding: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
                text-align: left;
                vertical-align: top;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.45;
            }
            tr:last-child td {
                border-bottom: none;
            }
            th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0;
                font-weight: var(--font-medium);
            }
            td code,
            th code {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-primary);
                overflow-wrap: anywhere;
            }
            .pill-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .pill {
                display: inline-flex;
                align-items: center;
                min-height: 22px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }
            .pill[data-tone="accent"] {
                color: var(--accent);
                border-color: var(--accent);
            }
            .run-form {
                display: grid;
                gap: var(--space-3);
            }
            .run-textarea-label {
                display: block;
                margin-bottom: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0;
            }
            .run-textarea {
                width: 100%;
                min-height: 128px;
                resize: vertical;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                color: var(--text-primary);
                padding: var(--space-2);
                box-sizing: border-box;
                font: inherit;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.5;
            }
            .run-textarea:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            .run-actions {
                display: flex;
                gap: var(--space-2);
                align-items: center;
                justify-content: flex-end;
            }
            .run-workbench {
                display: grid;
                grid-template-columns: minmax(340px, 0.42fr) minmax(0, 1fr);
                gap: var(--space-3);
                align-items: start;
            }
            .run-column {
                min-width: 0;
                display: grid;
                gap: var(--space-3);
            }
            .api-panel {
                min-width: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .api-panel-head {
                min-height: 46px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            .api-panel-title {
                min-width: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
            }
            .api-panel-title span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .api-panel-body {
                min-width: 0;
                display: grid;
                gap: var(--space-3);
                padding: var(--space-3);
            }
            .request-header-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .request-header {
                min-width: 0;
                padding: var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
            }
            .request-header span {
                display: block;
                margin-bottom: 3px;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .request-header code {
                display: block;
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                overflow-wrap: anywhere;
            }
            .api-json-editor {
                height: 260px;
                min-height: 240px;
                background: var(--bg-elevated);
            }
            .api-json-editor.compact {
                height: 180px;
                min-height: 180px;
            }
            .api-json-editor.tall {
                height: min(520px, 52vh);
                min-height: 420px;
            }
            .api-code-editor {
                height: 420px;
                min-height: 360px;
                background: var(--bg-elevated);
            }
            .api-code-editor.short {
                height: 220px;
                min-height: 220px;
            }
            .response-inspector {
                min-width: 0;
                display: grid;
                gap: var(--space-3);
            }
            .status-strip {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
                gap: var(--space-2);
            }
            .status-item {
                min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            .status-item b {
                display: block;
                margin-bottom: 2px;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .status-item code,
            .status-item span {
                display: block;
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                overflow-wrap: anywhere;
            }
            .status-item[data-tone="ok"] {
                border-color: var(--success-border);
                background: var(--success-bg);
            }
            .status-item[data-tone="error"] {
                border-color: var(--error-border);
                background: var(--error-bg);
            }
            .assistant-response {
                min-height: 72px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                color: var(--text-primary);
                padding: var(--space-3);
                line-height: 1.55;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }
            .response-tabs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                padding: 3px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            .response-tabs button {
                min-height: 30px;
                padding: 0 var(--space-2);
                border: 1px solid transparent;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                transition: var(--motion-transition-interactive);
            }
            .response-tabs button:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .response-tabs button[active] {
                background: var(--glass-solid-strong);
                color: var(--accent);
                border-color: var(--border-medium);
            }
            .run-result {
                display: grid;
                gap: var(--space-2);
                margin-top: var(--space-4);
            }
            .result-box {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                padding: var(--space-3);
                color: var(--text-secondary);
                line-height: 1.55;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                min-height: 92px;
                max-height: 220px;
                overflow: auto;
                font-size: var(--text-sm);
            }
            .error-box {
                border-color: var(--error-border);
                background: var(--error-bg);
                color: var(--error);
            }
            .empty-note {
                padding: var(--space-3);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                line-height: 1.45;
            }
            @media (max-width: 1120px) {
                .api-console-shell {
                    grid-template-columns: 190px minmax(0, 1fr);
                }
                .api-console-shell.run-focused {
                    grid-template-columns: 190px minmax(0, 1fr);
                }
                .api-live {
                    grid-column: 1 / -1;
                }
            }
            @media (max-width: 760px) {
                .api-console-shell {
                    grid-template-columns: minmax(0, 1fr);
                }
                .metric-grid,
                .steps,
                .mode-grid {
                    grid-template-columns: minmax(0, 1fr);
                }
                .api-side {
                    overflow: visible;
                }
                .run-workbench,
                .request-header-grid,
                .status-strip {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.flowId = '';
        this.branchId = 'base';
        this._activeTab = 'start';
        this._language = 'curl';
        this._mode = 'stream';
        this._messageText = '';
        this._contextId = '';
        this._variablesText = '{}';
        this._result = null;
        this._resultView = 'response';
        this._lastError = '';
        this._editor = this.useOp('flows/editor');
        this._run = this.useOp('flows/api_console_run');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('open') && this.open) {
            this._ensureDefaults();
        }
        let identityChanged = changed.has('flowId');
        if (!identityChanged) {
            identityChanged = changed.has('branchId');
        }
        if (identityChanged) {
            this._ensureDefaults();
        }
    }

    _ensureDefaults() {
        if (typeof this._messageText !== 'string') {
            this._messageText = this.t('api_console.default_message');
        }
        if (this._messageText.length === 0) {
            this._messageText = this.t('api_console.default_message');
        }
        if (typeof this._contextId !== 'string') {
            this._contextId = _sampleContextId(this.flowId, this.branchId);
        }
        if (this._contextId.length === 0) {
            this._contextId = _sampleContextId(this.flowId, this.branchId);
        }
        if (typeof this._variablesText !== 'string') {
            this._variablesText = '{}';
        }
        if (this._variablesText.trim().length === 0) {
            this._variablesText = '{}';
        }
    }

    _setTab(tab) {
        if (!TAB_KEYS.includes(tab)) {
            throw new Error(`flows-api-console-modal: unknown tab ${tab}`);
        }
        this._activeTab = tab;
    }

    _setLanguage(language) {
        if (!LANG_KEYS.includes(language)) {
            throw new Error(`flows-api-console-modal: unknown language ${language}`);
        }
        this._language = language;
    }

    _setMode(mode) {
        if (!MODE_KEYS.includes(mode)) {
            throw new Error(`flows-api-console-modal: unknown mode ${mode}`);
        }
        this._mode = mode;
        this._result = null;
        this._resultView = 'response';
        this._lastError = '';
    }

    _setResultView(view) {
        const tabs = this._resultTabs(isPlainObject(this._result) ? this._result : null);
        if (!tabs.includes(view)) {
            throw new Error(`flows-api-console-modal: unknown result view ${view}`);
        }
        this._resultView = view;
    }

    _flowState() {
        return asObject(this._editor.state);
    }

    _flowConfig() {
        const state = this._flowState();
        return isPlainObject(state.flowConfig) ? state.flowConfig : {};
    }

    _branchData() {
        const state = this._flowState();
        return isPlainObject(state.branchData) ? state.branchData : {};
    }

    _variablesEntries() {
        const branchData = this._branchData();
        return _publicVariableEntries(branchData.variables);
    }

    _endpointPath() {
        const id = typeof this.flowId === 'string' && this.flowId.length > 0 ? this.flowId : ':flow_id';
        return `/flows/api/v1/${encodeURIComponent(id)}`;
    }

    _endpointUrl() {
        const origin =
            typeof window !== 'undefined' && window.location && typeof window.location.origin === 'string'
                ? window.location.origin
                : 'https://your-company.example.com';
        return `${origin}${this._endpointPath()}`;
    }

    _metadataForMode(variables, mode) {
        const metadata = {
            branch: _apiBranchId(this.branchId),
            variables,
        };
        if (mode === 'async') {
            metadata.execution_mode = 'async';
        }
        return metadata;
    }

    _requestBody() {
        const variables = _parseVariablesText(this._variablesText);
        const messageId = `msg_${_safeToken(this.flowId)}_${Date.now()}`;
        const mode = this._mode;
        return {
            jsonrpc: '2.0',
            id: `req_${Date.now()}`,
            method: _methodForMode(mode),
            params: {
                message: {
                    messageId,
                    role: 'user',
                    parts: [{ kind: 'text', text: this._messageText }],
                    contextId: this._contextId,
                },
                metadata: this._metadataForMode(variables, mode),
            },
        };
    }

    _sampleBody(mode = this._mode) {
        let variables;
        try {
            variables = _parseVariablesText(this._variablesText);
        } catch {
            variables = {};
        }
        return {
            jsonrpc: '2.0',
            id: 'req_001',
            method: _methodForMode(mode),
            params: {
                message: {
                    messageId: 'msg_001',
                    role: 'user',
                    parts: [{ kind: 'text', text: this._messageText }],
                    contextId: this._contextId,
                },
                metadata: this._metadataForMode(variables, mode),
            },
        };
    }

    _tasksGetBody() {
        return {
            jsonrpc: '2.0',
            id: 'get_001',
            method: 'tasks/get',
            params: {
                id: this._contextId,
                historyLength: 20,
            },
        };
    }

    _examples() {
        const mode = this._mode;
        const body = this._sampleBody(mode);
        const bodyText = _jsonPretty(body);
        const endpoint = this._endpointUrl();
        const flowId = typeof this.flowId === 'string' && this.flowId.length > 0 ? this.flowId : 'your_flow_id';
        const baseUrl = endpoint.replace(this._endpointPath(), '');
        const accept = _acceptForMode(mode);
        const tasksGetBodyText = _jsonPretty(this._tasksGetBody());
        const asyncCurlSuffix = mode === 'async'
            ? `

# Async returns status.state=submitted. Poll by contextId or task_id:
curl "$BASE_URL/flows/api/v1/${flowId}" \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Accept: application/json" \\
  -H "Content-Type: application/json" \\
  --data-raw ${_shellSingleQuote(tasksGetBodyText)}`
            : '';
        const syncPythonTail = mode === 'stream'
            ? `with requests.post(
    f"{base_url}/flows/api/v1/${flowId}",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    },
    json=payload,
    stream=True,
    timeout=300,
) as response:
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        frame = json.loads(line[6:])
        if "error" in frame:
            raise RuntimeError(frame["error"])
        print(json.dumps(frame["result"], ensure_ascii=False, indent=2))`
            : `response = requests.post(
    f"{base_url}/flows/api/v1/${flowId}",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=300,
)
response.raise_for_status()
frame = response.json()
if "error" in frame:
    raise RuntimeError(frame["error"])
print(json.dumps(frame["result"], ensure_ascii=False, indent=2))`;
        const asyncPythonSuffix = mode === 'async'
            ? `

poll_payload = ${tasksGetBodyText}
for _ in range(60):
    poll = requests.post(
        f"{base_url}/flows/api/v1/${flowId}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=poll_payload,
        timeout=30,
    )
    poll.raise_for_status()
    task = poll.json()["result"]
    state = task["status"]["state"]
    if state in {"completed", "failed", "input-required"}:
        print(json.dumps(task, ensure_ascii=False, indent=2))
        break`
            : '';
        const jsRequest = mode === 'stream'
            ? `const response = await globalThis["fetch"](\`\${baseUrl}/flows/api/v1/${flowId}\`, {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${token}\`,
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});

if (!response.ok) {
  throw new Error(await response.text());
}

const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += value;
  const lines = buffer.split("\\n");
  buffer = lines.pop();
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const frame = JSON.parse(line.slice(6));
    if (frame.error) throw new Error(JSON.stringify(frame.error));
    console.log(frame.result);
  }
}`
            : `const response = await globalThis["fetch"](\`\${baseUrl}/flows/api/v1/${flowId}\`, {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${token}\`,
    Accept: "application/json",
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});

if (!response.ok) {
  throw new Error(await response.text());
}

const frame = await response.json();
if (frame.error) throw new Error(JSON.stringify(frame.error));
console.log(frame.result);`;
        const asyncJsSuffix = mode === 'async'
            ? `

const pollPayload = ${tasksGetBodyText};
for (let i = 0; i < 60; i += 1) {
  const poll = await globalThis["fetch"](\`\${baseUrl}/flows/api/v1/${flowId}\`, {
    method: "POST",
    headers: {
      Authorization: \`Bearer \${token}\`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(pollPayload),
  });
  if (!poll.ok) throw new Error(await poll.text());
  const task = (await poll.json()).result;
  if (["completed", "failed", "input-required"].includes(task.status.state)) {
    console.log(task);
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}`
            : '';
        return {
            curl:
`BASE_URL=${_shellSingleQuote(baseUrl)}
TOKEN="<your_api_token>"

curl ${mode === 'stream' ? '-N ' : ''}"$BASE_URL/flows/api/v1/${flowId}" \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Accept: ${accept}" \\
  -H "Content-Type: application/json" \\
  --data-raw ${_shellSingleQuote(bodyText)}${asyncCurlSuffix}`,
            python:
`import json
import requests

base_url = "${baseUrl}"
token = "<your_api_token>"
payload = ${bodyText}

${syncPythonTail}${asyncPythonSuffix}`,
            javascript:
`const baseUrl = "${baseUrl}";
const token = "<your_api_token>";
const payload = ${bodyText};

${jsRequest}${asyncJsSuffix}`,
        };
    }

    _currentExample() {
        const examples = this._examples();
        return examples[this._language];
    }

    _currentExampleLanguage() {
        if (this._language === 'python') {
            return 'python';
        }
        if (this._language === 'javascript') {
            return 'javascript';
        }
        return 'text';
    }

    async _copy(text) {
        if (typeof text !== 'string') {
            throw new Error('flows-api-console-modal: copy text required');
        }
        if (text.length === 0) {
            throw new Error('flows-api-console-modal: copy text required');
        }
        await this.copyToClipboard(text, {
            success_i18n_key: 'flows:api_console.copy_success',
            error_i18n_key: 'flows:api_console.copy_error',
        });
    }

    async _runRequest() {
        if (typeof this.flowId !== 'string') {
            throw new Error('flows-api-console-modal: flowId required');
        }
        if (this.flowId.length === 0) {
            throw new Error('flows-api-console-modal: flowId required');
        }
        this._lastError = '';
        this._result = null;
        let body;
        try {
            body = this._requestBody();
        } catch (err) {
            this._lastError = err instanceof Error ? err.message : String(err);
            return;
        }
        try {
            const result = await this._run.run({ flow_id: this.flowId, mode: this._mode, body });
            this._result = result;
            this._resultView = 'response';
        } catch (err) {
            this._lastError = err instanceof Error ? err.message : String(err);
        }
    }

    _resetContext() {
        this._contextId = _sampleContextId(this.flowId, this.branchId);
        this._result = null;
        this._resultView = 'response';
        this._lastError = '';
    }

    renderHeader() {
        return html`${this.t('api_console.title')}`;
    }

    renderHeaderActions() {
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('api_console.copy_body')}
                aria-label=${this.t('api_console.copy_body')}
                @click=${() => this._copy(_jsonPretty(this._sampleBody()))}
            >
                <platform-icon name="copy" size="16"></platform-icon>
            </button>
        `;
    }

    _renderNav() {
        return html`
            <div class="api-nav">
                ${TAB_KEYS.map((key) => html`
                    <button
                        type="button"
                        ?active=${this._activeTab === key}
                        @click=${() => this._setTab(key)}
                    >
                        <platform-icon name=${key === 'run' ? 'play' : key === 'fields' ? 'table' : key === 'examples' ? 'code' : 'book-open'} size="15"></platform-icon>
                        ${this.t(`api_console.tab_${key}`)}
                    </button>
                `)}
            </div>
        `;
    }

    _renderEndpointCard() {
        return html`
            <div class="endpoint-card">
                <div>
                    <div class="endpoint-label">${this.t('api_console.endpoint')}</div>
                    <div class="endpoint-value">${this._endpointPath()}</div>
                </div>
                <div>
                    <div class="endpoint-label">${this.t('api_console.branch')}</div>
                    <div class="endpoint-value">${_apiBranchId(this.branchId)}</div>
                </div>
                <div>
                    <div class="endpoint-label">${this.t('api_console.protocol')}</div>
                    <div class="endpoint-value">JSON-RPC 2.0 / ${_acceptForMode(this._mode)}</div>
                </div>
                <div>
                    <div class="endpoint-label">${this.t('api_console.mode_label')}</div>
                    <div class="endpoint-value">${this.t(`api_console.mode_${this._mode}`)}</div>
                </div>
            </div>
        `;
    }

    _renderModeSelector() {
        return html`
            <div class="mode-tabs" role="tablist" aria-label=${this.t('api_console.mode_tabs_aria')}>
                ${MODE_KEYS.map((mode) => html`
                    <button
                        type="button"
                        role="tab"
                        ?active=${this._mode === mode}
                        @click=${() => this._setMode(mode)}
                    >
                        <platform-icon name=${mode === 'stream' ? 'radio' : mode === 'sync' ? 'send' : 'clock'} size="13"></platform-icon>
                        ${this.t(`api_console.mode_${mode}`)}
                    </button>
                `)}
            </div>
        `;
    }

    _renderModeCards() {
        return html`
            <div class="mode-grid">
                ${MODE_KEYS.map((mode) => html`
                    <div class="mode-card" ?active=${this._mode === mode}>
                        <b>
                            <platform-icon name=${mode === 'stream' ? 'radio' : mode === 'sync' ? 'send' : 'clock'} size="15"></platform-icon>
                            ${this.t(`api_console.mode_${mode}_title`)}
                        </b>
                        <code>${_methodForMode(mode)}${mode === 'async' ? ' + execution_mode=async' : ''}</code>
                        <p>${this.t(`api_console.mode_${mode}_text`)}</p>
                    </div>
                `)}
            </div>
        `;
    }

    _renderHero() {
        const variables = this._variablesEntries();
        return html`
            <div class="hero">
                <h2 class="hero-title">
                    <platform-icon name="api" size="20"></platform-icon>
                    ${this.t('api_console.hero_title')}
                </h2>
                <p class="hero-sub">${this.t('api_console.hero_subtitle')}</p>
                <div class="metric-grid">
                    <div class="metric">
                        <span>${this.t('api_console.metric_flow')}</span>
                        <code>${this.flowId}</code>
                    </div>
                    <div class="metric">
                        <span>${this.t('api_console.metric_branch')}</span>
                        <code>${_apiBranchId(this.branchId)}</code>
                    </div>
                    <div class="metric">
                        <span>${this.t('api_console.metric_context')}</span>
                        <code>${this._contextId}</code>
                    </div>
                    <div class="metric">
                        <span>${this.t('api_console.metric_variables')}</span>
                        <code>${String(variables.length)}</code>
                    </div>
                </div>
                ${this._renderModeSelector()}
            </div>
        `;
    }

    _renderStart() {
        return html`
            ${this._renderHero()}
            <div class="section">
                <h3 class="section-title"><platform-icon name="list" size="16"></platform-icon>${this.t('api_console.quick_title')}</h3>
                <div class="steps">
                    <div class="step">
                        <b>${this.t('api_console.quick_step_1_title')}</b>
                        <p>${this.t('api_console.quick_step_1_text')}</p>
                    </div>
                    <div class="step">
                        <b>${this.t('api_console.quick_step_2_title')}</b>
                        <p>${this.t('api_console.quick_step_2_text')}</p>
                    </div>
                    <div class="step">
                        <b>${this.t('api_console.quick_step_3_title')}</b>
                        <p>${this.t('api_console.quick_step_3_text')}</p>
                    </div>
                </div>
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="split" size="16"></platform-icon>${this.t('api_console.modes_title')}</h3>
                <p class="section-copy">${this.t('api_console.modes_text')}</p>
                ${this._renderModeCards()}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="route" size="16"></platform-icon>${this.t('api_console.methods_title')}</h3>
                ${this._renderRowsTable(
                    [this.t('api_console.col_method'), this.t('api_console.col_why')],
                    METHOD_ROWS.map(([name, key]) => [html`<code>${name}</code>`, this.t(key)]),
                )}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="key" size="16"></platform-icon>${this.t('api_console.auth_title')}</h3>
                <p class="section-copy">${this.t('api_console.auth_text')}</p>
            </div>
        `;
    }

    _renderExamples() {
        const example = this._currentExample();
        const body = this._sampleBody();
        return html`
            ${this._renderHero()}
            <div class="section">
                <div class="code-head">
                    <div class="lang-tabs" role="tablist" aria-label=${this.t('api_console.examples_tabs_aria')}>
                        ${LANG_KEYS.map((lang) => html`
                            <button
                                type="button"
                                role="tab"
                                ?active=${this._language === lang}
                                @click=${() => this._setLanguage(lang)}
                            >${this.t(`api_console.lang_${lang}`)}</button>
                        `)}
                    </div>
                    <button class="copy-btn" type="button" @click=${() => this._copy(example)}>
                        <platform-icon name="copy" size="13"></platform-icon>
                        ${this.t('api_console.copy')}
                    </button>
                </div>
                <flows-code-editor
                    class="api-code-editor"
                    language=${this._currentExampleLanguage()}
                    .value=${example}
                    .readonly=${true}
                    .showToolbar=${false}
                    .fillParent=${true}
                ></flows-code-editor>
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="file-json" size="16"></platform-icon>${this.t('api_console.request_body_title')}</h3>
                <flows-code-editor
                    class="api-json-editor"
                    language="json"
                    .value=${_jsonPretty(body)}
                    .readonly=${true}
                    .showToolbar=${false}
                    .fillParent=${true}
                ></flows-code-editor>
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="file" size="16"></platform-icon>${this.t('api_console.file_example_title')}</h3>
                <p class="section-copy">${this.t('api_console.file_example_text')}</p>
                <flows-code-editor
                    class="api-code-editor short"
                    language="json"
                    .value=${_jsonPretty({
                    kind: 'file',
                    file: {
                        name: 'invoice.pdf',
                        mimeType: 'application/pdf',
                        uri: 'https://example.com/invoice.pdf',
                    },
                })}
                    .readonly=${true}
                    .showToolbar=${false}
                    .fillParent=${true}
                ></flows-code-editor>
            </div>
        `;
    }

    _renderRowsTable(headers, rows) {
        return html`
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>${headers.map((header) => html`<th>${header}</th>`)}</tr>
                    </thead>
                    <tbody>
                        ${rows.map((row) => html`
                            <tr>${row.map((cell) => html`<td>${cell}</td>`)}</tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    _renderFields() {
        const variables = this._variablesEntries();
        return html`
            ${this._renderHero()}
            <div class="section">
                <h3 class="section-title"><platform-icon name="split" size="16"></platform-icon>${this.t('api_console.modes_title')}</h3>
                ${this._renderRowsTable(
                    [this.t('api_console.col_mode'), this.t('api_console.col_method'), this.t('api_console.col_meaning')],
                    MODE_KEYS.map((mode) => [
                        this.t(`api_console.mode_${mode}`),
                        html`<code>${_methodForMode(mode)}${mode === 'async' ? ' + metadata.execution_mode' : ''}</code>`,
                        this.t(`api_console.mode_${mode}_text`),
                    ]),
                )}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="table" size="16"></platform-icon>${this.t('api_console.fields_title')}</h3>
                ${this._renderRowsTable(
                    [this.t('api_console.col_field'), this.t('api_console.col_meaning')],
                    JSON_RPC_FIELD_ROWS.map(([name, key]) => [html`<code>${name}</code>`, this.t(key)]),
                )}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="key" size="16"></platform-icon>${this.t('api_console.variables_title')}</h3>
                <p class="section-copy">${this.t('api_console.variables_text')}</p>
                ${this._renderRowsTable(
                    [this.t('api_console.col_field'), this.t('api_console.col_meaning')],
                    VARIABLE_FIELD_ROWS.map(([name, key]) => [html`<code>${name}</code>`, this.t(key)]),
                )}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="workflow" size="16"></platform-icon>${this.t('api_console.current_variables_title')}</h3>
                ${variables.length === 0
                    ? html`<div class="empty-note">${this.t('api_console.current_variables_empty')}</div>`
                    : this._renderRowsTable(
                        [this.t('api_console.col_key'), this.t('api_console.col_value'), this.t('api_console.col_flags')],
                        variables.map((entry) => [
                            html`<code>${entry.key}</code>`,
                            html`<code>${_visibleVariableValue(entry)}</code>`,
                            html`
                                <div class="pill-row">
                                    ${entry.secret ? html`<span class="pill">${this.t('api_console.flag_secret')}</span>` : nothing}
                                    ${entry.public ? html`<span class="pill" data-tone="accent">${this.t('api_console.flag_public')}</span>` : nothing}
                                    ${entry.title ? html`<span class="pill">${entry.title}</span>` : nothing}
                                </div>
                            `,
                        ]),
                    )}
            </div>
            <div class="section">
                <h3 class="section-title"><platform-icon name="info" size="16"></platform-icon>${this.t('api_console.system_variables_title')}</h3>
                <div class="pill-row">
                    ${SYSTEM_VARIABLE_KEYS.map((key) => html`<span class="pill">${key}</span>`)}
                </div>
                <p class="section-copy">${this.t('api_console.system_variables_text')}</p>
            </div>
        `;
    }

    _renderRunControls() {
        return html`
            <div class="api-panel">
                <div class="api-panel-head">
                    <div class="api-panel-title">
                        <platform-icon name="play" size="15"></platform-icon>
                        <span>${this.t('api_console.run_title')}</span>
                    </div>
                </div>
                <div class="api-panel-body run-form">
                    <div>
                        <div class="run-textarea-label">${this.t('api_console.mode_label')}</div>
                        ${this._renderModeSelector()}
                    </div>
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('api_console.run_context_label')}
                        .value=${this._contextId}
                        @change=${(e) => {
                            this._contextId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        }}
                    ></platform-field>
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('api_console.run_message_label')}
                        .value=${this._messageText}
                        @change=${(e) => {
                            this._messageText = typeof e.detail.value === 'string' ? e.detail.value : '';
                        }}
                    ></platform-field>
                    <div>
                        <div class="run-textarea-label">${this.t('api_console.run_variables_label')}</div>
                        <flows-code-editor
                            class="api-json-editor compact"
                            language="json"
                            .value=${this._variablesText}
                            .readonly=${false}
                            .showToolbar=${false}
                            .fillParent=${true}
                            @change=${(e) => {
                                this._variablesText = typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></flows-code-editor>
                    </div>
                    <div class="run-actions">
                        <button class="ghost-btn" type="button" @click=${() => this._resetContext()}>
                            ${this.t('api_console.reset_context')}
                        </button>
                        <platform-button variant="primary" ?disabled=${this._run.busy} @click=${() => void this._runRequest()}>
                            ${this._run.busy
                                ? html`<glass-spinner size="sm"></glass-spinner>${this.t('api_console.running')}`
                                : html`<platform-icon name="play" size="14"></platform-icon>${this.t('api_console.run')}`}
                        </platform-button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderRequestPreview() {
        const headers = _requestHeadersForMode(this._mode);
        return html`
            <div class="api-panel">
                <div class="api-panel-head">
                    <div class="api-panel-title">
                        <platform-icon name="file-json" size="15"></platform-icon>
                        <span>${this.t('api_console.request_preview_title')}</span>
                    </div>
                    <button class="copy-btn" type="button" @click=${() => this._copy(_jsonPretty(this._sampleBody()))}>
                        <platform-icon name="copy" size="13"></platform-icon>${this.t('api_console.copy')}
                    </button>
                </div>
                <div class="api-panel-body">
                    <div class="request-header-grid">
                        <div class="request-header">
                            <span>${this.t('api_console.request_method')}</span>
                            <code>POST ${this._endpointPath()}</code>
                        </div>
                        <div class="request-header">
                            <span>${this.t('api_console.request_accept')}</span>
                            <code>${headers.Accept}</code>
                        </div>
                        <div class="request-header">
                            <span>${this.t('api_console.request_content_type')}</span>
                            <code>${headers['Content-Type']}</code>
                        </div>
                        <div class="request-header">
                            <span>${this.t('api_console.request_credentials')}</span>
                            <code>same-origin</code>
                        </div>
                    </div>
                    <flows-code-editor
                        class="api-json-editor"
                        language="json"
                        .value=${_jsonPretty(this._sampleBody())}
                        .readonly=${true}
                        .showToolbar=${false}
                        .fillParent=${true}
                    ></flows-code-editor>
                </div>
            </div>
        `;
    }

    _resultTabs(result) {
        if (!result) {
            return ['response'];
        }
        const tabs = ['response', 'headers', 'full'];
        if (_resultStreamEvents(result).length > 0) {
            tabs.splice(1, 0, 'events', 'raw');
        } else {
            tabs.splice(2, 0, 'raw');
        }
        if (_resultPollExchanges(result).length > 0) {
            tabs.push('polls');
        }
        return tabs;
    }

    _resultTabIcon(tab) {
        if (tab === 'headers') {
            return 'list';
        }
        if (tab === 'events') {
            return 'trace-timeline';
        }
        if (tab === 'raw') {
            return 'file-text';
        }
        if (tab === 'polls') {
            return 'refresh';
        }
        if (tab === 'full') {
            return 'trace-json';
        }
        return 'file-json';
    }

    _visibleResultView(result) {
        const tabs = this._resultTabs(result);
        if (tabs.includes(this._resultView)) {
            return this._resultView;
        }
        return tabs[0];
    }

    _renderStatusStrip(result) {
        const response = _resultResponse(result);
        const status = response && typeof response.status === 'number' ? response.status : 0;
        const tone = status >= 200 && status < 300 ? 'ok' : 'error';
        const state = typeof result.terminal_state === 'string' && result.terminal_state.length > 0
            ? result.terminal_state
            : this.t('api_console.value_empty');
        const taskId = typeof result.task_id === 'string' && result.task_id.length > 0
            ? result.task_id
            : this.t('api_console.value_empty');
        const contextId = typeof result.context_id === 'string' && result.context_id.length > 0
            ? result.context_id
            : this.t('api_console.value_empty');
        const contentType = response && typeof response.content_type === 'string' && response.content_type.length > 0
            ? response.content_type
            : this.t('api_console.value_empty');
        return html`
            <div class="status-strip">
                <div class="status-item" data-tone=${tone}>
                    <b>${this.t('api_console.http_status')}</b>
                    <span>${status}</span>
                </div>
                <div class="status-item">
                    <b>${this.t('api_console.content_type')}</b>
                    <code>${contentType}</code>
                </div>
                <div class="status-item">
                    <b>${this.t('api_console.task_id')}</b>
                    <code>${taskId}</code>
                </div>
                <div class="status-item">
                    <b>${this.t('api_console.context_id')}</b>
                    <code>${contextId}</code>
                </div>
                <div class="status-item">
                    <b>${this.t('api_console.a2a_state')}</b>
                    <code>${state}</code>
                </div>
                <div class="status-item">
                    <b>${this.t('api_console.event_count')}</b>
                    <span>${String(_resultStreamEvents(result).length)}</span>
                </div>
            </div>
        `;
    }

    _renderAssistantSummary(result) {
        const responseText = typeof result.response_text === 'string' ? result.response_text.trim() : '';
        const reasoningText = typeof result.reasoning_text === 'string' ? result.reasoning_text.trim() : '';
        return html`
            <div>
                <div class="run-textarea-label">${this.t('api_console.assistant_text_title')}</div>
                ${responseText.length > 0
                    ? html`<div class="assistant-response">${responseText}</div>`
                    : html`<div class="empty-note">${this.t('api_console.result_no_text')}</div>`}
            </div>
            ${reasoningText.length > 0
                ? html`
                    <div>
                        <div class="run-textarea-label">${this.t('api_console.reasoning_text_title')}</div>
                        <div class="assistant-response">${reasoningText}</div>
                    </div>
                `
                : nothing}
        `;
    }

    _renderResultInspector(compact = false) {
        const result = isPlainObject(this._result) ? this._result : null;
        const errorText = typeof this._lastError === 'string' ? this._lastError : '';
        if (errorText.length > 0) {
            return html`
                <div class="api-panel">
                    <div class="api-panel-head">
                        <div class="api-panel-title">
                            <platform-icon name="alert-triangle" size="15"></platform-icon>
                            <span>${this.t('api_console.result_title')}</span>
                        </div>
                    </div>
                    <div class="api-panel-body">
                        <div class="result-box error-box">${errorText}</div>
                    </div>
                </div>
            `;
        }
        if (!result) {
            return html`
                <div class="api-panel">
                    <div class="api-panel-head">
                        <div class="api-panel-title">
                            <platform-icon name="code" size="15"></platform-icon>
                            <span>${this.t('api_console.response_inspector_title')}</span>
                        </div>
                    </div>
                    <div class="api-panel-body">
                        <div class="empty-note">${this.t('api_console.result_empty')}</div>
                    </div>
                </div>
            `;
        }
        const tabs = this._resultTabs(result);
        const view = this._visibleResultView(result);
        const payload = _resultViewPayload(result, view);
        const editorValue = _displayJson(payload);
        const language = view === 'raw' && typeof payload === 'string' ? 'text' : 'json';
        const editorClass = compact ? 'api-json-editor compact' : 'api-json-editor tall';
        return html`
            <div class="api-panel response-inspector">
                <div class="api-panel-head">
                    <div class="api-panel-title">
                        <platform-icon name="code" size="15"></platform-icon>
                        <span>${this.t('api_console.response_inspector_title')}</span>
                    </div>
                    <button class="copy-btn" type="button" @click=${() => this._copy(editorValue)}>
                        <platform-icon name="copy" size="13"></platform-icon>${this.t('api_console.copy')}
                    </button>
                </div>
                <div class="api-panel-body">
                    ${this._renderStatusStrip(result)}
                    ${this._renderAssistantSummary(result)}
                    <div class="response-tabs" role="tablist" aria-label=${this.t('api_console.response_tabs_aria')}>
                        ${tabs.map((tab) => html`
                            <button
                                type="button"
                                role="tab"
                                ?active=${view === tab}
                                @click=${() => this._setResultView(tab)}
                            >
                                <platform-icon name=${this._resultTabIcon(tab)} size="13"></platform-icon>
                                ${this.t(`api_console.result_tab_${tab}`)}
                            </button>
                        `)}
                    </div>
                    <flows-code-editor
                        class=${editorClass}
                        language=${language}
                        .value=${editorValue}
                        .readonly=${true}
                        .showToolbar=${false}
                        .fillParent=${true}
                    ></flows-code-editor>
                </div>
            </div>
        `;
    }

    _renderRunPanelBody() {
        return html`
            ${this._renderRunControls()}
            ${this._renderResultInspector(true)}
        `;
    }

    _renderRun() {
        return html`
            ${this._renderHero()}
            <div class="section">
                <h3 class="section-title"><platform-icon name="play" size="16"></platform-icon>${this.t('api_console.run_title')}</h3>
                <p class="section-copy">${this.t(`api_console.run_text_${this._mode}`)}</p>
            </div>
            <div class="run-workbench">
                <div class="run-column">
                    ${this._renderRunControls()}
                    ${this._renderRequestPreview()}
                </div>
                <div class="run-column">
                    ${this._renderResultInspector(false)}
                </div>
            </div>
        `;
    }

    _renderMain() {
        if (this._activeTab === 'examples') {
            return this._renderExamples();
        }
        if (this._activeTab === 'fields') {
            return this._renderFields();
        }
        if (this._activeTab === 'run') {
            return this._renderRun();
        }
        return this._renderStart();
    }

    _renderLiveAside() {
        if (this._activeTab === 'run') {
            return nothing;
        }
        return html`
            <div class="api-live">
                <div class="section">
                    <h3 class="section-title"><platform-icon name="play" size="16"></platform-icon>${this.t('api_console.live_title')}</h3>
                    <p class="section-copy">${this.t('api_console.live_text')}</p>
                    ${this._renderRunPanelBody()}
                </div>
            </div>
        `;
    }

    renderBody() {
        this._ensureDefaults();
        const shellClass = this._activeTab === 'run' ? 'api-console-shell run-focused' : 'api-console-shell';
        return html`
            <div class=${shellClass}>
                <aside class="api-side">
                    ${this._renderEndpointCard()}
                    ${this._renderNav()}
                </aside>
                <main class="api-main">
                    ${this._renderMain()}
                </main>
                ${this._renderLiveAside()}
            </div>
        `;
    }
}

customElements.define('flows-api-console-modal', FlowsApiConsoleModal);
registerModalKind(FlowsApiConsoleModal.modalKind, 'flows-api-console-modal');

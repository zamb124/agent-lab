import { html, css, nothing } from '../lit-shim.js';
import { unsafeHTML } from '../unsafe-html-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import './chat-run-trace.js';
import '../components/platform-icon.js';
import '../components/platform-work-item-badge.js';
import '../components/platform-help-hint.js';
import '../components/platform-assistant-message-actions.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import {
    pairFlowChatToolCallsAndResults,
    flowChatToolRowDisplayName,
    flowChatToolRowId,
    formatFlowChatToolPairHintText,
    toolCallIconName,
} from './tool-helpers.js';
import { flowsChatMarkdownToHtml } from './markdown.js';
import {
    normalizeFlowChatBlockForPlatformUrls,
    rewritePlatformFileUrlsInHtml,
    CANONICAL_FILES_DOWNLOAD_PREFIX,
} from './flows-url-rewrite.js';
import { registerBuiltinFlowChatBlocks } from './chat-builtin-blocks.js';
import { stopStreamTtsPlayback } from '../voice/stream-tts-registry.js';
import { normalizeChatAuthor } from './chat-author.js';
import './chat-block-renderer.js';

registerBuiltinFlowChatBlocks();

const DEFAULT_LABELS = {
    role_user: 'You',
    role_agent: 'Agent',
    role_subagent: 'Sub-agent',
    role_assistant: 'Assistant',
    role_operator: 'Operator',
    role_system: 'System',
    operator_files: 'Attached files',
    thinking_status: 'Thinking...',
    thinking_aria: 'Show reasoning',
    tool_default_name: 'tool',
    tool_stack_aria: 'Tool calls: {names}',
    tool_hint_tool_name: 'Tool: {name}',
    tool_hint_args_label: 'Arguments:',
    tool_hint_result_label: 'Result:',
    show_tracing_title: 'Open tracing',
    show_logs_title: 'Open logs',
    show_durable_history_title: 'Open execution history',
    interrupt_operator_banner: 'Waiting for an operator. The chat is on hold.',
    interrupt_oauth_banner: 'External service authorization required',
    interrupt_oauth_button: 'Authorize',
    interrupt_oauth_workspace_banner: 'Google Workspace authorization required',
    interrupt_oauth_workspace_question: 'Connect Google Workspace to continue with Docs and Sheets.',
    interrupt_oauth_workspace_button: 'Connect Google Workspace',
    interrupt_handoff_banner: 'Control transferred to another agent',
    operator_reply_heading: 'Operator',
    streaming_placeholder: 'Generating a reply...',
    breakpoint_continue: 'Continue',
    breakpoint_view_state: 'View state',
    download_file: 'Download',
    skill_loaded: 'Skill «{name}»',
    skill_loads_aria: 'Activated skills: {names}',
    skill_load_hint: 'Agent Skill: {id}',
    reflection_results_aria: 'Quality checks: {names}',
    reflection_chip_passed: 'Check passed: {label}',
    reflection_chip_revise: 'Needs revision: {label}',
    reflection_chip_blocked: 'Blocked: {label}',
    reflection_detail_summary: 'Summary',
    reflection_detail_issues: 'Findings',
    reflection_detail_reasons: 'Reasons',
    reflection_expand: 'Show details',
    reflection_collapse: 'Hide details',
};

function asArray(value) {
    return Array.isArray(value) ? value : [];
}

function asString(value) {
    return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function isPlainObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function classNames(flags) {
    return Object.entries(flags)
        .filter(([, enabled]) => Boolean(enabled))
        .map(([name]) => name)
        .join(' ');
}

function formatLabel(template, vars) {
    let out = String(template);
    for (const [key, value] of Object.entries(vars || {})) {
        out = out.replace(new RegExp(`\\{\\{${key}\\}\\}|\\{${key}\\}`, 'g'), String(value));
    }
    return out;
}

export class FlowsChatMessage extends PlatformElement {
    static properties = {
        variant: { type: String, reflect: true },
        role: { type: String },
        author: { type: Object },
        content: { type: String },
        timestamp: { type: String },
        locale: { type: String },
        streaming: { type: Boolean },
        reasoning: { type: String },
        activity: { type: String },
        toolCalls: { type: Array },
        toolResults: { type: Array },
        browserPreviews: { type: Array },
        skillLoads: { type: Array },
        reflectionResults: { type: Array },
        error: { type: String },
        errorI18nKey: { type: String },
        inputRequired: { type: Object },
        handoff: { type: Object },
        handback: { type: Object },
        operatorReply: { type: String },
        breakpoint: { type: Object },
        files: { type: Array },
        filesMeta: { type: Array },
        fileIds: { type: Array },
        blocks: { type: Array },
        taskId: { type: String, attribute: 'task-id' },
        traceTaskId: { type: String, attribute: 'trace-task-id' },
        isLastUserMessage: { type: Boolean, attribute: 'is-last-user-message' },
        runTraceAvailable: { type: Boolean, attribute: 'run-trace-available' },
        runTraceEntries: { type: Array },
        sessionId: { type: String, attribute: 'session-id' },
        labels: { type: Object },
        flowRoot: { type: String, attribute: 'flow-root' },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        getHeaders: { attribute: false },
        showAvatar: { type: Boolean, attribute: 'show-avatar' },
        showHeader: { type: Boolean, attribute: 'show-header' },
        headerCompact: { type: Boolean, attribute: 'header-compact', reflect: true },
        showTraceControls: { type: Boolean, attribute: 'show-trace-controls' },
        showRunTraceControls: { type: Boolean, attribute: 'show-run-trace-controls' },
        showLogsAction: { type: Boolean, attribute: 'show-logs-action' },
        showDurableHistoryAction: { type: Boolean, attribute: 'show-durable-history-action' },
        showUserActions: { type: Boolean, attribute: 'show-user-actions' },
        showAssistantActions: { type: Boolean, attribute: 'show-assistant-actions' },
        _runTracePanelOpen: { type: Boolean, state: true },
    };

    static styles = css`
        :host {
            display: block;
            color: var(--flows-chat-text, var(--text-primary, rgba(17, 24, 39, 0.92)));
            font-family: var(--flows-chat-font-family, inherit);
            --flows-chat-radius: var(--radius-xl, 16px);
            --flows-chat-radius-sm: var(--radius-sm, 4px);
            --flows-chat-surface: var(--glass-solid-medium, rgba(255, 255, 255, 0.76));
            --flows-chat-surface-subtle: var(--glass-solid-subtle, rgba(255, 255, 255, 0.52));
            --flows-chat-border: var(--glass-border-subtle, rgba(148, 163, 184, 0.22));
            --flows-chat-shadow: var(--glass-shadow-subtle, 0 8px 28px rgba(15, 23, 42, 0.08));
            --flows-chat-muted: var(--text-tertiary, rgba(100, 116, 139, 0.72));
            --flows-chat-secondary: var(--text-secondary, rgba(51, 65, 85, 0.86));
            --flows-chat-accent: var(--accent, #6474f6);
            --flows-chat-accent-muted: rgba(100, 116, 246, 0.16);
            --flows-chat-danger: var(--error, #ef4444);
            --flows-chat-danger-bg: var(--error-bg, rgba(239, 68, 68, 0.1));
            --flows-chat-danger-border: var(--error-border, rgba(239, 68, 68, 0.35));
            --flows-chat-info-bg: var(--info-bg, rgba(59, 130, 246, 0.1));
            --flows-chat-info-border: var(--info-border, rgba(59, 130, 246, 0.24));
            --flows-chat-warning: var(--warning, #f59e0b);
            --flows-chat-warning-bg: var(--warning-bg, rgba(245, 158, 11, 0.1));
            --flows-chat-warning-border: var(--warning-border, rgba(245, 158, 11, 0.28));
            --flows-chat-on-accent: var(--platform-chat-on-accent, #ffffff);
            --flows-chat-user-fg: var(--flows-chat-on-accent, #ffffff);
            --flows-chat-user-fg-muted: color-mix(in srgb, var(--flows-chat-user-fg) 78%, transparent);
        }

        :host([variant='embed']) {
            --flows-chat-user-fg: var(--flows-chat-text);
            --flows-chat-user-fg-muted: var(--flows-chat-muted);
        }

        .message {
            display: flex;
            gap: 16px;
            min-width: 0;
            animation: message-enter 180ms ease-out;
        }

        .message.user {
            flex-direction: row-reverse;
        }

        .avatar {
            flex-shrink: 0;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: var(--flows-chat-radius);
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface);
            color: var(--flows-chat-accent);
            box-shadow: var(--flows-chat-shadow);
        }

        .message.user .avatar {
            background: var(--flows-chat-accent);
            border: none;
            color: white;
        }

        .message.operator .avatar {
            color: var(--flows-chat-warning);
        }

        .message.system .avatar {
            background: var(--flows-chat-info-bg);
            color: var(--flows-chat-accent);
        }

        .bubble {
            flex: 1;
            max-width: 70%;
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }

        .message.user .bubble {
            flex: 0 0 auto;
            width: max-content;
            max-width: 70%;
            min-width: min-content;
            align-items: flex-end;
        }

        .content {
            position: relative;
            box-sizing: border-box;
            width: 100%;
            min-width: 0;
            padding: 16px 20px;
            border-radius: var(--flows-chat-radius);
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface);
            box-shadow: var(--flows-chat-shadow);
        }

        .message.user .content {
            width: auto;
            max-width: 100%;
            background: var(--flows-chat-accent);
            color: var(--flows-chat-user-fg);
            border: none;
            border-bottom-right-radius: var(--flows-chat-radius-sm);
        }

        .message.assistant .content,
        .message.operator .content {
            border-bottom-left-radius: var(--flows-chat-radius-sm);
        }

        .message.system .content {
            background: var(--flows-chat-info-bg);
            border-color: var(--flows-chat-info-border);
        }

        .header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            min-width: 0;
        }

        .bubble-meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 8px;
            min-width: 0;
            width: 100%;
            box-sizing: border-box;
        }

        .bubble-meta.user-meta {
            justify-content: flex-end;
        }

        .author-identity {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            min-width: 0;
            max-width: min(100%, 320px);
        }

        .author-mark {
            width: 22px;
            height: 22px;
            flex: 0 0 22px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            color: var(--flows-chat-accent);
            background: var(--flows-chat-accent-muted);
            border: 1px solid color-mix(in srgb, var(--flows-chat-accent) 22%, transparent);
        }

        .author-identity[data-author-kind='subagent'] .author-mark {
            color: var(--info, #3b82f6);
            background: var(--info-bg, rgba(59, 130, 246, 0.12));
            border-color: var(--info-border, rgba(59, 130, 246, 0.24));
        }

        .author-identity[data-author-kind='operator'] .author-mark {
            color: var(--flows-chat-warning);
            background: color-mix(in srgb, var(--flows-chat-warning) 12%, transparent);
            border-color: color-mix(in srgb, var(--flows-chat-warning) 26%, transparent);
        }

        .author-identity[data-author-kind='user'] .author-mark {
            color: var(--flows-chat-user-fg);
            background: rgba(255, 255, 255, 0.16);
            border-color: rgba(255, 255, 255, 0.28);
        }

        .author-name {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: var(--flows-chat-secondary);
            font-size: 12px;
            line-height: 1.2;
            font-weight: var(--font-semibold, 600);
        }

        .author-kind {
            flex: 0 0 auto;
            padding: 2px 6px;
            border-radius: var(--radius-full, 999px);
            color: var(--flows-chat-muted);
            background: var(--flows-chat-surface-subtle);
            border: 1px solid var(--flows-chat-border);
            font-size: 10px;
            line-height: 1.2;
            font-weight: var(--font-medium, 500);
        }

        .message.user .author-name,
        .message.user .author-kind {
            color: var(--flows-chat-user-fg);
        }

        .message.user .author-kind {
            background: rgba(255, 255, 255, 0.12);
            border-color: rgba(255, 255, 255, 0.24);
        }

        .bubble-meta.assistant-meta {
            position: relative;
            align-items: center;
            flex-wrap: nowrap;
            min-height: 24px;
        }

        .bubble-meta.assistant-meta:has(.bubble-observability-actions) {
            padding-right: 84px;
        }

        .bubble-observability-actions,
        .bubble-meta .header-actions {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            flex-shrink: 0;
            margin-left: auto;
        }

        :host([header-compact]) .bubble-meta.assistant-meta .bubble-observability-actions {
            position: absolute;
            top: 0;
            right: 0;
            margin-left: 0;
        }

        :host([header-compact]) .timestamp {
            font-size: 11px;
            line-height: 1.2;
            white-space: nowrap;
            flex-shrink: 0;
        }

        :host([header-compact]) .message.user .bubble-meta .timestamp {
            color: var(--flows-chat-user-fg-muted);
        }

        :host([header-compact]) .bubble-meta {
            margin-bottom: 6px;
        }

        :host([variant='embed']) .timestamp {
            font-size: 11px;
        }

        .message.user .header {
            justify-content: flex-end;
        }

        .header.has-inline-tools {
            justify-content: space-between;
            width: 100%;
        }

        .user-header-meta {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: 8px;
            min-width: 0;
        }

        .role {
            font-size: 14px;
            font-weight: 600;
            color: var(--flows-chat-secondary);
        }

        .message.user .role,
        .message.user .timestamp {
            color: var(--flows-chat-user-fg-muted);
        }

        .timestamp {
            font-size: 12px;
            color: var(--flows-chat-muted);
        }

        .header-actions,
        .assistant-actions,
        .user-actions,
        .breakpoint-actions {
            display: flex;
            gap: 8px;
        }

        .header-actions {
            margin-left: auto;
        }

        .tracing-btn,
        .breakpoint-actions button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface-subtle);
            color: var(--flows-chat-muted);
            cursor: pointer;
            font: inherit;
        }

        .tracing-btn {
            width: 24px;
            height: 24px;
            padding: 0;
            border-radius: 6px;
        }

        .tracing-btn:hover,
        .tracing-btn[aria-pressed='true'] {
            color: var(--flows-chat-accent);
            border-color: var(--flows-chat-accent);
        }

        .message.user .tracing-btn {
            background: rgba(255, 255, 255, 0.2);
            border-color: rgba(255, 255, 255, 0.36);
            color: white;
        }

        .text,
        .markdown {
            font-size: 15px;
            line-height: 1.58;
            color: var(--flows-chat-text);
            word-break: break-word;
        }

        .message.user .text,
        .message.user .markdown {
            color: var(--flows-chat-user-fg);
            white-space: pre-wrap;
            word-break: normal;
            overflow-wrap: break-word;
        }

        .markdown p {
            margin: 0 0 12px;
        }

        .markdown p:last-child {
            margin-bottom: 0;
        }

        .markdown code {
            font-family: var(--font-mono);
            font-size: 0.875em;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(0, 0, 0, 0.12);
        }

        .markdown pre {
            margin: 14px 0;
            padding: 14px;
            overflow-x: auto;
            border-radius: 8px;
            border: 1px solid var(--flows-chat-border);
            background: rgba(15, 23, 42, 0.08);
        }

        .markdown pre code {
            padding: 0;
            background: none;
        }

        .markdown table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        .markdown th,
        .markdown td {
            border: 1px solid var(--flows-chat-border);
            padding: 8px 10px;
            text-align: left;
        }

        .markdown a {
            color: var(--flows-chat-accent);
        }

        .streaming .markdown.has-content::after {
            content: '|';
            color: var(--flows-chat-accent);
            animation: blink 1s infinite;
            margin-left: 2px;
        }

        .stream-pending,
        .activity-line,
        .thinking-row-compact {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: var(--flows-chat-secondary);
        }

        .activity-line {
            align-items: flex-start;
            margin-bottom: 12px;
            padding: 8px 10px;
            background: var(--flows-chat-surface-subtle);
            border: 1px solid var(--flows-chat-border);
            border-radius: 10px;
        }

        .skill-loads {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 10px;
        }

        .skill-load-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface-subtle);
            color: var(--flows-chat-secondary);
            font-size: 12px;
            line-height: 1.3;
        }

        .skill-load-chip-inner {
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .skill-load-chip platform-icon {
            color: var(--flows-chat-accent);
        }

        .reflection-results {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 10px;
        }

        .reflection-card {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 0;
            align-items: flex-start;
        }

        .reflection-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            max-width: 100%;
            padding: 5px 12px;
            border-radius: 999px;
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface-subtle);
            color: var(--flows-chat-secondary);
            font-size: 12px;
            font-weight: 500;
            line-height: 1.3;
            cursor: pointer;
        }

        .reflection-chip[data-tone="success"] {
            color: var(--success);
            border-color: color-mix(in oklab, var(--success) 35%, var(--flows-chat-border));
            background: color-mix(in oklab, var(--success) 12%, var(--flows-chat-surface-subtle));
        }

        .reflection-chip[data-tone="warning"] {
            color: var(--warning);
            border-color: color-mix(in oklab, var(--warning) 35%, var(--flows-chat-border));
            background: color-mix(in oklab, var(--warning) 12%, var(--flows-chat-surface-subtle));
        }

        .reflection-chip[data-tone="error"] {
            color: var(--error);
            border-color: color-mix(in oklab, var(--error) 35%, var(--flows-chat-border));
            background: color-mix(in oklab, var(--error) 12%, var(--flows-chat-surface-subtle));
        }

        .reflection-chip-inner {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            min-width: 0;
        }

        .reflection-chip-label {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .reflection-detail {
            display: flex;
            flex-direction: column;
            gap: 8px;
            width: 100%;
            max-width: 28rem;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid var(--flows-chat-border);
            background: var(--flows-chat-surface-subtle);
        }

        .reflection-detail-title {
            margin: 0;
            font-size: 11px;
            font-weight: 600;
            color: var(--flows-chat-tertiary, var(--flows-chat-secondary));
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .reflection-detail-body {
            margin: 0;
            font-size: 13px;
            color: var(--flows-chat-secondary);
            line-height: 1.45;
        }

        .reflection-issues {
            display: flex;
            flex-direction: column;
            gap: 6px;
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .reflection-issue {
            display: flex;
            flex-direction: column;
            gap: 2px;
            padding: 6px 8px;
            border-radius: 8px;
            background: color-mix(in oklab, var(--flows-chat-surface, #fff) 70%, transparent);
        }

        .reflection-issue-meta {
            font-size: 11px;
            font-weight: 600;
            color: var(--flows-chat-tertiary, var(--flows-chat-secondary));
        }

        .reflection-issue-finding {
            font-size: 13px;
            color: var(--flows-chat-secondary);
            line-height: 1.4;
        }

        .thinking-row-compact {
            display: inline-flex;
            margin-top: 12px;
        }

        .thinking-live {
            color: var(--flows-chat-accent);
        }

        .stream-pending {
            min-height: 24px;
            color: var(--flows-chat-muted);
        }

        .stream-placeholder-shimmer {
            flex: 1;
            min-width: 120px;
            max-width: 220px;
            height: 10px;
            border-radius: 999px;
            background: linear-gradient(90deg, transparent 0%, var(--flows-chat-surface-subtle) 50%, transparent 100%);
            background-size: 200% 100%;
            animation: stream-shimmer 1.4s ease-in-out infinite;
        }

        .tool-stack {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            margin-top: 12px;
        }

        .tool-orb {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            margin-left: -10px;
            border-radius: 50%;
            background: var(--flows-chat-surface-subtle);
            border: 1px solid var(--flows-chat-border);
            box-shadow: var(--flows-chat-shadow);
        }

        .tool-orb:first-child {
            margin-left: 0;
        }

        .tool-orb-inner,
        .tool-orb platform-help-hint {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
        }

        .tool-orb-button {
            appearance: none;
            position: relative;
            border: 0;
            padding: 0;
            margin: 0;
            background: transparent;
            color: inherit;
            cursor: pointer;
            border-radius: 50%;
        }

        .tool-orb.browser-preview {
            border-color: var(--flows-chat-accent);
            background: var(--flows-chat-accent-muted);
        }

        .browser-preview-dot {
            position: absolute;
            top: -3px;
            right: -3px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--success, #22c55e);
            border: 2px solid var(--flows-chat-surface);
            box-sizing: border-box;
            pointer-events: none;
        }

        .browser-closed .browser-preview-dot {
            background: var(--flows-chat-muted);
        }

        .chat-line-error,
        .input-required,
        .operator-reply,
        .breakpoint,
        .user-run-trace-embed {
            margin-top: 14px;
            padding: 14px;
            border-radius: 10px;
            border: 1px solid var(--flows-chat-border);
        }

        .chat-line-error {
            color: var(--flows-chat-danger);
            background: var(--flows-chat-danger-bg);
            border-color: var(--flows-chat-danger-border);
        }

        .input-required {
            background: var(--flows-chat-info-bg);
            border-color: var(--flows-chat-info-border);
        }

        .input-required-banner,
        .operator-reply-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--flows-chat-muted);
            margin-bottom: 8px;
        }

        .oauth-auth-link {
            display: inline-flex;
            align-items: center;
            margin-top: 10px;
            padding: 8px 12px;
            border-radius: 8px;
            background: var(--flows-chat-accent);
            color: white;
            text-decoration: none;
            font-size: 14px;
            font-weight: 600;
        }

        .operator-reply {
            background: var(--flows-chat-surface-subtle);
        }

        .breakpoint {
            background: var(--flows-chat-warning-bg);
            border-color: var(--flows-chat-warning-border);
        }

        .breakpoint-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
        }

        .breakpoint-icon {
            width: 10px;
            height: 10px;
            flex-shrink: 0;
            border-radius: 50%;
            background: var(--flows-chat-warning);
        }

        .breakpoint-title {
            font-size: 15px;
            font-weight: 600;
            color: var(--flows-chat-warning);
        }

        .breakpoint-message {
            font-size: 14px;
            margin-bottom: 10px;
        }

        .breakpoint-actions button {
            min-height: 32px;
            padding: 0 12px;
            border-radius: 8px;
        }

        .files-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }

        .file-item {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
            max-width: 100%;
            padding: 4px 0;
            border: 0;
            background: transparent;
            font-size: 14px;
            text-decoration: none;
            color: inherit;
            cursor: pointer;
            font-family: inherit;
            text-align: left;
        }

        .file-item:hover .file-name {
            color: var(--flows-chat-accent);
            text-decoration: underline;
            text-underline-offset: 2px;
        }

        .file-name {
            color: var(--flows-chat-text);
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .message.user .file-name {
            color: var(--flows-chat-user-fg);
        }

        .file-size {
            color: var(--flows-chat-muted);
            font-size: 12px;
        }

        .assistant-actions,
        .user-actions {
            flex-shrink: 0;
            margin-top: 8px;
            padding-left: 4px;
        }

        .message.user .assistant-actions,
        .message.user .user-actions {
            width: 100%;
            justify-content: flex-end;
            padding-left: 0;
        }

        .blocks {
            display: grid;
            gap: 10px;
            margin-top: 12px;
        }

        :host([variant='embed']) .message {
            gap: 0;
        }

        :host([variant='embed']) .avatar.hidden,
        .avatar.hidden,
        .header.hidden {
            display: none;
        }

        :host([variant='embed']) .bubble {
            max-width: 100%;
        }

        :host([variant='embed']) .message.user .bubble {
            max-width: 86%;
            min-width: min-content;
            margin-left: auto;
        }

        :host([variant='embed']) .content {
            padding: 10px 12px;
            border-radius: var(--flows-chat-radius, 18px);
            background: var(--flows-chat-surface, rgba(255, 255, 255, 0.08));
            border-color: var(--flows-chat-border, rgba(255, 255, 255, 0.12));
            box-shadow: none;
        }

        :host([variant='embed']) .message.user .content {
            background: var(--flows-chat-accent-muted, rgba(153, 166, 249, 0.2));
            color: var(--flows-chat-user-fg);
            border: 1px solid var(--flows-chat-border, rgba(255, 255, 255, 0.12));
        }

        :host([variant='embed']) .message.user .markdown,
        :host([variant='embed']) .message.user .text {
            color: var(--flows-chat-user-fg);
        }

        :host([variant='embed']) .assistant-actions,
        :host([variant='embed']) .user-actions {
            margin-top: 4px;
            opacity: 0.72;
        }

        @media (max-width: 767px) {
            .message {
                display: block;
                position: relative;
            }

            .avatar {
                position: absolute;
                top: 8px;
                width: 28px;
                height: 28px;
                z-index: 2;
            }

            .message.user .avatar {
                right: 8px;
            }

            .message.assistant .avatar,
            .message.operator .avatar,
            .message.system .avatar {
                left: 8px;
            }

            .bubble,
            .message.user .bubble {
                max-width: 100%;
                width: 100%;
            }

            .message.user .content {
                padding-right: 40px;
            }

            .message.assistant .content,
            .message.operator .content,
            .message.system .content {
                padding-left: 40px;
            }

            :host([variant='embed']) .message.user .bubble {
                width: max-content;
                max-width: 92%;
                min-width: min-content;
            }

            :host([variant='embed']) .message.user .content,
            :host([variant='embed']) .message.assistant .content,
            :host([variant='embed']) .message.operator .content,
            :host([variant='embed']) .message.system .content {
                padding: 10px 12px;
            }
        }

        @keyframes message-enter {
            from {
                opacity: 0;
                transform: translateY(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes blink {
            50% {
                opacity: 0;
            }
        }

        @keyframes stream-shimmer {
            0% {
                background-position: 100% 0;
            }
            100% {
                background-position: -100% 0;
            }
        }
    `;

    constructor() {
        super();
        this.variant = 'app';
        this.role = 'user';
        this.author = null;
        this.content = '';
        this.timestamp = '';
        this.locale = 'en';
        this.streaming = false;
        this.reasoning = '';
        this.activity = '';
        this.toolCalls = [];
        this.toolResults = [];
        this.browserPreviews = [];
        this.skillLoads = [];
        this.reflectionResults = [];
        this._reflectionExpanded = {};
        this.error = '';
        this.errorI18nKey = '';
        this.inputRequired = null;
        this.handoff = null;
        this.handback = null;
        this.operatorReply = '';
        this.breakpoint = null;
        this.files = [];
        this.filesMeta = [];
        this.fileIds = [];
        this.blocks = [];
        this.taskId = '';
        this.traceTaskId = '';
        this.isLastUserMessage = false;
        this.runTraceAvailable = false;
        this.runTraceEntries = [];
        this.sessionId = '';
        this.labels = {};
        this.flowRoot = '';
        this.useCredentials = true;
        this.voiceBaseUrl = '';
        this.getHeaders = null;
        this.showAvatar = true;
        this.showHeader = true;
        this.headerCompact = false;
        this.showTraceControls = true;
        this.showRunTraceControls = false;
        this.showLogsAction = false;
        this.showDurableHistoryAction = false;
        this.showUserActions = true;
        this.showAssistantActions = true;
        this._runTracePanelOpen = false;
    }

    willUpdate(changed) {
        if (changed.has('isLastUserMessage') && !this.isLastUserMessage) {
            this._runTracePanelOpen = false;
        }
    }

    _label(key, fallback = '', vars = null) {
        const labels = this.labels && typeof this.labels === 'object' ? this.labels : {};
        const value = typeof labels[key] === 'string' && labels[key].trim() !== ''
            ? labels[key]
            : DEFAULT_LABELS[key] || fallback;
        return formatLabel(value, vars || {});
    }

    _formatTimestamp(iso) {
        const raw = asString(iso);
        if (raw.length === 0) {
            return '';
        }
        const ms = Date.parse(raw);
        if (Number.isNaN(ms)) {
            return raw;
        }
        return new Intl.DateTimeFormat(this.locale || 'en', {
            dateStyle: 'short',
            timeStyle: 'short',
        }).format(new Date(ms));
    }

    _resolvedAuthor() {
        return normalizeChatAuthor(this.author, this.role);
    }

    _authorKindName() {
        const author = this._resolvedAuthor();
        switch (author.kind) {
            case 'user':
                return this._label('role_user', 'You');
            case 'agent':
                return this._label('role_agent', this._label('role_assistant', 'Agent'));
            case 'subagent':
                return this._label('role_subagent', 'Sub-agent');
            case 'operator':
                return this._label('role_operator', 'Operator');
            case 'system':
                return this._label('role_system', 'System');
            default:
                return '';
        }
    }

    _authorDisplayName() {
        const author = this._resolvedAuthor();
        return author.name || this._authorKindName();
    }

    _authorIdentityIcon() {
        switch (this._resolvedAuthor().kind) {
            case 'user':
                return 'user';
            case 'agent':
                return 'bot';
            case 'subagent':
                return 'workflow';
            case 'operator':
                return 'agent';
            case 'system':
                return 'info';
            default:
                return 'chat';
        }
    }

    _renderAuthorIdentity() {
        const author = this._resolvedAuthor();
        const name = this._authorDisplayName();
        const kindName = this._authorKindName();
        const showKind = author.name.length > 0 && author.name !== kindName;
        return html`
            <span class="author-identity" data-author-kind=${author.kind} title=${kindName}>
                <span class="author-mark" aria-hidden="true">
                    <platform-icon name=${this._authorIdentityIcon()} size="13"></platform-icon>
                </span>
                <span class="author-name">${name}</span>
                ${showKind ? html`<span class="author-kind">${kindName}</span>` : nothing}
            </span>
        `;
    }

    _avatarIcon() {
        if (this.role !== 'handoff' && this.role !== 'handback') {
            return this._authorIdentityIcon();
        }
        switch (this.role) {
            case 'user':
                return 'user';
            case 'assistant':
                return 'bot';
            case 'operator':
                return 'agent';
            case 'system':
                return 'info';
            case 'handoff':
                return 'agent';
            case 'handback':
                return 'undo';
            default:
                return 'chat';
        }
    }

    _flowRoot() {
        return asString(this.flowRoot).replace(/\/+$/, '');
    }

    _downloadUrl(fileId) {
        const fid = asString(fileId);
        if (fid.length === 0) {
            return '';
        }
        return `${CANONICAL_FILES_DOWNLOAD_PREFIX}/${encodeURIComponent(fid)}`;
    }

    _markdownTemplate(text, opts = {}) {
        const htmlText = rewritePlatformFileUrlsInHtml(
            flowsChatMarkdownToHtml(asString(text), opts),
        );
        return unsafeHTML(htmlText);
    }

    _streamPendingSuppressed() {
        if (this.role !== 'assistant') {
            return false;
        }
        return (
            asString(this.activity).length > 0 ||
            asString(this.reasoning).length > 0 ||
            asArray(this.toolCalls).length > 0 ||
            asArray(this.toolResults).length > 0 ||
            asArray(this.browserPreviews).length > 0 ||
            asArray(this.skillLoads).length > 0 ||
            asArray(this.reflectionResults).length > 0 ||
            asArray(this.files).length > 0 ||
            asArray(this.blocks).length > 0
        );
    }

    _browserPreviewForToolRow(call, result) {
        const previews = asArray(this.browserPreviews);
        if (previews.length === 0) {
            return null;
        }
        const rowId = flowChatToolRowId(call, result);
        const displayName = flowChatToolRowDisplayName(call, result, this._label('tool_default_name', 'tool'));
        const candidates = previews.filter((preview) => {
            if (!isPlainObject(preview)) return false;
            const previewToolCallId =
                typeof preview.parentToolCallId === 'string' && preview.parentToolCallId.length > 0
                    ? preview.parentToolCallId
                    : typeof preview.toolCallId === 'string'
                      ? preview.toolCallId
                      : '';
            if (rowId.length > 0 && previewToolCallId === rowId) {
                return true;
            }
            return (
                typeof preview.topLevelToolName === 'string' &&
                preview.topLevelToolName.length > 0 &&
                preview.topLevelToolName === displayName
            );
        });
        return candidates.length > 0 ? candidates[candidates.length - 1] : null;
    }

    _browserPreviewHint(preview, fallback) {
        const status = isPlainObject(preview) ? asString(preview.status) : '';
        const parts = [
            status === 'closed' ? 'Browser preview is closed' : 'Click to open browser preview',
            'Watch the live browser window for this tool.',
            '',
        ];
        if (isPlainObject(preview)) {
            const url = asString(preview.currentUrl);
            if (status.length > 0) {
                parts.push(`Status: ${status}`);
            }
            if (url.length > 0) {
                parts.push(url);
            }
        }
        if (fallback.length > 0) {
            parts.push('', 'Tool details:', fallback);
        }
        return parts.join('\n');
    }

    _openBrowserPreview(preview, event) {
        event?.stopPropagation?.();
        if (!isPlainObject(preview)) {
            return;
        }
        const url = asString(preview.viewerUrl);
        if (url.length === 0) {
            return;
        }
        const sessionId = asString(preview.sessionId).replace(/[^a-zA-Z0-9_-]/g, '_') || 'browser';
        const openEvent = new CustomEvent('browser-preview-open', {
            detail: {
                preview,
                viewerUrl: url,
                sessionId,
                currentUrl: asString(preview.currentUrl),
                status: asString(preview.status),
            },
            bubbles: true,
            composed: true,
            cancelable: true,
        });
        this.dispatchEvent(openEvent);
        if (openEvent.defaultPrevented) {
            return;
        }
        const opened = globalThis.window?.open?.(
            url,
            `browser_preview_${sessionId}`,
            'popup=yes,width=1240,height=860,menubar=no,toolbar=no,location=no,status=no,scrollbars=yes,resizable=yes',
        );
        if (!opened && globalThis.window?.location) {
            globalThis.window.location.assign(url);
        }
    }

    _renderToolOrbs() {
        const skillLoads = asArray(this.skillLoads);
        const hideLoadAgentSkill = skillLoads.length > 0;
        const rows = pairFlowChatToolCallsAndResults(this.toolCalls, this.toolResults).filter((row) => {
            if (!hideLoadAgentSkill) {
                return true;
            }
            const name = flowChatToolRowDisplayName(row.call, row.result, '');
            return name !== 'load_agent_skill';
        });
        if (rows.length === 0) {
            return nothing;
        }
        const defaultName = this._label('tool_default_name', 'tool');
        const hintStrings = {
            tool_hint_tool_name: (name) => this._label('tool_hint_tool_name', 'Tool: {name}', { name }),
            tool_hint_args_label: this._label('tool_hint_args_label', 'Arguments:'),
            tool_hint_result_label: this._label('tool_hint_result_label', 'Result:'),
        };
        const names = rows.map((row) => flowChatToolRowDisplayName(row.call, row.result, defaultName)).join(', ');
        return html`
            <div class="tool-stack" role="group" aria-label=${this._label('tool_stack_aria', 'Tool calls: {names}', { names })}>
                ${rows.map((row, index) => {
                    const name = flowChatToolRowDisplayName(row.call, row.result, defaultName);
                    const preview = this._browserPreviewForToolRow(row.call, row.result);
                    const baseHint = formatFlowChatToolPairHintText(row.call, row.result, hintStrings, defaultName);
                    const hint = preview ? this._browserPreviewHint(preview, baseHint) : baseHint;
                    const closed = isPlainObject(preview) && preview.status === 'closed';
                    return html`
                        <span
                            class=${classNames({
                                'tool-orb': true,
                                'browser-preview': Boolean(preview),
                                'browser-closed': closed,
                            })}
                            style="z-index: ${index + 1};"
                        >
                            <platform-help-hint fill .text=${hint} .label=${preview ? 'Click to open browser preview' : name} ?wide=${true}>
                                ${preview
                                    ? html`
                                          <button
                                              type="button"
                                              class="tool-orb-inner tool-orb-button"
                                              aria-label=${`Click to open browser preview: ${name}`}
                                              title="Click to open browser preview"
                                              @click=${(event) => this._openBrowserPreview(preview, event)}
                                          >
                                              <platform-icon name=${toolCallIconName(name)} size="16"></platform-icon>
                                              <span class="browser-preview-dot" aria-hidden="true"></span>
                                          </button>
                                      `
                                    : html`
                                          <span class="tool-orb-inner" tabindex="0" role="img" aria-label=${name}>
                                              <platform-icon name=${toolCallIconName(name)} size="16"></platform-icon>
                                          </span>
                                      `}
                            </platform-help-hint>
                        </span>
                    `;
                })}
            </div>
        `;
    }

    _renderReasoning() {
        const plain = asString(this.reasoning);
        if (plain.length === 0) {
            return nothing;
        }
        return html`
            <div class=${classNames({ 'thinking-row-compact': true, 'thinking-live': this.role === 'assistant' && this.streaming })}>
                <platform-help-hint .text=${plain} .label=${this._label('thinking_aria', 'Show reasoning')} ?wide=${true}>
                    <span class="tool-orb-inner" tabindex="0">
                        <platform-icon name="message-circle" size="16"></platform-icon>
                        <span>${this._label('thinking_status', 'Thinking...')}</span>
                    </span>
                </platform-help-hint>
            </div>
        `;
    }

    _renderActivity() {
        const value = asString(this.activity);
        if (this.role !== 'assistant' || value.length === 0) {
            return nothing;
        }
        return html`
            <div class="activity-line">
                <platform-icon name="search" size="16"></platform-icon>
                <span>${value}</span>
            </div>
        `;
    }

    _renderSkillLoads() {
        const loads = asArray(this.skillLoads).filter((row) => isPlainObject(row));
        if (this.role !== 'assistant' || loads.length === 0) {
            return nothing;
        }
        const names = loads
            .map((row) => asString(row.name || row.agentSkillId))
            .filter((name) => name.length > 0)
            .join(', ');
        return html`
            <div
                class="skill-loads"
                role="group"
                aria-label=${this._label('skill_loads_aria', 'Activated skills: {names}', { names })}
            >
                ${loads.map((row) => {
                    const skillId = asString(row.agentSkillId);
                    const name = asString(row.name || skillId);
                    const hint = this._label('skill_load_hint', 'Agent Skill: {id}', { id: skillId || name });
                    const label = this._label('skill_loaded', 'Skill «{name}»', { name });
                    return html`
                        <span class="skill-load-chip">
                            <platform-help-hint .text=${hint} .label=${label}>
                                <span class="skill-load-chip-inner">
                                    <platform-icon name="sparkles" size="14"></platform-icon>
                                    <span>${label}</span>
                                </span>
                            </platform-help-hint>
                        </span>
                    `;
                })}
            </div>
        `;
    }

    _reflectionTone(row) {
        if (row && row.approved === true) {
            return 'success';
        }
        if (row && asString(row.decision) === 'needs_revision') {
            return 'warning';
        }
        return 'error';
    }

    _reflectionChipKey(row) {
        return `${asString(row.nodeId)}:${asString(row.exitId)}`;
    }

    _reflectionIsExpanded(row) {
        const key = this._reflectionChipKey(row);
        if (Object.hasOwn(this._reflectionExpanded, key)) {
            return this._reflectionExpanded[key] === true;
        }
        return row.approved !== true;
    }

    _toggleReflectionExpanded(row) {
        const key = this._reflectionChipKey(row);
        const nextOpen = !this._reflectionIsExpanded(row);
        this._reflectionExpanded = { ...this._reflectionExpanded, [key]: nextOpen };
        this.requestUpdate();
    }

    _renderReflectionResults() {
        const rows = asArray(this.reflectionResults).filter((row) => isPlainObject(row));
        if (this.role !== 'assistant' || rows.length === 0) {
            return nothing;
        }
        const names = rows
            .map((row) => asString(row.exitLabel || row.exitId))
            .filter((name) => name.length > 0)
            .join(', ');
        return html`
            <div
                class="reflection-results"
                role="group"
                aria-label=${this._label('reflection_results_aria', 'Quality checks: {names}', { names })}
            >
                ${rows.map((row) => this._renderReflectionCard(row))}
            </div>
        `;
    }

    _renderReflectionCard(row) {
        const tone = this._reflectionTone(row);
        const labelText = asString(row.exitLabel || row.exitId);
        const chipLabel = tone === 'success'
            ? this._label('reflection_chip_passed', 'Check passed: {label}', { label: labelText })
            : tone === 'warning'
              ? this._label('reflection_chip_revise', 'Needs revision: {label}', { label: labelText })
              : this._label('reflection_chip_blocked', 'Blocked: {label}', { label: labelText });
        const iconName = tone === 'success' ? 'check' : tone === 'warning' ? 'alert-triangle' : 'close';
        const expanded = this._reflectionIsExpanded(row);
        const summary = asString(row.summary);
        const issues = asArray(row.issues).filter((item) => isPlainObject(item)).slice(0, 3);
        const reasons = asArray(row.blockedReasons)
            .filter((item) => typeof item === 'string' && item.length > 0)
            .slice(0, 4);
        const hasDetail = summary.length > 0 || issues.length > 0 || reasons.length > 0;
        return html`
            <div class="reflection-card">
                <button
                    type="button"
                    class="reflection-chip"
                    data-tone=${tone}
                    aria-expanded=${expanded ? 'true' : 'false'}
                    title=${expanded
                        ? this._label('reflection_collapse', 'Hide details')
                        : this._label('reflection_expand', 'Show details')}
                    @click=${() => this._toggleReflectionExpanded(row)}
                >
                    <span class="reflection-chip-inner">
                        <platform-icon name=${iconName} size="14"></platform-icon>
                        <span class="reflection-chip-label">${chipLabel}</span>
                    </span>
                </button>
                ${expanded && hasDetail ? html`
                    <div class="reflection-detail">
                        ${summary.length > 0 ? html`
                            <p class="reflection-detail-title">${this._label('reflection_detail_summary', 'Summary')}</p>
                            <p class="reflection-detail-body">${summary}</p>
                        ` : nothing}
                        ${issues.length > 0 ? html`
                            <p class="reflection-detail-title">${this._label('reflection_detail_issues', 'Findings')}</p>
                            <ul class="reflection-issues">
                                ${issues.map((issue) => html`
                                    <li class="reflection-issue">
                                        <span class="reflection-issue-meta">
                                            ${asString(issue.severity)}${asString(issue.criterionId)
                                                ? html` · ${asString(issue.criterionId)}`
                                                : nothing}
                                        </span>
                                        <span class="reflection-issue-finding">${asString(issue.finding)}</span>
                                    </li>
                                `)}
                            </ul>
                        ` : nothing}
                        ${reasons.length > 0 ? html`
                            <p class="reflection-detail-title">${this._label('reflection_detail_reasons', 'Reasons')}</p>
                            <p class="reflection-detail-body">${reasons.join(' · ')}</p>
                        ` : nothing}
                    </div>
                ` : nothing}
            </div>
        `;
    }

    _renderAssistantError() {
        if (this.role !== 'assistant') {
            return nothing;
        }
        const key = asString(this.errorI18nKey);
        const text = key.length > 0 ? this._label(key, key) : asString(this.error);
        if (text.length === 0) {
            return nothing;
        }
        return html`<div class="chat-line-error" role="alert">${text}</div>`;
    }

    _renderStreamPending() {
        if (this.role !== 'assistant' || !this.streaming || this._streamPendingSuppressed()) {
            return nothing;
        }
        if (asString(this.content).length > 0) {
            return nothing;
        }
        return html`
            <div class="stream-pending" aria-live="polite">
                <span>${this._label('streaming_placeholder', 'Generating a reply...')}</span>
                <span class="stream-placeholder-shimmer" aria-hidden="true"></span>
            </div>
        `;
    }

    _renderInputRequired() {
        if (!this.inputRequired || typeof this.inputRequired !== 'object') {
            return nothing;
        }
        const kind = asString(this.inputRequired.interruptKind);
        const workItemId = asString(this.inputRequired.workItemId);
        const oauthService = asString(this.inputRequired.service);
        const isWorkspaceOauth = kind === 'oauth_required' && oauthService === 'workspace';
        const banner = isWorkspaceOauth
            ? this._label('interrupt_oauth_workspace_banner', 'Google Workspace authorization required')
            : kind === 'oauth_required'
              ? this._label('interrupt_oauth_banner', 'External service authorization required')
              : kind === 'operator_task'
                ? this._label('interrupt_operator_banner', 'Waiting for an operator. The chat is on hold.')
                : kind === 'handoff'
                  ? this._label('interrupt_handoff_banner', 'Control transferred to another agent')
                  : '';
        const oauthQuestion = isWorkspaceOauth
            ? this._label(
                'interrupt_oauth_workspace_question',
                'Connect Google Workspace to continue with Docs and Sheets.',
            )
            : asString(this.inputRequired.question);
        const oauthButton = isWorkspaceOauth
            ? this._label('interrupt_oauth_workspace_button', 'Connect Google Workspace')
            : this._label('interrupt_oauth_button', 'Authorize');
        const targetFlowName = asString(this.inputRequired.targetFlowName);
        const handoffReason = asString(this.inputRequired.reason);
        const handoffDepth = this.inputRequired.depth;
        const authUrl = asString(this.inputRequired.authUrl);
        return html`
            <div class="input-required">
                ${banner ? html`<div class="input-required-banner">${banner}</div>` : nothing}
                ${kind === 'handoff' && targetFlowName.length > 0
                    ? html`<div class="input-required-handoff-target">${targetFlowName}</div>`
                    : nothing}
                ${kind === 'handoff' && handoffReason.length > 0
                    ? html`<div class="input-required-handoff-reason">${handoffReason}</div>`
                    : nothing}
                ${kind === 'handoff' && typeof handoffDepth === 'number' && handoffDepth > 0
                    ? html`<div class="input-required-handoff-depth">${this._label('chat_handoff.handoff_chain_depth', 'Chain depth: {depth}').replace('{depth}', String(handoffDepth))}</div>`
                    : nothing}
                ${kind === 'operator_task' && workItemId.length > 0
                    ? html`<platform-work-item-badge
                        work-item-id=${workItemId}
                        variant="chip"
                        size="sm"
                        interactive
                    ></platform-work-item-badge>`
                    : nothing}
                <div class="markdown">${this._markdownTemplate(oauthQuestion)}</div>
                ${kind === 'oauth_required' && authUrl
                    ? html`
                          <a class="oauth-auth-link" href=${authUrl} target="_blank" rel="noopener noreferrer">
                              ${oauthButton}
                          </a>
                      `
                    : nothing}
            </div>
        `;
    }

    _renderOperatorReply() {
        const reply = asString(this.operatorReply).trim();
        if (reply.length === 0) {
            return nothing;
        }
        return html`
            <div class="operator-reply">
                <div class="operator-reply-label">${this._label('operator_reply_heading', 'Operator')}</div>
                <div class="markdown">${this._markdownTemplate(reply)}</div>
            </div>
        `;
    }

    _renderBreakpoint() {
        if (!this.breakpoint || typeof this.breakpoint !== 'object') {
            return nothing;
        }
        const nodeId = asString(this.breakpoint.nodeId) || asString(this.breakpoint.node_id);
        return html`
            <div class="breakpoint">
                <div class="breakpoint-header">
                    <span class="breakpoint-icon" aria-hidden="true"></span>
                    <span class="breakpoint-title">Breakpoint: ${nodeId}</span>
                </div>
                <div class="breakpoint-message markdown">${this._markdownTemplate(asString(this.breakpoint.message))}</div>
                <div class="breakpoint-actions">
                    <button type="button" @click=${this._continueBreakpoint}>${this._label('breakpoint_continue', 'Continue')}</button>
                    <button type="button" @click=${this._viewBreakpointState}>${this._label('breakpoint_view_state', 'View state')}</button>
                </div>
            </div>
        `;
    }

    _renderFiles() {
        const files = asArray(this.files);
        if (files.length > 0) {
            return html`<div class="files-container">${files.map((file) => this._renderFile(file))}</div>`;
        }
        const meta = asArray(this.filesMeta);
        if (meta.length === 0) {
            return nothing;
        }
        return html`
            <div class="files-container">
                ${meta.map((file) => {
                    const name = asString(file?.name) || asString(file?.original_name) || this._label('download_file', 'Download');
                    const mimeType = asString(file?.content_type || file?.mime_type);
                    return html`
                        <div class="file-item">
                            <platform-icon file-icon name=${resolveFileIconKey(name, mimeType)} size="20"></platform-icon>
                            <div class="file-name">${name}</div>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    _renderFile(file) {
        if (!file || typeof file !== 'object') {
            return nothing;
        }
        const mimeType = asString(file.content_type || file.mime_type);
        const originalName = asString(file.original_name || file.name);
        const isImage = mimeType.startsWith('image/');
        const iconKey = isImage ? 'image' : resolveFileIconKey(originalName, mimeType);
        const fileId = asString(file.file_id);
        const href = asString(file.url) || (fileId.length > 0 ? this._downloadUrl(fileId) : '');
        const content = html`
            <platform-icon file-icon name=${iconKey} size="20"></platform-icon>
            <div>
                <div class="file-name">${originalName || fileId || href}</div>
                ${file.file_size ? html`<div class="file-size">${formatFileSize(file.file_size)}</div>` : nothing}
            </div>
        `;
        if (fileId.length > 0) {
            return html`
                <button
                    type="button"
                    class="file-item"
                    @click=${() => this.openFile({
                        ...file,
                        file_id: fileId,
                        original_name: originalName,
                        content_type: mimeType,
                    }, { source: 'flows_chat_message' })}
                >
                    ${content}
                </button>
            `;
        }
        if (href.length === 0) {
            return html`<div class="file-item">${content}</div>`;
        }
        return html`<a class="file-item" href=${href} target="_blank" rel="noopener">${content}</a>`;
    }

    _renderOperatorFiles() {
        const ids = asArray(this.fileIds);
        if (ids.length === 0) {
            return nothing;
        }
        return html`
            <div class="files-container">
                ${ids.map((fid) => html`
                    <button
                        type="button"
                        class="file-item"
                        @click=${() => this.openFile(fid, { source: 'flows_chat_operator_file' })}
                    >
                        <platform-icon file-icon name="text" size="20"></platform-icon>
                        <div>
                            <div class="file-name">${this._label('operator_files', 'Attached files')}</div>
                        </div>
                    </button>
                `)}
            </div>
        `;
    }

    _renderBlocks() {
        const blocks = asArray(this.blocks);
        if (blocks.length === 0) {
            return nothing;
        }
        const root = this._flowRoot();
        return html`
            <div class="blocks">
                ${blocks.map((block) => html`
                    <flows-chat-block-renderer .block=${normalizeFlowChatBlockForPlatformUrls(block)}></flows-chat-block-renderer>
                `)}
            </div>
        `;
    }

    _onMessageHttpPlayStarted() {
        stopStreamTtsPlayback();
        this.dispatchEvent(new CustomEvent('play-started', { bubbles: true, composed: true }));
    }

    _renderAssistantActions() {
        if (!this.showAssistantActions || this.role !== 'assistant' || this.streaming) {
            return nothing;
        }
        const text = asString(this.content).trim();
        if (text.length === 0) {
            return nothing;
        }
        return html`
            <div class="assistant-actions">
                <platform-assistant-message-actions
                    .text=${text}
                    voice-base-url=${asString(this.voiceBaseUrl)}
                    credentials=${this.useCredentials ? 'include' : 'omit'}
                    .getHeaders=${typeof this.getHeaders === 'function' ? this.getHeaders : null}
                    @play-started=${this._onMessageHttpPlayStarted}
                ></platform-assistant-message-actions>
            </div>
        `;
    }

    _renderUserActions() {
        if (!this.showUserActions || this.role !== 'user' || this.streaming) {
            return nothing;
        }
        const text = asString(this.content).trim();
        if (text.length === 0) {
            return nothing;
        }
        return html`
            <div class="user-actions">
                <platform-assistant-message-actions
                    .text=${text}
                    voice-base-url=""
                    credentials=${this.useCredentials ? 'include' : 'omit'}
                    show-edit
                    @compose-edit=${this._forwardComposeEdit}
                ></platform-assistant-message-actions>
            </div>
        `;
    }

    _forwardComposeEdit(event) {
        event?.stopPropagation?.();
        const text = asString(event?.detail?.text);
        if (text.length === 0) {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('compose-edit', {
                detail: { text },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _continueBreakpoint() {
        this.dispatchEvent(
            new CustomEvent('continue-breakpoint', {
                detail: { breakpoint: this.breakpoint },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _viewBreakpointState() {
        this.dispatchEvent(
            new CustomEvent('view-breakpoint-state', {
                detail: { breakpoint: this.breakpoint },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _showTracing() {
        const taskId = asString(this.taskId) || asString(this.traceTaskId);
        const traceId = asString(this.handoff?.traceId || this.handback?.traceId);
        this.dispatchEvent(
            new CustomEvent('show-tracing', {
                detail: traceId.length > 0 ? { traceId } : { taskId },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _showLogs() {
        const sessionId = asString(this.sessionId);
        if (sessionId.length === 0) {
            return;
        }
        const taskId = asString(this.taskId);
        this.dispatchEvent(
            new CustomEvent('show-logs', {
                detail: { sessionId, taskId },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _showDurableHistory() {
        const sessionId = asString(this.sessionId);
        if (sessionId.length === 0) {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('show-durable-history', {
                detail: { sessionId },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _showHandoffTrace() {
        const traceId = asString(this.handoff?.traceId || this.handback?.traceId);
        if (traceId.length === 0) {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('show-tracing', {
                detail: { traceId },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _toggleUserRunTrace() {
        this._runTracePanelOpen = !this._runTracePanelOpen;
    }

    _renderUserInlineRunTrace() {
        if (this.role !== 'user' || !this.isLastUserMessage || !this._runTracePanelOpen) {
            return nothing;
        }
        const entries = asArray(this.runTraceEntries);
        return html`
            <div class="user-run-trace-embed">
                <chat-run-trace .entries=${entries} compact show-section-header></chat-run-trace>
            </div>
        `;
    }

    _assistantObservabilityVisible() {
        if (this.role !== 'assistant' || this.streaming) {
            return false;
        }
        const taskId = asString(this.taskId);
        const sessionId = asString(this.sessionId);
        if (this.showTraceControls && taskId.length > 0) {
            return true;
        }
        if (this.showLogsAction && taskId.length > 0) {
            return true;
        }
        if (this.showDurableHistoryAction && sessionId.length > 0) {
            return true;
        }
        return false;
    }

    _renderAssistantObservabilityActions() {
        if (!this._assistantObservabilityVisible()) {
            return nothing;
        }
        const taskId = asString(this.taskId);
        const showTrace = this.showTraceControls && taskId.length > 0;
        const showLogs = this.showLogsAction && taskId.length > 0;
        const showDurable = this.showDurableHistoryAction && asString(this.sessionId).length > 0;
        return html`
            <div class="bubble-observability-actions">
                ${showTrace
                    ? html`
                          <button
                              type="button"
                              class="tracing-btn"
                              @click=${this._showTracing}
                              title=${this._label('show_tracing_title', 'Open tracing')}
                              aria-label=${this._label('show_tracing_title', 'Open tracing')}
                          >
                              <platform-icon name="terminal" size="14"></platform-icon>
                          </button>
                      `
                    : nothing}
                ${showLogs
                    ? html`
                          <button
                              type="button"
                              class="tracing-btn"
                              @click=${this._showLogs}
                              title=${this._label('show_logs_title', 'Open logs')}
                              aria-label=${this._label('show_logs_title', 'Open logs')}
                          >
                              <platform-icon name="file-text" size="14"></platform-icon>
                          </button>
                      `
                    : nothing}
                ${showDurable
                    ? html`
                          <button
                              type="button"
                              class="tracing-btn"
                              @click=${this._showDurableHistory}
                              title=${this._label('show_durable_history_title', 'Open execution history')}
                              aria-label=${this._label('show_durable_history_title', 'Open execution history')}
                          >
                              <platform-icon name="trace-timeline" size="14"></platform-icon>
                          </button>
                      `
                    : nothing}
            </div>
        `;
    }

    _renderUserRunTraceActions() {
        if (!this.showRunTraceControls || !this.isLastUserMessage) {
            return nothing;
        }
        return html`
            <div class="header-actions">
                ${this.runTraceAvailable
                    ? html`
                          <button
                              type="button"
                              class="tracing-btn"
                              @click=${this._toggleUserRunTrace}
                              title=${this._label('show_run_trace_title', this._label('show_tracing_title', 'Open tracing'))}
                              aria-pressed=${this._runTracePanelOpen ? 'true' : 'false'}
                              aria-label=${this._label('show_run_trace_title', this._label('show_tracing_title', 'Open tracing'))}
                          >
                              <platform-icon name="chart" size="14"></platform-icon>
                          </button>
                      `
                    : nothing}
                <button
                    type="button"
                    class="tracing-btn"
                    @click=${this._showTracing}
                    title=${this._label('show_tracing_title', 'Open tracing')}
                    aria-label=${this._label('show_tracing_title', 'Open tracing')}
                >
                    <platform-icon name="terminal" size="14"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderBubbleMeta() {
        if (!this.showHeader) {
            return nothing;
        }
        const timestamp = this._formatTimestamp(this.timestamp);
        if (this.headerCompact) {
            if (this.role === 'user') {
                return html`
                    <div class="bubble-meta user-meta">
                        ${this._renderUserRunTraceActions()}
                        ${timestamp ? html`<span class="timestamp">${timestamp}</span>` : nothing}
                        ${this._renderAuthorIdentity()}
                    </div>
                `;
            }
            if (this.role === 'assistant' || this.role === 'operator') {
                return html`
                    <div class="bubble-meta assistant-meta">
                        ${this._renderAuthorIdentity()}
                        ${timestamp ? html`<span class="timestamp">${timestamp}</span>` : nothing}
                        ${this._renderAssistantObservabilityActions()}
                    </div>
                `;
            }
        }
        if (this.role === 'user') {
            return this._renderUserHeaderLegacy();
        }
        return this._renderDefaultHeaderLegacy();
    }

    _renderUserHeaderLegacy() {
        const hasTools = this.showRunTraceControls && this.isLastUserMessage;
        const timestamp = this._formatTimestamp(this.timestamp);
        if (!hasTools) {
            return html`
                <div class="header">
                    ${this._renderAuthorIdentity()}
                    ${timestamp ? html`<span class="timestamp">${timestamp}</span>` : nothing}
                </div>
            `;
        }
        return html`
            <div class="header has-inline-tools">
                <div class="user-header-meta">
                    ${this._renderAuthorIdentity()}
                    ${timestamp ? html`<span class="timestamp">${timestamp}</span>` : nothing}
                </div>
                ${this._renderUserRunTraceActions()}
            </div>
        `;
    }

    _renderDefaultHeaderLegacy() {
        const timestamp = this._formatTimestamp(this.timestamp);
        return html`
            <div class="header">
                ${this._renderAuthorIdentity()}
                ${timestamp ? html`<span class="timestamp">${timestamp}</span>` : nothing}
                ${this._renderAssistantObservabilityActions()}
            </div>
        `;
    }

    _renderHandoffCard() {
        const card = this.handoff;
        if (!isPlainObject(card)) {
            return nothing;
        }
        const targetName = asString(card.targetFlowName || card.targetFlowId);
        const reason = asString(card.reason);
        const depth = card.depth;
        const traceId = asString(card.traceId);
        const title = formatLabel(
            this._label('chat_handoff.handoff_initiated', 'Transferred control to agent «{targetName}»'),
            { targetName },
        );
        return html`
            <div class="handoff-card">
                <div class="handoff-card-title">${title}</div>
                ${reason.length > 0
                    ? html`<div class="handoff-card-reason"><span class="handoff-card-label">${this._label('chat_handoff.handoff_reason_label', 'Reason')}</span> ${reason}</div>`
                    : nothing}
                ${typeof depth === 'number' && depth > 0
                    ? html`<div class="handoff-card-depth">${formatLabel(this._label('chat_handoff.handoff_chain_depth', 'Chain depth: {depth}'), { depth: String(depth) })}</div>`
                    : nothing}
                ${traceId.length > 0
                    ? html`<button type="button" class="handoff-trace-btn" @click=${this._showHandoffTrace}>${this._label('chat_handoff.open_trace', 'Open trace')}</button>`
                    : nothing}
            </div>
        `;
    }

    _renderHandbackCard() {
        const card = this.handback;
        if (!isPlainObject(card)) {
            return nothing;
        }
        const parentName = asString(card.parentFlowName || card.childFlowName);
        const response = asString(card.response);
        const traceId = asString(card.traceId);
        const title = formatLabel(
            this._label('chat_handoff.handback_completed', 'Returned control to agent «{parentName}»'),
            { parentName },
        );
        return html`
            <div class="handback-card">
                <div class="handback-card-title">${title}</div>
                ${response.length > 0
                    ? html`<div class="handback-card-response"><span class="handback-card-label">${this._label('chat_handoff.handoff_result_label', 'Result')}</span> ${this._markdownTemplate(response)}</div>`
                    : nothing}
                ${traceId.length > 0
                    ? html`<button type="button" class="handoff-trace-btn" @click=${this._showHandoffTrace}>${this._label('chat_handoff.open_trace', 'Open trace')}</button>`
                    : nothing}
            </div>
        `;
    }

    _renderHandoffMessage() {
        return html`
            <div class="message handoff">
                <div class=${classNames({ avatar: true, hidden: !this.showAvatar })}>
                    <platform-icon name=${this._avatarIcon()} size="18"></platform-icon>
                </div>
                <div class="bubble handoff-bubble">
                    ${this._renderHandoffCard()}
                </div>
            </div>
        `;
    }

    _renderHandbackMessage() {
        return html`
            <div class="message handback">
                <div class=${classNames({ avatar: true, hidden: !this.showAvatar })}>
                    <platform-icon name=${this._avatarIcon()} size="18"></platform-icon>
                </div>
                <div class="bubble handback-bubble">
                    ${this._renderHandbackCard()}
                </div>
            </div>
        `;
    }

    _renderMainText(role, text) {
        if (text.length === 0) {
            return nothing;
        }
        if (role === 'user') {
            return html`<div class=${classNames({ text: true, 'has-content': true })}>${text}</div>`;
        }
        return html`<div class=${classNames({ markdown: true, 'has-content': true })}>${this._markdownTemplate(text, { streaming: Boolean(this.streaming) })}</div>`;
    }

    render() {
        const role = asString(this.role) || 'assistant';
        if (role === 'handoff') {
            return this._renderHandoffMessage();
        }
        if (role === 'handback') {
            return this._renderHandbackMessage();
        }
        const text = asString(this.content);
        const classes = classNames({
            message: true,
            [role]: true,
            streaming: this.streaming,
        });
        return html`
            <div class=${classes}>
                <div class=${classNames({ avatar: true, hidden: !this.showAvatar })}>
                    <platform-icon name=${this._avatarIcon()} size="18"></platform-icon>
                </div>
                <div class="bubble">
                    <div class="content">
                        ${this._renderBubbleMeta()}
                        ${this._renderUserInlineRunTrace()}
                        ${this._renderFiles()}
                        ${this._renderOperatorFiles()}
                        ${this._renderActivity()}
                        ${this._renderSkillLoads()}
                        ${this._renderReflectionResults()}
                        ${this._renderToolOrbs()}
                        ${this._renderReasoning()}
                        ${this._renderMainText(role, text)}
                        ${this._renderStreamPending()}
                        ${this._renderAssistantError()}
                        ${this._renderInputRequired()}
                        ${this._renderOperatorReply()}
                        ${this._renderBreakpoint()}
                        ${this._renderBlocks()}
                    </div>
                    ${this._renderUserActions()}
                    ${this._renderAssistantActions()}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-chat-message', FlowsChatMessage);

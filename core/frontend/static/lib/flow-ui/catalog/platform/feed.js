import { html, nothing } from '../../../lit-shim.js';
import { flowUIGlyph } from '../flow-ui-glyph.js';
import {
    labelOfComponent,
    localizedText,
    optionalComponentProperty,
    renderProjectedArtifactCard,
    renderSanitizedMarkdown,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import {
    conversationTasks,
    conversationTurnText,
    conversationUserFiles,
    conversationUserText,
    hasConversationContent,
    isOrdinaryConversationArtifact,
    isTerminalTaskState,
    mergeConversationTasks,
} from './conversation-turn.js';
import {
    projectConversationActivity,
    resolveTurnActivityPolicy,
} from '../../runtime/turn-activity.js';
import { flowUIText } from '../../utils/text.js';
import { openFlowUISessionFile } from '../../utils/open-session-file.js';

export {
    conversationTasks,
    conversationTurnText,
    conversationUserText,
    hasConversationContent,
    mergeConversationTasks,
} from './conversation-turn.js';

const BRAND_LOGO_SRC = '/static/core/assets/service_logos/linnex_spinner_logo.png';

/**
 * Close a dangling `**`/backtick pair so a streaming chunk renders styled
 * progressively instead of flashing raw markers until the closing token lands.
 */
function streamingSafeMarkdown(text) {
    let safe = text;
    const boldCount = (safe.match(/\*\*/g) || []).length;
    if (boldCount % 2 === 1) safe += '**';
    const codeCount = (safe.match(/`/g) || []).length;
    if (codeCount % 2 === 1) safe += '`';
    return safe;
}

function bubbleFileLabel(ref) {
    if (typeof ref.original_name === 'string' && ref.original_name !== '') return ref.original_name;
    if (typeof ref.filename === 'string' && ref.filename !== '') return ref.filename;
    return String(ref.file_id || '');
}

function renderFileChips(host, files) {
    if (!files.length) return nothing;
    return html`<div class="bubble-files" role="list">
        ${files.map((ref) => {
            const name = bubbleFileLabel(ref);
            return html`<button
                type="button"
                class="bubble-file-chip"
                role="listitem"
                title=${name}
                aria-label=${flowUIText(host.locale, 'open_file', { name })}
                @click=${() => openFlowUISessionFile(ref, 'flow_ui_bubble')}
            >
                ${flowUIGlyph('file', 14)}
                <span class="bubble-file-name">${name}</span>
            </button>`;
        })}
    </div>`;
}

function renderUserBubble(host, task, text, files) {
    if (text === '' && files.length === 0) return nothing;
    return html`<div class="message-row user">
        <article class="bubble">
            ${text !== '' ? html`<div class="part-text">${renderSanitizedMarkdown(text)}</div>` : nothing}
            ${renderFileChips(host, files)}
        </article>
    </div>`;
}

function assistantAvatar() {
    return html`<div class="avatar" aria-hidden="true"><img src=${BRAND_LOGO_SRC} alt=""></div>`;
}

function renderAssistantBubble(host, task, text, { streaming, failed }) {
    const copied = host.copiedTaskId === task.id;
    return html`<div class="message-row assistant">
        ${assistantAvatar()}
        <article class="bubble">
            <div class="part-text">
                ${renderSanitizedMarkdown(streaming ? streamingSafeMarkdown(text) : text)}${streaming
                    ? html`<span class="streaming-caret" aria-hidden="true"></span>`
                    : nothing}
            </div>
        </article>
        ${streaming ? nothing : html`<div class="msg-actions">
            <button
                type="button"
                class="msg-action-btn"
                aria-label=${flowUIText(host.locale, copied ? 'message_copied' : 'message_copy')}
                title=${flowUIText(host.locale, copied ? 'message_copied' : 'message_copy')}
                @click=${() => host._copyTurnText(task.id, text)}
            >${flowUIGlyph(copied ? 'check' : 'copy', 14)}</button>
            ${failed && !host.readonly ? html`<button
                type="button"
                class="msg-action-btn"
                aria-label=${flowUIText(host.locale, 'retry')}
                title=${flowUIText(host.locale, 'retry')}
                @click=${() => host._retryTurn(task)}
            >${flowUIGlyph('rotate-ccw', 14)}</button>` : nothing}
        </div>`}
    </div>`;
}

function renderTypingBubble(host) {
    return html`<div class="message-row assistant">
        ${assistantAvatar()}
        <article class="bubble" aria-label=${flowUIText(host.locale, 'assistant_typing')}>
            <span class="typing-indicator" aria-hidden="true">
                <span class="dot-pulse"></span><span class="dot-pulse"></span><span class="dot-pulse"></span>
            </span>
        </article>
    </div>`;
}

function activityChipTitle(item) {
    if (item.detail && item.detail !== '') {
        return `${item.label}: ${item.detail}`;
    }
    return item.label;
}

function renderTurnActivityStrip(host, task) {
    const document = host.controller?.document || null;
    const policy = resolveTurnActivityPolicy(document || {});
    const locale = host.locale === 'en' ? 'en' : 'ru';
    const items = projectConversationActivity(task, policy, locale);
    if (items.length === 0) return nothing;
    return html`<div class="turn-activity" role="list" aria-label=${flowUIText(locale, 'turn_toast_activity')}>
        ${items.map((item) => html`<span
            class="turn-activity-chip"
            role="listitem"
            data-kind=${item.kind}
            data-status=${item.status}
            title=${activityChipTitle(item)}
        >
            <span class="turn-activity-kind">${item.kind === 'skill'
                ? flowUIText(locale, 'skill_activity')
                : (item.kind === 'error'
                    ? flowUIText(locale, 'turn_toast_error')
                    : flowUIText(locale, 'tool_activity'))}</span>
            <span class="turn-activity-label">${item.label}</span>
            ${item.status === 'running'
                ? html`<span class="turn-activity-pulse" aria-hidden="true"></span>`
                : nothing}
        </span>`)}
    </div>`;
}

function renderConversationTask(host, task, { isLast }) {
    const userText = conversationUserText(task);
    const userFiles = conversationUserFiles(task);
    const turnText = conversationTurnText(task);
    const state = task.status?.state;
    const terminal = isTerminalTaskState(state);
    const failed = state === 'TASK_STATE_FAILED';
    const streaming = !terminal && turnText !== '';
    const waiting = !terminal && turnText === '' && isLast;
    return html`<section class="task" data-task-id=${task.id}>
        ${renderUserBubble(host, task, userText, userFiles)}
        ${renderTurnActivityStrip(host, task)}
        ${turnText !== ''
            ? renderAssistantBubble(host, task, turnText, { streaming, failed })
            : nothing}
        ${waiting ? renderTypingBubble(host) : nothing}
    </section>`;
}

function renderDebugTask(host, task) {
    return html`<section class="task">
        <div class="task-head">
            <span>${task.id}</span>
            <span class="task-state">${task.status?.state || 'TASK_STATE_SUBMITTED'}</span>
        </div>
        ${(task.artifacts || [])
            .filter(isOrdinaryConversationArtifact)
            .map((artifact) => renderProjectedArtifactCard(host.locale, artifact))}
    </section>`;
}

export function renderArtifactFeed(host, component) {
    if (!Array.isArray(host.tasks)) {
        throw new Error('flow-ui: ArtifactFeed host.tasks must be an array');
    }
    const presentation = optionalComponentProperty(component, 'presentation');
    const conversation = presentation === 'conversation';
    const pendingTurns = host.controller?.activeContext?.pendingTurns;
    const tasks = conversation
        ? mergeConversationTasks(host.tasks, pendingTurns)
        : host.tasks;
    if (!tasks.length) return wrapFlowNode(host, component, nothing);
    return wrapFlowNode(
        host,
        component,
        html`<div
            class="task-feed"
            role="log"
            aria-live="polite"
            aria-atomic="false"
            aria-label=${flowUIText(host.locale, 'conversation_feed'        )}
        >${tasks.map((task, index) => (
            conversation
                ? renderConversationTask(host, task, { isLast: index === tasks.length - 1 })
                : renderDebugTask(host, task)
        ))}</div>`,
    );
}

export function renderTaskControls(host, component) {
    // Runtime cancel control lives in <platform-flow-ui> chrome (left of Share).
    // Document slot stays for catalog/editor structure only.
    return wrapFlowNode(host, component, nothing);
}

export function renderAgentIdentity(host, component) {
    const agent = resolveBound(host.surface, component, 'agent', host.tasks);
    if (agent != null && typeof agent !== 'object') {
        throw new Error(`flow-ui: AgentIdentity ${component.component_id} agent must be an object`);
    }
    const title = agent?.title
        || agent?.name
        || optionalComponentProperty(component, 'title')
        || 'Agent';
    const logoSrc = typeof agent?.logo_path === 'string' && agent.logo_path.trim() !== ''
        ? agent.logo_path
        : BRAND_LOGO_SRC;
    const subtitle = typeof agent?.subtitle === 'string' ? agent.subtitle : '';
    return wrapFlowNode(
        host,
        component,
        html`<div class="identity">
            <div class="avatar" aria-hidden="true"><img src=${logoSrc} alt=""></div>
            <div>
                <strong>${title}</strong>
                ${subtitle ? html`<div class="muted">${subtitle}</div>` : nothing}
            </div>
        </div>`,
    );
}

export function renderEmptyState(host, component) {
    if (!Array.isArray(host.tasks)) {
        throw new Error('flow-ui: EmptyState host.tasks must be an array');
    }
    const message = localizedText(
        resolveBound(host.surface, component, 'message', host.tasks)
            ?? optionalComponentProperty(component, 'message'),
    );
    const pendingTurns = host.controller?.activeContext?.pendingTurns;
    const feedTasks = mergeConversationTasks(host.tasks, pendingTurns);
    if (!message || hasConversationContent(feedTasks)) {
        return nothing;
    }
    return wrapFlowNode(host, component, html`<div class="empty empty--greeting"><p>${message}</p></div>`);
}

export function renderSuggestedPrompts(host, component) {
    const items = resolveBound(host.surface, component, 'items', host.tasks);
    if (items != null && !Array.isArray(items)) {
        throw new Error(`flow-ui: SuggestedPrompts ${component.component_id} items must be an array`);
    }
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return nothing;
    const feedTasks = mergeConversationTasks(host.tasks, host.controller?.activeContext?.pendingTurns);
    if (hasConversationContent(feedTasks)) return nothing;
    return wrapFlowNode(
        host,
        component,
        html`<div class="suggestions">${list.map((item) => html`<button
            class="secondary"
            ?disabled=${host.readonly}
            @click=${() => host._action(component, 'select', { value: String(item) })}
        >${String(item)}</button>`)}</div>`,
    );
}

export function renderBadge(host, component) {
    const label = labelOfComponent(host, component)
        || localizedText(resolveBound(host.surface, component, 'text', host.tasks));
    return wrapFlowNode(host, component, html`<span class="badge">${label}</span>`);
}

export function renderStatus(host, component) {
    return renderBadge(host, component);
}

export function renderProgress(host, component) {
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const max = optionalComponentProperty(component, 'max');
    const propertyValue = optionalComponentProperty(component, 'value');
    return wrapFlowNode(
        host,
        component,
        html`<progress
            class="progress"
            max=${max == null ? 100 : Number(max)}
            value=${Number(value ?? propertyValue ?? 0)}
        ></progress>`,
    );
}

export function renderAlert(host, component) {
    const label = labelOfComponent(host, component)
        || optionalComponentProperty(component, 'message');
    return wrapFlowNode(
        host,
        component,
        html`<div class="alert" role="status">${label}</div>`,
    );
}

export function renderMetric(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks)
        ?? optionalComponentProperty(component, 'value');
    return wrapFlowNode(
        host,
        component,
        html`<div class="metric"><div class="muted">${label}</div><h2>${value}</h2></div>`,
    );
}

export function renderDataTable(host, component) {
    const rows = resolveBound(host.surface, component, 'rows', host.tasks)
        ?? optionalComponentProperty(component, 'rows');
    const columns = optionalComponentProperty(component, 'columns');
    if (rows != null && !Array.isArray(rows)) {
        throw new Error(`flow-ui: DataTable ${component.component_id} rows must be an array`);
    }
    if (columns != null && !Array.isArray(columns)) {
        throw new Error(`flow-ui: DataTable ${component.component_id} columns must be an array`);
    }
    const rowList = Array.isArray(rows) ? rows : [];
    const columnList = Array.isArray(columns) ? columns : [];
    return wrapFlowNode(
        host,
        component,
        html`<div class="table-wrap"><table>
            <thead><tr>${columnList.map((column) => html`<th>${column.label || column.key}</th>`)}</tr></thead>
            <tbody>${rowList.map((row) => html`<tr>${columnList.map((column) => html`<td>${String(row[column.key] ?? '')}</td>`)}</tr>`)}</tbody>
        </table></div>`,
    );
}

export function registerPlatformFeed(register) {
    register('ArtifactFeed', renderArtifactFeed);
    register('TaskControls', renderTaskControls);
    register('AgentIdentity', renderAgentIdentity);
    register('EmptyState', renderEmptyState);
    register('SuggestedPrompts', renderSuggestedPrompts);
    register('Badge', renderBadge);
    register('Status', renderStatus);
    register('Progress', renderProgress);
    register('Alert', renderAlert);
    register('Metric', renderMetric);
    register('DataTable', renderDataTable);
}

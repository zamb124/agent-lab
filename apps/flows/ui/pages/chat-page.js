/**
 * ChatPage — тонкий SPA-хост единого чат-компонента.
 *
 * Весь чат (сообщения, композер, файлы, voice/TTS, SSE A2A) живёт в
 * `<platform-chat display="page" profile="spa">` (core/lib/chat). Страница даёт
 * только shell: page-header с действиями (трейсы, логи, история, редактор,
 * очистка, share preview, триггеры) и восстановление сессии из URL
 * (`flows/session_state` → `loadSession`).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/chat/platform-chat.js';
import { dispatchEmbedChatWindowToggle } from '@platform/lib/chat/chat-window-toggle.js';
import { resolveVoiceHttpOrigin } from '@platform/lib/voice/voice-http-origin.js';
import '../modals/flows-preview-share-modal.js';
import { asArray, asString, isPlainObject, authActiveCompanyId } from '../_helpers/flows-resolvers.js';
import { a2aStateMessagesToChatMessages } from '../_helpers/chat-session-messages.js';
import { resolveFlowsChatTaskId } from '../_helpers/resolve-flows-chat-task-id.js';

export class ChatPage extends PlatformPage {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        sessionId: { type: String, attribute: 'session-id' },
        _isMobile: { state: true },
        _overflowOpen: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                background: transparent;
                box-sizing: border-box;
            }
            .chat-breadcrumbs {
                flex-shrink: 0;
                padding: var(--space-2) var(--space-4) 0;
            }
            .chat-branch-hint {
                flex-shrink: 0;
                padding: 0 var(--space-4) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .flow-chat-header-actions {
                position: relative;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                isolation: isolate;
            }
            .chat-actions-help {
                flex-shrink: 0;
            }
            .flow-chat-overflow-anchor {
                position: relative;
            }
            .flow-chat-overflow-anchor[data-open] {
                z-index: 1;
            }
            .menu-flyout {
                position: absolute;
                right: 0;
                top: 100%;
                margin-top: 4px;
                width: min(320px, calc(100vw - 2 * var(--space-4)));
                max-width: calc(100vw - 2 * var(--space-4));
                box-sizing: border-box;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border, var(--border-subtle));
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
                z-index: 2;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-1);
                overflow: hidden;
            }
            .chat-workspace {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                padding: 0 var(--space-4) var(--space-3);
            }
            platform-chat {
                flex: 1;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.sessionId = '';
        this._isMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
        this._overflowOpen = false;
        this._chatMql = null;
        this._onChatMobileMql = null;
        this._onDocPointer = (e) => {
            if (!this._overflowOpen) {
                return;
            }
            const path = e.composedPath();
            for (const n of path) {
                if (n === this) {
                    break;
                }
                if (n == null || typeof n !== 'object' || !('classList' in n) || !n.classList) {
                    continue;
                }
                if (n.classList.contains('flow-chat-header-actions')) {
                    return;
                }
            }
            this._overflowOpen = false;
        };
        this._sessionState = this.useOp('flows/session_state');
        this._flows = this.useResource('flows/flows');
        this._activeCompanySel = this.select((s) => authActiveCompanyId(s));
        this._localeSel = this.select((s) => s.i18n.locale);
        this._voiceBaseUrl =
            typeof window !== 'undefined' && typeof window.location !== 'undefined'
                ? resolveVoiceHttpOrigin()
                : '';
        this._restoredSessionId = '';
        this.useEvent(CoreEvents.UI_MODAL_OPEN, () => {
            if (this._overflowOpen) {
                this._overflowOpen = false;
            }
        });
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        this._chatMql = window.matchMedia('(max-width: 767px)');
        this._onChatMobileMql = () => {
            const next = this._chatMql.matches;
            if (next !== this._isMobile) {
                this._isMobile = next;
            }
        };
        this._chatMql.addEventListener('change', this._onChatMobileMql);
        const next = this._chatMql.matches;
        if (next !== this._isMobile) {
            this._isMobile = next;
        }
        document.addEventListener('pointerdown', this._onDocPointer);
    }

    disconnectedCallback() {
        if (this._chatMql && this._onChatMobileMql) {
            this._chatMql.removeEventListener('change', this._onChatMobileMql);
        }
        document.removeEventListener('pointerdown', this._onDocPointer);
        super.disconnectedCallback();
    }

    firstUpdated() {
        this._initOrLoadSession();
    }

    updated(changed) {
        if (super.updated) {
            super.updated(changed);
        }
        if (changed.has('flowId') || changed.has('sessionId') || changed.has('branchId')) {
            this._initOrLoadSession();
        }
    }

    /** @returns {import('@platform/lib/chat/platform-chat.js').PlatformChat|null} */
    _platformChat() {
        const el = this.renderRoot?.querySelector('platform-chat');
        return el || null;
    }

    _initOrLoadSession() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        if (this.sessionId && this.sessionId.length > 0) {
            if (this._restoredSessionId !== this.sessionId) {
                this._restoredSessionId = this.sessionId;
                void this._restoreSessionFromUrl(this.sessionId);
            }
            return;
        }
        this._restoredSessionId = '';
    }

    async _restoreSessionFromUrl(sessionId) {
        const result = await this._sessionState.run({ session_id: sessionId });
        const rawMessages = isPlainObject(result) && Array.isArray(result.messages) ? result.messages : [];
        const rawFiles = isPlainObject(result) && Array.isArray(result.files) ? result.files : [];
        const resultTaskId = isPlainObject(result) && typeof result.task_id === 'string' ? result.task_id : null;
        const messages = a2aStateMessagesToChatMessages(rawMessages, resultTaskId);
        await this.updateComplete;
        const chat = this._platformChat();
        if (!chat) {
            throw new Error('chat-page: platform-chat is not mounted');
        }
        chat.loadSession({
            sessionId,
            flowId: this.flowId,
            messages,
            files: rawFiles,
            taskId: resultTaskId,
        });
    }

    _chatRuntimeState() {
        const chat = this._platformChat();
        return chat ? chat.runtimeState : null;
    }

    _currentContextId() {
        const state = this._chatRuntimeState();
        const ctx = state && typeof state.currentContextId === 'string' ? state.currentContextId : '';
        return ctx;
    }

    _currentFlow() {
        const items = asArray(this._flows.items);
        const found = items.find((f) => f && f.flow_id === this.flowId);
        return found ? found : null;
    }

    _onChatRunEvent(e) {
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (!detail || typeof detail.type !== 'string') {
            return;
        }
        this.dispatch(detail.type, isPlainObject(detail.payload) ? detail.payload : {}, { source: 'http' });
    }

    _onChatVoiceError(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const msg = typeof detail.detail === 'string' && detail.detail.trim() !== ''
            ? detail.detail
            : typeof detail.code === 'string'
              ? detail.code
              : this.t('platform_chat.toast_voice_ws_hint');
        this.toast('flows:platform_chat.toast_voice_error', {
            type: 'error',
            vars: { detail: msg },
        });
    }

    _onChatToast(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const message = typeof detail.message === 'string' ? detail.message.trim() : '';
        if (message === '') {
            return;
        }
        this.toast('flows:platform_chat.toast_voice_error', {
            type: 'warning',
            vars: { detail: message },
        });
    }

    _onClear() {
        this._overflowOpen = false;
        const chat = this._platformChat();
        if (chat) {
            chat.startNewChat();
        }
    }

    _onFlowsChatBack() {
        this.navigate('list', {});
    }

    _openEditor() {
        this._overflowOpen = false;
        if (!this.flowId) return;
        if (this.branchId && this.branchId !== 'base') {
            this.navigate('flow_editor_branch', { flowId: this.flowId, branchId: this.branchId });
        } else {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    _openTriggers() {
        this._overflowOpen = false;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.triggers', { flowId: this.flowId });
    }

    _openFlowSettings() {
        this._overflowOpen = false;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.flow_edit', { flowId: this.flowId });
    }

    _openTracingModalFromDetail(detail) {
        this._overflowOpen = false;
        const ctxId = this._currentContextId();
        if (!ctxId || !this.flowId) {
            return;
        }
        const sessionId = `${this.flowId}:${ctxId}`;
        const taskId =
            detail && typeof detail === 'object' && typeof detail.taskId === 'string' && detail.taskId.length > 0
                ? detail.taskId
                : '';
        const props = { sessionId };
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        const traceId =
            detail && typeof detail === 'object' && typeof detail.traceId === 'string' && detail.traceId.length > 0
                ? detail.traceId
                : '';
        if (traceId.length > 0) {
            props.traceId = traceId;
        }
        this.openModal('flows.tracing', props);
    }

    _openTracing() {
        this._openTracingModalFromDetail(null);
    }

    _onChatShowTracing(e) {
        this._openTracingModalFromDetail(e.detail);
    }

    _onChatShowLogs(e) {
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const sessionId = typeof detail.sessionId === 'string' ? detail.sessionId : '';
        if (sessionId.length === 0) {
            return;
        }
        const props = { sessionId };
        const taskId = typeof detail.taskId === 'string' ? detail.taskId : '';
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.logs', props);
    }

    _onChatShowDurableHistory(e) {
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const sessionId = typeof detail.sessionId === 'string' ? detail.sessionId : '';
        if (sessionId.length === 0) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    /** Вместо window.open (default поведение bubble) — платформенная модалка предпросмотра браузера. */
    _onBrowserPreviewOpen(e) {
        e.preventDefault();
        const detail = isPlainObject(e.detail) ? e.detail : {};
        this.openModal('flows.browser_preview', {
            viewerUrl: asString(detail.viewerUrl),
            sessionId: asString(detail.sessionId),
            currentUrl: asString(detail.currentUrl),
            status: asString(detail.status),
        });
    }

    _openLogs() {
        this._overflowOpen = false;
        const ctxId = this._currentContextId();
        if (!ctxId || !this.flowId) {
            return;
        }
        const sessionId = `${this.flowId}:${ctxId}`;
        const state = this._chatRuntimeState();
        const taskId = state ? resolveFlowsChatTaskId(state) : '';
        const props = { sessionId };
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.logs', props);
    }

    _openDurableHistory() {
        this._overflowOpen = false;
        const ctxId = this._currentContextId();
        if (!ctxId || !this.flowId) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId: `${this.flowId}:${ctxId}` });
    }

    _openLara() {
        this._overflowOpen = false;
        dispatchEmbedChatWindowToggle('flows-lara-open', { open: true });
    }

    _openPreviewShare() {
        this._overflowOpen = false;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.openModal('flows.preview_share', { flowId: this.flowId, branchId: bid });
    }

    _toggleOverflow(e) {
        e.stopPropagation();
        this._overflowOpen = !this._overflowOpen;
    }

    _renderHeaderIconButton({ title, icon, iconSize = '16', onClick, dataAction, danger = false }) {
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                ?danger=${danger}
                aria-label=${title}
                title=${title}
                data-action=${dataAction || nothing}
                @click=${onClick}
            >
                <platform-icon name=${icon} size=${iconSize}></platform-icon>
            </platform-button>
        `;
    }

    _renderMenuButton({ label, icon, onClick, danger = false }) {
        return html`
            <platform-button variant="ghost" density="compact" block ?danger=${danger} @click=${onClick}>
                <platform-icon name=${icon} size="16"></platform-icon>
                ${label}
            </platform-button>
        `;
    }

    _renderDesktopActions(hasFlow) {
        return html`
            <platform-help-hint
                class="chat-actions-help"
                .label=${this.t('platform_chat.actions_help_label')}
                .summary=${this.t('platform_chat.actions_help_summary')}
                .details=${this.t('platform_chat.actions_help_details')}
                .docHref=${'/documentation/scenarios/flows/run-flow-chat/'}
                .docLabel=${this.t('help_hints.open_scenario')}
            ></platform-help-hint>
            ${this._renderHeaderIconButton({
                title: this.t('editor_header.lara'),
                icon: 'ai',
                onClick: this._openLara,
            })}
            ${hasFlow
                ? this._renderHeaderIconButton({
                    title: this.t('chat_page.flow_settings'),
                    icon: 'settings',
                    dataAction: 'flow-settings',
                    onClick: this._openFlowSettings,
                })
                : nothing}
            ${hasFlow
                ? this._renderHeaderIconButton({
                    title: this.t('editor_header.share_preview'),
                    icon: 'share',
                    onClick: this._openPreviewShare,
                })
                : nothing}
            ${hasFlow
                ? this._renderHeaderIconButton({
                    title: this.t('flows_sidebar.footer_triggers'),
                    icon: 'zap',
                    onClick: this._openTriggers,
                })
                : nothing}
            ${this._renderHeaderIconButton({
                title: this.t('platform_chat.btn_traces'),
                icon: 'chart',
                onClick: this._openTracing,
            })}
            ${this._renderHeaderIconButton({
                title: this.t('platform_chat.btn_logs'),
                icon: 'file-text',
                onClick: this._openLogs,
            })}
            ${this._renderHeaderIconButton({
                title: this.t('platform_chat.btn_history'),
                icon: 'trace-timeline',
                onClick: this._openDurableHistory,
            })}
            ${this._renderHeaderIconButton({
                title: this.t('platform_chat.btn_editor'),
                icon: 'edit',
                onClick: this._openEditor,
            })}
            ${this._renderHeaderIconButton({
                title: this.t('platform_chat.btn_clear'),
                icon: 'trash',
                danger: true,
                onClick: this._onClear,
            })}
        `;
    }

    _renderMobileActions(hasFlow) {
        return html`
            <div class="flow-chat-header-actions" @click=${(e) => e.stopPropagation()}>
                <platform-help-hint
                    class="chat-actions-help"
                    .label=${this.t('platform_chat.actions_help_label')}
                    .summary=${this.t('platform_chat.actions_help_summary')}
                    .details=${this.t('platform_chat.actions_help_details')}
                    .docHref=${'/documentation/scenarios/flows/run-flow-chat/'}
                    .docLabel=${this.t('help_hints.open_scenario')}
                ></platform-help-hint>
                ${this._renderHeaderIconButton({
                    title: this.t('editor_header.lara'),
                    icon: 'ai',
                    onClick: this._openLara,
                })}
                <div class="flow-chat-overflow-anchor" ?data-open=${this._overflowOpen}>
                    ${this._renderHeaderIconButton({
                        title: this.t('platform_chat.overflow_aria'),
                        icon: 'more-vertical',
                        iconSize: '20',
                        onClick: this._toggleOverflow,
                    })}
                    ${this._overflowOpen
                        ? html`
                            <div class="menu-flyout" @click=${(e) => e.stopPropagation()}>
                                ${hasFlow
                                    ? this._renderMenuButton({
                                        label: this.t('chat_page.flow_settings'),
                                        icon: 'settings',
                                        onClick: this._openFlowSettings,
                                    })
                                    : nothing}
                                ${hasFlow
                                    ? this._renderMenuButton({
                                        label: this.t('editor_header.share_preview'),
                                        icon: 'share',
                                        onClick: this._openPreviewShare,
                                    })
                                    : nothing}
                                ${hasFlow
                                    ? this._renderMenuButton({
                                        label: this.t('flows_sidebar.footer_triggers'),
                                        icon: 'zap',
                                        onClick: this._openTriggers,
                                    })
                                    : nothing}
                                ${this._renderMenuButton({
                                    label: this.t('platform_chat.btn_traces'),
                                    icon: 'chart',
                                    onClick: this._openTracing,
                                })}
                                ${this._renderMenuButton({
                                    label: this.t('platform_chat.btn_logs'),
                                    icon: 'file-text',
                                    onClick: this._openLogs,
                                })}
                                ${this._renderMenuButton({
                                    label: this.t('platform_chat.btn_history'),
                                    icon: 'trace-timeline',
                                    onClick: this._openDurableHistory,
                                })}
                                ${this._renderMenuButton({
                                    label: this.t('platform_chat.btn_editor'),
                                    icon: 'edit',
                                    onClick: this._openEditor,
                                })}
                                ${this._renderMenuButton({
                                    label: this.t('platform_chat.btn_clear'),
                                    icon: 'trash',
                                    danger: true,
                                    onClick: this._onClear,
                                })}
                            </div>
                        `
                        : nothing}
                </div>
            </div>
        `;
    }

    render() {
        const flow = this._currentFlow();
        let flowName;
        if (flow && typeof flow.name === 'string' && flow.name.length > 0) {
            flowName = flow.name;
        } else if (typeof this.flowId === 'string' && this.flowId.length > 0) {
            flowName = this.flowId;
        } else {
            flowName = this.t('platform_chat.no_flow');
        }
        const branchLabel = this.branchId === 'base' ? this.t('platform_chat.base_branch') : this.branchId;
        const hasFlow = typeof this.flowId === 'string' && this.flowId.length > 0;
        const companyId = asString(this._activeCompanySel.value);
        const locale = asString(this._localeSel.value);
        const voiceReady = hasFlow && companyId !== '' && this._voiceBaseUrl !== '';

        return html`
            <div class="chat-breadcrumbs">
                <platform-breadcrumbs compact current-label=${flowName}></platform-breadcrumbs>
            </div>
            <page-header
                title=${flowName}
                subtitle=${branchLabel}
                actions-overflow="visible"
            >
                ${this._isMobile
                    ? html`
                          <platform-button
                              slot="leading"
                              variant="ghost"
                              icon-only
                              density="dense"
                              aria-label=${this.t('platform_chat.title_back_to_flows_list')}
                              title=${this.t('platform_chat.title_back_to_flows_list')}
                              @click=${this._onFlowsChatBack}
                          >
                              <platform-icon name="arrow-left" size="20"></platform-icon>
                          </platform-button>
                      `
                    : nothing}
                <div slot="actions">
                    ${this._isMobile
                        ? this._renderMobileActions(hasFlow)
                        : html`<div class="flow-chat-header-actions">${this._renderDesktopActions(hasFlow)}</div>`}
                </div>
            </page-header>
            ${this._isMobile ? html`<div class="chat-branch-hint">${branchLabel}</div>` : nothing}
            <div class="chat-workspace">
                <platform-chat
                    display="page"
                    profile="spa"
                    hide-header
                    flow-id=${this.flowId}
                    branch-id=${this.branchId}
                    .flowsBaseUrl=${'/flows'}
                    ?use-credentials=${true}
                    company-id=${companyId}
                    ?voice-enabled=${voiceReady}
                    voice-base-url=${this._voiceBaseUrl}
                    interface-locale=${locale || 'auto'}
                    @chat-state-changed=${() => this.requestUpdate()}
                    @chat-run-event=${this._onChatRunEvent}
                    @show-tracing=${this._onChatShowTracing}
                    @show-logs=${this._onChatShowLogs}
                    @show-durable-history=${this._onChatShowDurableHistory}
                    @browser-preview-open=${this._onBrowserPreviewOpen}
                    @humanitec-embed-voice-error=${this._onChatVoiceError}
                    @embed-toast=${this._onChatToast}
                ></platform-chat>
            </div>
        `;
    }
}

customElements.define('chat-page', ChatPage);

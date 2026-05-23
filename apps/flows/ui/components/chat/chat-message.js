/**
 * App-host adapter over the shared flows-chat message surface.
 */
import { html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flows-chat/flows-chat-message.js';
import { asArray, asString } from '../../_helpers/flows-resolvers.js';
import { resolveFlowVoiceHttpOrigin } from '../../_helpers/flow-voice-session.js';
import {
    readTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '@platform/lib/voice/tts-output-pref.js';
import './flows-chat-run-trace.js';

export class ChatMessage extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        role: { type: String },
        content: { type: String },
        timestamp: { type: String },
        streaming: { type: Boolean },
        reasoning: { type: String },
        activity: { type: String },
        toolCalls: { type: Array },
        toolResults: { type: Array },
        browserPreviews: { type: Array },
        error: { type: String },
        errorI18nKey: { type: String },
        inputRequired: { type: Object },
        operatorReply: { type: String },
        breakpoint: { type: Object },
        files: { type: Array },
        fileIds: { type: Array },
        taskId: { type: String },
        isLastUserMessage: { type: Boolean, attribute: 'is-last-user-message' },
        runTraceEntries: { type: Array },
        traceTaskId: { type: String },
        voicePlayGetHeaders: { attribute: false },
    };

    constructor() {
        super();
        this.role = 'user';
        this.content = '';
        this.timestamp = '';
        this.streaming = false;
        this.reasoning = '';
        this.activity = '';
        this.toolCalls = [];
        this.toolResults = [];
        this.browserPreviews = [];
        this.error = '';
        this.errorI18nKey = null;
        this.inputRequired = null;
        this.operatorReply = '';
        this.breakpoint = null;
        this.files = [];
        this.fileIds = [];
        this.taskId = '';
        this.isLastUserMessage = false;
        this.runTraceEntries = [];
        this.traceTaskId = '';
        this.voicePlayGetHeaders = null;
        this._i18nLocale = this.select((s) => s.i18n.locale);
        this._onTtsPrefBound = null;
        this._onTtsStorageBound = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._onTtsPrefBound = () => this.requestUpdate();
        this._onTtsStorageBound = (event) => {
            if (event.storageArea === window.localStorage && event.key === TTS_OUTPUT_STORAGE_KEY) {
                this.requestUpdate();
            }
        };
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefBound);
            window.addEventListener('storage', this._onTtsStorageBound);
        }
    }

    disconnectedCallback() {
        if (typeof window !== 'undefined') {
            if (this._onTtsPrefBound) {
                window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefBound);
                this._onTtsPrefBound = null;
            }
            if (this._onTtsStorageBound) {
                window.removeEventListener('storage', this._onTtsStorageBound);
                this._onTtsStorageBound = null;
            }
        }
        super.disconnectedCallback();
    }

    _labels() {
        return {
            breakpoint_continue: this.t('chat_message.breakpoint_continue'),
            breakpoint_view_state: this.t('chat_message.breakpoint_view_state'),
            role_user: this.t('chat_message.role_user'),
            role_assistant: this.t('chat_message.role_assistant'),
            role_operator: this.t('chat_message.role_operator'),
            role_system: this.t('chat_message.role_system'),
            operator_files: this.t('chat_message.operator_files'),
            thinking_status: this.t('chat_message.thinking_status'),
            thinking_aria: this.t('chat_message.thinking_aria'),
            tool_default_name: this.t('chat_message.tool_default_name'),
            tool_stack_aria: this.t('chat_message.tool_stack_aria', { names: '{names}' }),
            tool_hint_tool_name: this.t('chat_message.tool_hint_tool_name', { name: '{name}' }),
            tool_hint_args_label: this.t('chat_message.tool_hint_args_label'),
            tool_hint_result_label: this.t('chat_message.tool_hint_result_label'),
            show_tracing_title: this.t('chat_message.show_tracing_title'),
            show_run_trace_title: this.t('run_trace.section_title'),
            interrupt_operator_banner: this.t('chat_message.interrupt_operator_banner'),
            interrupt_oauth_banner: this.t('chat_message.interrupt_oauth_banner'),
            interrupt_oauth_button: this.t('chat_message.interrupt_oauth_button'),
            operator_reply_heading: this.t('chat_message.operator_reply_heading'),
            streaming_placeholder: this.t('chat_message.streaming_placeholder'),
            stream_incomplete: this.t('chat_message.stream_incomplete'),
        };
    }

    _locale() {
        const value = this._i18nLocale?.value;
        return typeof value === 'string' && value.length > 0 ? value : 'ru';
    }

    _voiceBaseUrlForAssistantPlay() {
        return readTtsOutputEnabled() ? resolveFlowVoiceHttpOrigin() : '';
    }

    _onComposeEdit(event) {
        event.stopPropagation();
        const text = asString(event.detail?.text);
        if (text.length === 0) {
            return;
        }
        this.dispatch('flows/chat/compose_edit', { text }, { source: 'local' });
    }

    _forwardEvent(event) {
        event.stopPropagation();
        this.emit(event.type, event.detail || {});
    }

    render() {
        const traceEntries = asArray(this.runTraceEntries);
        const showTrace = this.isLastUserMessage;
        return html`
            <flows-chat-message
                variant="app"
                flow-root="/flows"
                .role=${this.role}
                .content=${this.content}
                .timestamp=${asString(this.timestamp)}
                .locale=${this._locale()}
                ?streaming=${this.streaming}
                .reasoning=${asString(this.reasoning)}
                .activity=${asString(this.activity)}
                .toolCalls=${asArray(this.toolCalls)}
                .toolResults=${asArray(this.toolResults)}
                .browserPreviews=${asArray(this.browserPreviews)}
                .inputRequired=${this.inputRequired}
                .operatorReply=${asString(this.operatorReply)}
                .breakpoint=${this.breakpoint}
                .files=${asArray(this.files)}
                .fileIds=${asArray(this.fileIds)}
                .taskId=${asString(this.taskId)}
                .traceTaskId=${showTrace ? asString(this.traceTaskId) : ''}
                .error=${asString(this.error)}
                .errorI18nKey=${this.errorI18nKey != null && typeof this.errorI18nKey === 'string'
                    ? this.errorI18nKey
                    : ''}
                ?isLastUserMessage=${showTrace}
                ?runTraceAvailable=${traceEntries.length > 0}
                .labels=${this._labels()}
                .useCredentials=${true}
                .voiceBaseUrl=${this._voiceBaseUrlForAssistantPlay()}
                .getHeaders=${typeof this.voicePlayGetHeaders === 'function' ? this.voicePlayGetHeaders : null}
                @compose-edit=${this._onComposeEdit}
                @show-tracing=${this._forwardEvent}
                @continue-breakpoint=${this._forwardEvent}
                @view-breakpoint-state=${this._forwardEvent}
            >
                ${showTrace
                    ? html`
                          <flows-chat-run-trace
                              slot="run-trace"
                              .entries=${traceEntries}
                              ?compact=${true}
                              ?showSectionHeader=${true}
                          ></flows-chat-run-trace>
                      `
                    : nothing}
            </flows-chat-message>
        `;
    }
}

customElements.define('chat-message', ChatMessage);

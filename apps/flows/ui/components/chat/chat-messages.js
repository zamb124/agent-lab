/**
 * Контейнер списка сообщений чата
 */
import { html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { asArray, asString } from '../../_helpers/flows-resolvers.js';
import './flows-chat-run-trace.js';

export class ChatMessages extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                flex: 1;
                overflow-y: auto;
                padding: var(--space-6);
            }
            
            .messages-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-6);
                max-width: 900px;
                margin: 0 auto;
            }
            
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                min-height: 400px;
                text-align: center;
                color: var(--text-tertiary);
            }
            
            .empty-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: var(--space-6);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                color: var(--accent);
            }
            
            .empty-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .empty-text {
                font-size: var(--text-sm);
                max-width: 300px;
                line-height: var(--leading-relaxed);
            }
            .run-trace-slot {
                max-width: 900px;
                margin: 0 auto;
                width: 100%;
            }
        `
    ];

    static properties = {
        messages: { type: Array },
        loading: { type: Boolean },
        runTrace: { type: Array },
    };

    constructor() {
        super();
        this.messages = [];
        this.loading = false;
        this.runTrace = [];
    }

    get listEl() {
        return this.shadowRoot?.querySelector('.messages-list');
    }

    updated(changedProperties) {
        if (changedProperties.has('messages')) {
            this._scrollToBottom();
        }
    }

    _scrollToBottom() {
        requestAnimationFrame(() => {
            this.scrollTop = this.scrollHeight;
        });
    }

    _onShowTracing(e) {
        this.emit('show-tracing', e.detail);
    }

    render() {
        const trace = asArray(this.runTrace);
        if (this.messages.length === 0 && !this.loading && trace.length === 0) {
            return html`
                <div class="empty-state">
                    <platform-icon class="empty-icon" name="chat" size="64"></platform-icon>
                    <div class="empty-title">${this.t('chat_messages.empty_title')}</div>
                    <div class="empty-text">${this.t('chat_messages.empty_text')}</div>
                </div>
            `;
        }

        if (this.messages.length === 0 && !this.loading && trace.length > 0) {
            return html`
                <div class="messages-list">
                    <div class="run-trace-slot">
                        <flows-chat-run-trace .entries=${trace}></flows-chat-run-trace>
                    </div>
                </div>
            `;
        }

        return html`
            <div class="messages-list">
                ${repeat(
                    this.messages,
                    (m) => m.id,
                    (message) => html`
                        <chat-message
                            .role=${message.role}
                            .content=${message.content}
                            .timestamp=${asString(message.timestamp)}
                            ?streaming=${message.streaming}
                            .reasoning=${asString(message.reasoning)}
                            .toolCalls=${asArray(message.toolCalls)}
                            .toolResults=${asArray(message.toolResults)}
                            .inputRequired=${message.inputRequired}
                            .operatorReply=${asString(message.operatorReply)}
                            .breakpoint=${message.breakpoint}
                            .files=${asArray(message.files)}
                            .fileIds=${asArray(message.fileIds)}
                            .taskId=${asString(message.taskId)}
                            @show-tracing=${this._onShowTracing}
                        ></chat-message>
                    `
                )}
                ${trace.length > 0
                    ? html`
                          <div class="run-trace-slot">
                              <flows-chat-run-trace .entries=${trace}></flows-chat-run-trace>
                          </div>
                      `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('chat-messages', ChatMessages);

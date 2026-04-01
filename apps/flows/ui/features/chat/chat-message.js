/**
 * Компонент одного сообщения в чате
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class ChatMessage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .message {
                display: flex;
                gap: var(--space-4);
                animation: message-enter var(--duration-normal) var(--easing-default);
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
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
            }
            
            .message.user .avatar {
                background: var(--accent-gradient);
                border: none;
                color: white;
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
            }
            
            .message.assistant .avatar {
                background: var(--glass-solid-medium);
                color: var(--accent);
            }
            
            .message.system .avatar {
                background: var(--info-bg);
                color: var(--info);
            }
            
            .bubble {
                flex: 1;
                max-width: 70%;
                min-width: 0;
            }
            
            .message.user .bubble {
                display: flex;
                flex-direction: column;
                align-items: flex-end;
            }
            
            .content {
                padding: var(--space-4) var(--space-5);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle), var(--glass-inner-glow-subtle);
            }
            
            .message.user .content {
                background: var(--accent);
                border: none;
                color: white;
                border-bottom-right-radius: var(--radius-sm);
                box-shadow: 0 4px 16px rgba(16, 185, 129, 0.2);
            }
            
            .message.assistant .content {
                background: var(--glass-solid-medium);
                border-bottom-left-radius: var(--radius-sm);
            }
            
            .message.system .content {
                background: var(--info-bg);
                border-color: var(--info-border);
            }
            
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            
            .message.user .header {
                justify-content: flex-end;
            }
            
            .header-actions {
                display: flex;
                gap: var(--space-1);
                margin-left: auto;
            }
            
            .tracing-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                padding: 0;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tracing-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--accent);
                border-color: var(--accent);
            }
            
            .role {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            
            .message.user .role {
                color: rgba(255, 255, 255, 0.8);
            }
            
            .timestamp {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .message.user .timestamp {
                color: rgba(255, 255, 255, 0.6);
            }
            
            .text {
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-primary);
                word-wrap: break-word;
            }
            
            .message.user .text {
                color: white;
            }
            
            .text p {
                margin: 0 0 var(--space-3);
            }
            
            .text p:last-child {
                margin-bottom: 0;
            }
            
            .text code {
                font-family: var(--font-mono);
                font-size: 0.875em;
                padding: 3px 8px;
                background: rgba(0, 0, 0, 0.15);
                border-radius: var(--radius-sm);
            }
            
            .message.user .text code {
                background: rgba(255, 255, 255, 0.2);
            }
            
            .text pre {
                margin: var(--space-4) 0;
                padding: var(--space-4);
                background: var(--bg-primary);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                overflow-x: auto;
            }
            
            .text pre code {
                padding: 0;
                background: none;
            }
            
            .streaming .text::after {
                content: '▊';
                color: var(--accent);
                animation: blink 1s infinite;
            }
            
            @keyframes message-enter {
                from {
                    opacity: 0;
                    transform: translateY(12px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            @keyframes blink {
                50% { opacity: 0; }
            }
            
            .reasoning-container {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
            }
            
            .reasoning-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-3);
                cursor: pointer;
                user-select: none;
            }
            
            .reasoning-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            
            .reasoning-toggle {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .reasoning-content {
                font-size: var(--text-sm);
                line-height: var(--leading-relaxed);
                color: var(--text-secondary);
            }
            
            .reasoning-content.collapsed {
                display: none;
            }
            
            .tool-call, .tool-result {
                margin-top: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
            }
            
            .tool-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
                cursor: pointer;
            }
            
            .tool-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--accent);
            }
            
            .tool-content {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                background: var(--bg-primary);
                padding: var(--space-3);
                border-radius: var(--radius-sm);
                overflow-x: auto;
                max-height: 300px;
                overflow-y: auto;
            }
            
            .tool-content.collapsed {
                display: none;
            }
            
            .input-required {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--info-bg);
                border: 1px solid var(--info-border);
                border-radius: var(--radius-lg);
            }
            
            .input-required-text {
                font-size: var(--text-base);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }
            
            .breakpoint {
                margin-top: var(--space-4);
                padding: var(--space-4);
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
                border-radius: var(--radius-lg);
            }
            
            .breakpoint-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .breakpoint-icon {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--warning);
                flex-shrink: 0;
            }
            
            .breakpoint-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--warning);
            }
            
            .breakpoint-message {
                font-size: var(--text-sm);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }
            
            .breakpoint-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .files-container {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            
            .file-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
            
            .file-image {
                width: 48px;
                height: 48px;
                object-fit: cover;
                border-radius: var(--radius-sm);
            }
            
            .file-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }
            
            .file-size {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `
    ];

    static properties = {
        role: { type: String },
        content: { type: String },
        timestamp: { type: String },
        streaming: { type: Boolean },
        reasoning: { type: String },
        toolCalls: { type: Array },
        toolResults: { type: Array },
        inputRequired: { type: Object },
        breakpoint: { type: Object },
        files: { type: Array },
        expandedStates: { type: Object },
        taskId: { type: String },
    };

    constructor() {
        super();
        this.role = 'user';
        this.content = '';
        this.timestamp = '';
        this.streaming = false;
        this.reasoning = '';
        this.toolCalls = [];
        this.toolResults = [];
        this.inputRequired = null;
        this.breakpoint = null;
        this.files = [];
        this.expandedStates = new Map();
        this.expandedStates.set('reasoning', false);
        this.taskId = '';
    }

    _escapeRegex(s) {
        return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    _getRoleName() {
        switch (this.role) {
            case 'user': return this.i18n.t('chat_message.role_user');
            case 'assistant': return this.i18n.t('chat_message.role_assistant');
            case 'system': return this.i18n.t('chat_message.role_system');
            default: return this.role;
        }
    }

    _getAvatarIcon() {
        switch (this.role) {
            case 'user': return 'user';
            case 'assistant': return 'bot';
            case 'system': return 'info';
            default: return 'chat';
        }
    }

    _renderContent() {
        if (window.marked && this.content) {
            return unsafeHTML(window.marked.parse(this.content));
        }
        return this.content;
    }

    _toggleReasoning() {
        const current = this.expandedStates.get('reasoning') || false;
        this.expandedStates.set('reasoning', !current);
        this.expandedStates = new Map(this.expandedStates);
    }

    _parseReasoningStructure(text) {
        if (!text) return '';

        const labelKeys = [
            'chat_message.reasoning_section_observation',
            'chat_message.reasoning_section_analysis',
            'chat_message.reasoning_section_plan',
            'chat_message.reasoning_section_action',
        ];

        let html = text;

        for (const labelKey of labelKeys) {
            const label = this.i18n.t(labelKey);
            const regex = new RegExp(`\\*\\*${this._escapeRegex(label)}:\\*\\*\\s*`, 'g');
            html = html.replace(
                regex,
                `<div style="font-weight: bold; margin-top: 12px; color: var(--accent);">${label}</div>`
            );
        }

        if (window.marked) {
            return unsafeHTML(window.marked.parse(html));
        }
        return html;
    }

    _renderReasoning() {
        if (!this.reasoning) return '';
        
        return html`
            <div class="reasoning-container">
                <div class="reasoning-header" @click=${this._toggleReasoning}>
                    <span class="reasoning-title">${this.i18n.t('chat_message.reasoning_title')}</span>
                    <span class="reasoning-toggle">${this.expandedStates.get('reasoning') ? '▼' : '▶'}</span>
                </div>
                <div class="reasoning-content ${this.expandedStates.get('reasoning') ? '' : 'collapsed'}">
                    ${this._parseReasoningStructure(this.reasoning)}
                </div>
            </div>
        `;
    }

    _renderToolCalls() {
        if (!this.toolCalls || this.toolCalls.length === 0) return '';
        
        return this.toolCalls.map((toolCall, index) => {
            const isExpanded = this.expandedStates.get(`toolCall${index}`) !== false;
            
            return html`
                <div class="tool-call">
                    <div class="tool-header" @click=${() => this._toggleToolCall(index)}>
                        <span class="tool-name">${this.i18n.t('chat_message.tool_call_label', { name: toolCall.name || 'Tool' })}</span>
                        <span class="reasoning-toggle">${isExpanded ? '▼' : '▶'}</span>
                    </div>
                    <div class="tool-content ${isExpanded ? '' : 'collapsed'}">
                        ${JSON.stringify(toolCall.arguments || toolCall.args || {}, null, 2)}
                    </div>
                </div>
            `;
        });
    }

    _toggleToolCall(index) {
        const key = `toolCall${index}`;
        const current = this.expandedStates.get(key);
        this.expandedStates.set(key, current === false ? true : false);
        this.expandedStates = new Map(this.expandedStates);
    }

    _renderToolResults() {
        if (!this.toolResults || this.toolResults.length === 0) return '';
        
        return this.toolResults.map((result, index) => {
            const isExpanded = this.expandedStates.get(`toolResult${index}`) !== false;
            
            return html`
                <div class="tool-result">
                    <div class="tool-header" @click=${() => this._toggleToolResult(index)}>
                        <span class="tool-name">${this.i18n.t('chat_message.tool_result_label', { name: result.name || 'Result' })}</span>
                        <span class="reasoning-toggle">${isExpanded ? '▼' : '▶'}</span>
                    </div>
                    <div class="tool-content ${isExpanded ? '' : 'collapsed'}">
                        ${typeof result.result === 'string' ? result.result : JSON.stringify(result.result, null, 2)}
                    </div>
                </div>
            `;
        });
    }

    _toggleToolResult(index) {
        const key = `toolResult${index}`;
        const current = this.expandedStates.get(key);
        this.expandedStates.set(key, current === false ? true : false);
        this.expandedStates = new Map(this.expandedStates);
    }

    _renderInputRequired() {
        if (!this.inputRequired) return '';
        
        return html`
            <div class="input-required">
                <div class="input-required-text">
                    ${window.marked ? unsafeHTML(window.marked.parse(this.inputRequired.question)) : this.inputRequired.question}
                </div>
            </div>
        `;
    }

    _renderBreakpoint() {
        if (!this.breakpoint) return '';
        
        return html`
            <div class="breakpoint">
                <div class="breakpoint-header">
                    <span class="breakpoint-icon" aria-hidden="true"></span>
                    <span class="breakpoint-title">Breakpoint: ${this.breakpoint.nodeId}</span>
                </div>
                <div class="breakpoint-message">
                    ${window.marked ? unsafeHTML(window.marked.parse(this.breakpoint.message)) : this.breakpoint.message}
                </div>
                <div class="breakpoint-actions">
                    <button class="btn" @click=${this._continueBreakpoint}>${this.i18n.t('chat_message.breakpoint_continue')}</button>
                    <button class="btn" @click=${this._viewBreakpointState}>${this.i18n.t('chat_message.breakpoint_view_state')}</button>
                </div>
            </div>
        `;
    }

    _continueBreakpoint() {
        this.emit('continue-breakpoint', { breakpoint: this.breakpoint });
    }

    _viewBreakpointState() {
        this.emit('view-breakpoint-state', { breakpoint: this.breakpoint });
    }

    _showTracing() {
        if (this.taskId) {
            this.emit('show-tracing', { taskId: this.taskId });
        }
    }

    _renderFiles() {
        if (!this.files || this.files.length === 0) return '';
        
        return html`
            <div class="files-container">
                ${this.files.map(file => this._renderFile(file))}
            </div>
        `;
    }

    _renderFile(file) {
        const isImage = file.type && file.type.startsWith('image/');
        
        return html`
            <div class="file-item">
                ${isImage ? html`
                    <platform-icon name="doc-detail" size="20"></platform-icon>
                ` : html`
                    <platform-icon name="file" size="20"></platform-icon>
                `}
                <div>
                    <div class="file-name">${file.name}</div>
                    ${file.size ? html`<div class="file-size">${this._formatFileSize(file.size)}</div>` : ''}
                </div>
            </div>
        `;
    }

    _formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    render() {
        const classes = {
            'message': true,
            [this.role]: true,
            'streaming': this.streaming,
        };

        return html`
            <div class=${classMap(classes)}>
                <div class="avatar">
                    <platform-icon name=${this._getAvatarIcon()} size="18"></platform-icon>
                </div>
                <div class="bubble">
                    <div class="content">
                        <div class="header">
                            <span class="role">${this._getRoleName()}</span>
                            ${this.timestamp ? html`<span class="timestamp">${this.timestamp}</span>` : ''}
                            ${this.role === 'assistant' && this.taskId && !this.streaming ? html`
                                <div class="header-actions">
                                    <button class="tracing-btn" @click=${this._showTracing} title=${this.i18n.t('chat_message.show_tracing_title')}>
                                        <platform-icon name="terminal" size="14"></platform-icon>
                                    </button>
                                </div>
                            ` : ''}
                        </div>
                        
                        ${this._renderFiles()}
                        ${this._renderReasoning()}
                        ${this._renderToolCalls()}
                        ${this._renderToolResults()}
                        
                        ${this.content ? html`<div class="text">${this._renderContent()}</div>` : ''}
                        
                        ${this._renderInputRequired()}
                        ${this._renderBreakpoint()}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('chat-message', ChatMessage);

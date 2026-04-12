/**
 * Модальное окно с деталями span
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class SpanDetailsModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 800px;
            }
            
            .span-details-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-height: 300px;
            }
            
            .span-detail-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .section-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .detail-row {
                display: flex;
                gap: var(--space-3);
                padding: var(--space-2);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .detail-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                min-width: 120px;
            }
            
            .detail-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                flex: 1;
                word-break: break-all;
            }
            
            .status-ok {
                color: var(--success);
            }
            
            .status-error {
                color: var(--error);
            }
            
            .attributes-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .attribute-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .attribute-key {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .attribute-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .state-snapshot-viewer {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .snapshot-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            
            .snapshot-key {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .snapshot-value {
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .raw-json-btn {
                padding: var(--space-2) var(--space-4);
                background: var(--glass-solid-medium);
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .raw-json-btn:hover {
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-subtle);
            }
            
            .llm-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .llm-tabs {
                display: flex;
                gap: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
                padding-bottom: var(--space-2);
            }
            
            .llm-tab {
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .llm-tab:hover {
                background: var(--glass-solid-medium);
            }
            
            .llm-tab.active {
                background: var(--accent);
                color: white;
            }
            
            .llm-content {
                display: none;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .llm-content.active {
                display: flex;
            }
            
            .chat-message {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                border-radius: var(--radius-md);
            }
            
            .chat-message.system {
                background: rgba(139, 92, 246, 0.1);
                border-left: 3px solid #8b5cf6;
            }
            
            .chat-message.user {
                background: rgba(59, 130, 246, 0.1);
                border-left: 3px solid #3b82f6;
            }
            
            .chat-message.assistant {
                background: rgba(153, 166, 249, 0.1);
                border-left: 3px solid var(--accent);
            }
            
            .chat-message.tool {
                background: rgba(245, 158, 11, 0.1);
                border-left: 3px solid #f59e0b;
            }
            
            .message-role {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: var(--text-tertiary);
            }
            
            .message-content {
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .tool-calls-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            
            .tool-call-item {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
                background: rgba(245, 158, 11, 0.1);
                border-radius: var(--radius-sm);
                border-left: 2px solid #f59e0b;
            }
            
            .tool-call-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: #f59e0b;
            }
            
            .tool-call-args {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                white-space: pre-wrap;
            }
            
            .tools-schema-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .tool-schema-item {
                padding: var(--space-2);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
            }
            
            .tool-schema-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .tool-schema-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            /* Responsive - Tablet */
            @media (max-width: 768px) {
                :host {
                    --modal-max-width: 95vw;
                }
                
                .detail-row {
                    flex-direction: column;
                    gap: var(--space-1);
                }
                
                .detail-label {
                    min-width: auto;
                }
            }

            /* Responsive - Mobile */
            @media (max-width: 480px) {
                .span-details-container {
                    gap: var(--space-3);
                    min-height: 200px;
                }
                
                .attribute-row,
                .snapshot-field {
                    padding: var(--space-2);
                }
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        span: { type: Object },
        _llmTab: { type: String, state: true },
    };

    constructor() {
        super();
        this.span = null;
        this._llmTab = 'request';
    }

    connectedCallback() {
        super.connectedCallback();
        this.title = this.i18n.t('span_details.modal_title');
    }
    
    _isLlmSpan() {
        return this.span?.operation_name?.startsWith('llm.');
    }
    
    _getLlmRequest() {
        const attrs = this._getAttrs();
        const requestStr = attrs['platform.llm.request'];
        if (!requestStr) return null;
        try {
            return JSON.parse(requestStr);
        } catch {
            return null;
        }
    }
    
    _getLlmResponse() {
        const attrs = this._getAttrs();
        const responseStr = attrs['platform.llm.response'];
        if (!responseStr) return null;
        try {
            return JSON.parse(responseStr);
        } catch {
            return null;
        }
    }
    
    _getAttrs() {
        let attrs = this.span?.attributes || {};
        if (typeof attrs === 'string') {
            try { attrs = JSON.parse(attrs); } catch { attrs = {}; }
        }
        return (typeof attrs === 'object' && attrs !== null && !Array.isArray(attrs)) ? attrs : {};
    }
    
    _setLlmTab(tab) {
        this._llmTab = tab;
    }
    
    _extractMessageContent(msg) {
        // OpenAI format: content as string
        if (typeof msg.content === 'string') {
            return msg.content;
        }
        
        // OpenAI format: content as array of parts
        if (Array.isArray(msg.content)) {
            return msg.content.map(c => c.text || c.content || JSON.stringify(c)).join('\n');
        }
        
        // A2A format: parts array
        if (Array.isArray(msg.parts)) {
            return msg.parts.map(p => {
                if (typeof p === 'string') return p;
                if (p.root?.text) return p.root.text;
                if (p.text) return p.text;
                if (p.root?.data) return JSON.stringify(p.root.data, null, 2);
                if (p.data) return JSON.stringify(p.data, null, 2);
                return JSON.stringify(p, null, 2);
            }).join('\n');
        }
        
        // Fallback
        if (msg.content) {
            return JSON.stringify(msg.content, null, 2);
        }
        
        return '';
    }
    
    _renderMessage(msg) {
        const role = (msg.role || 'unknown').toLowerCase();
        const content = this._extractMessageContent(msg);
        const toolCalls = msg.tool_calls || [];
        
        // Tool result message
        if (msg.tool_call_id) {
            return html`
                <div class="chat-message tool">
                    <span class="message-role">tool result (${msg.tool_call_id})</span>
                    <div class="message-content">${content}</div>
                </div>
            `;
        }
        
        return html`
            <div class="chat-message ${role}">
                <span class="message-role">${role}</span>
                ${content ? html`<div class="message-content">${content}</div>` : ''}
                ${toolCalls.length > 0 ? html`
                    <div class="tool-calls-list">
                        ${toolCalls.map(tc => html`
                            <div class="tool-call-item">
                                <span class="tool-call-name">${tc.name || tc.function?.name || 'unknown'}</span>
                                <span class="tool-call-args">${JSON.stringify(tc.arguments || tc.function?.arguments || {}, null, 2)}</span>
                            </div>
                        `)}
                    </div>
                ` : ''}
            </div>
        `;
    }
    
    _getSystemPrompt() {
        const request = this._getLlmRequest();
        if (!request?.messages) return null;
        
        const systemMsg = request.messages.find(m => 
            (m.role || '').toLowerCase() === 'system'
        );
        
        return systemMsg ? this._extractMessageContent(systemMsg) : null;
    }
    
    _getNonSystemMessages() {
        const request = this._getLlmRequest();
        if (!request?.messages) return [];
        
        return request.messages.filter(m => 
            (m.role || '').toLowerCase() !== 'system'
        );
    }
    
    _renderLlmSection() {
        const request = this._getLlmRequest();
        const response = this._getLlmResponse();
        
        if (!request && !response) return '';
        
        const hasResponseFormat = !!request?.response_format;
        const hasTools = request?.tools?.length > 0;
        const systemPrompt = this._getSystemPrompt();
        const messages = this._getNonSystemMessages();
        
        // Показываем prompt по умолчанию если есть
        if (systemPrompt && this._llmTab === 'request') {
            this._llmTab = 'prompt';
        }
        
        return html`
            <div class="span-detail-section">
                <h3 class="section-title">${this.i18n.t('span_details.section_llm')}</h3>
                <div class="llm-section">
                    <div class="llm-tabs">
                        ${systemPrompt ? html`
                            <button 
                                class="llm-tab ${this._llmTab === 'prompt' ? 'active' : ''}"
                                @click=${() => this._setLlmTab('prompt')}
                            >${this.i18n.t('span_details.tab_prompt')}</button>
                        ` : ''}
                        <button 
                            class="llm-tab ${this._llmTab === 'request' ? 'active' : ''}"
                            @click=${() => this._setLlmTab('request')}
                        >${this.i18n.t('span_details.tab_messages', { count: messages.length })}</button>
                        ${hasTools ? html`
                            <button 
                                class="llm-tab ${this._llmTab === 'tools' ? 'active' : ''}"
                                @click=${() => this._setLlmTab('tools')}
                            >${this.i18n.t('span_details.tab_tools', { count: request?.tools?.length || 0 })}</button>
                        ` : ''}
                        ${hasResponseFormat ? html`
                            <button 
                                class="llm-tab ${this._llmTab === 'schema' ? 'active' : ''}"
                                @click=${() => this._setLlmTab('schema')}
                            >${this.i18n.t('span_details.structured_output')}</button>
                        ` : ''}
                        <button 
                            class="llm-tab ${this._llmTab === 'response' ? 'active' : ''}"
                            @click=${() => this._setLlmTab('response')}
                        >${this.i18n.t('span_details.tab_response')}</button>
                    </div>
                    
                    ${systemPrompt ? html`
                        <div class="llm-content ${this._llmTab === 'prompt' ? 'active' : ''}">
                            <div class="chat-message system">
                                <span class="message-role">${this.i18n.t('span_details.role_system_prompt')}</span>
                                <div class="message-content">${systemPrompt}</div>
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="llm-content ${this._llmTab === 'request' ? 'active' : ''}">
                        ${messages.length > 0 
                            ? messages.map(msg => this._renderMessage(msg)) 
                            : html`<div class="empty-state">${this.i18n.t('span_details.empty_messages')}</div>`}
                    </div>
                    
                    ${hasTools ? html`
                        <div class="llm-content ${this._llmTab === 'tools' ? 'active' : ''}">
                            <div class="tools-schema-list">
                                ${request?.tools?.map(tool => html`
                                    <div class="tool-schema-item">
                                        <div class="tool-schema-name">${tool.function?.name || tool.name || 'unknown'}</div>
                                        <div class="tool-schema-desc">${tool.function?.description || tool.description || ''}</div>
                                    </div>
                                `)}
                            </div>
                        </div>
                    ` : ''}
                    
                    ${hasResponseFormat ? html`
                        <div class="llm-content ${this._llmTab === 'schema' ? 'active' : ''}">
                            <div class="attribute-row">
                                <span class="attribute-key">JSON Schema</span>
                                <pre class="attribute-value">${JSON.stringify(request.response_format, null, 2)}</pre>
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="llm-content ${this._llmTab === 'response' ? 'active' : ''}">
                        ${response ? html`
                            ${response.content ? html`
                                <div class="chat-message assistant">
                                    <span class="message-role">${this.i18n.t('span_details.role_assistant')}</span>
                                    <div class="message-content">${response.content}</div>
                                </div>
                            ` : ''}
                            ${response.tool_calls?.length > 0 ? html`
                                <div class="tool-calls-list">
                                    ${response.tool_calls.map(tc => html`
                                        <div class="tool-call-item">
                                            <span class="tool-call-name">${tc.name || 'unknown'}</span>
                                            <span class="tool-call-args">${JSON.stringify(tc.arguments || {}, null, 2)}</span>
                                        </div>
                                    `)}
                                </div>
                            ` : ''}
                        ` : this.i18n.t('span_details.no_response_data')}
                    </div>
                </div>
            </div>
        `;
    }

    _showRawJson() {
        const modal = document.createElement('raw-json-modal');
        modal.data = this.span;
        modal.title = this.i18n.t('span_details.raw_json_title', {
            name: this.span.operation_name || 'unknown',
        });
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    renderHeader() {
        return this.title;
    }

    renderHeaderActions() {
        return html`
            <button class="header-btn" @click=${this._showRawJson} title=${this.i18n.t('span_details.raw_json_button_title')}>
                { }
            </button>
        `;
    }

    renderBody() {
        if (!this.span) {
            return html`<p>${this.i18n.t('span_details.empty_span')}</p>`;
        }

        const operationName = this.span.operation_name || 'unknown';
        const kind = this.span.kind || 'UNKNOWN';
        const status = this.span.status || 'OK';
        const duration = this.span.duration_ms || 0;
        const startTime = this.span.start_time || '';
        const endTime = this.span.end_time || '';
        
        const attrs = this._getAttrs();

        const snapshot = attrs['platform.state.snapshot'];
        let snapshotFields = [];
        if (snapshot) {
            try {
                const parsed = typeof snapshot === 'string' ? JSON.parse(snapshot) : snapshot;
                snapshotFields = Object.entries(parsed);
            } catch (e) {
                console.warn('Failed to parse snapshot:', e);
            }
        }

        const attrsToHide = [
            'platform.state.snapshot',
            'platform.llm.request',
            'platform.llm.response'
        ];
        const attrsWithoutHidden = { ...attrs };
        attrsToHide.forEach(key => delete attrsWithoutHidden[key]);
        const attributesList = Object.entries(attrsWithoutHidden);
        
        const isLlmSpan = this._isLlmSpan();

        return html`
            <div class="span-details-container">
                <div class="span-detail-section">
                    <h3 class="section-title">${this.i18n.t('span_details.section_main')}</h3>
                    <div class="detail-row">
                        <span class="detail-label">${this.i18n.t('span_details.label_operation')}</span>
                        <span class="detail-value">${operationName}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">${this.i18n.t('span_details.label_kind')}</span>
                        <span class="detail-value">${kind}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">${this.i18n.t('span_details.label_status')}</span>
                        <span class="detail-value status-${status.toLowerCase()}">${status}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">${this.i18n.t('span_details.label_duration')}</span>
                        <span class="detail-value">${duration}ms</span>
                    </div>
                    ${startTime ? html`
                        <div class="detail-row">
                            <span class="detail-label">${this.i18n.t('span_details.label_start_time')}</span>
                            <span class="detail-value">${startTime}</span>
                        </div>
                    ` : ''}
                    ${endTime ? html`
                        <div class="detail-row">
                            <span class="detail-label">${this.i18n.t('span_details.label_end_time')}</span>
                            <span class="detail-value">${endTime}</span>
                        </div>
                    ` : ''}
                </div>

                ${this._renderLlmSection()}

                ${attributesList.length > 0 ? html`
                    <div class="span-detail-section">
                        <h3 class="section-title">${this.i18n.t('span_details.section_attributes')}</h3>
                        <div class="attributes-list">
                            ${attributesList.map(([key, value]) => html`
                                <div class="attribute-row">
                                    <span class="attribute-key">${key}</span>
                                    <span class="attribute-value">${
                                        typeof value === 'object' 
                                            ? JSON.stringify(value, null, 2)
                                            : String(value)
                                    }</span>
                                </div>
                            `)}
                        </div>
                    </div>
                ` : ''}

                ${snapshotFields.length > 0 ? html`
                    <div class="span-detail-section">
                        <h3 class="section-title">State Snapshot</h3>
                        <div class="state-snapshot-viewer">
                            ${snapshotFields.map(([key, value]) => html`
                                <div class="snapshot-field">
                                    <span class="snapshot-key">${key}</span>
                                    <span class="snapshot-value">${
                                        typeof value === 'object' 
                                            ? JSON.stringify(value, null, 2)
                                            : String(value)
                                    }</span>
                                </div>
                            `)}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('span-details-modal', SpanDetailsModal);

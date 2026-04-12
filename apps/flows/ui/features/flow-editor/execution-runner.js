/**
 * ExecutionRunner - запуск агента и SSE streaming
 * Отображает статусы выполнения нод на canvas
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class ExecutionRunner extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .runner-panel {
                display: flex;
                flex-direction: column;
                height: 100%;
                border-top: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
            }
            
            .runner-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .runner-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .runner-status {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--text-tertiary);
            }
            
            .status-dot.running {
                background: var(--warning);
                animation: pulse 1s infinite;
            }
            
            .status-dot.completed {
                background: var(--success);
            }
            
            .status-dot.error {
                background: var(--error);
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            .runner-body {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-3);
            }
            
            .input-section {
                margin-bottom: var(--space-3);
            }
            
            .input-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }
            
            .input-textarea {
                width: 100%;
                min-height: 60px;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                resize: vertical;
                outline: none;
            }
            
            .input-textarea:focus {
                border-color: var(--accent);
            }
            
            .run-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: white;
                background: var(--accent);
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .run-btn:hover {
                background: var(--accent-hover);
            }
            
            .run-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            
            .run-btn.stop {
                background: var(--error);
            }
            
            .output-section {
                margin-top: var(--space-3);
            }
            
            .output-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }
            
            .output-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .output-clear {
                font-size: var(--text-xs);
                color: var(--accent);
                background: none;
                border: none;
                cursor: pointer;
            }
            
            .output-content {
                padding: var(--space-3);
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                background: var(--bg-primary);
                border-radius: var(--radius-md);
                min-height: 100px;
                max-height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .event-log {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            
            .event-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-1) 0;
                font-size: var(--text-xs);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .event-time {
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            
            .event-node {
                color: var(--accent);
                font-weight: var(--font-medium);
                flex-shrink: 0;
            }
            
            .event-message {
                color: var(--text-secondary);
                flex: 1;
            }
        `
    ];

    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        status: { type: String },
        output: { type: String },
        events: { type: Array },
    };

    constructor() {
        super();
        this.flowId = '';
        this.status = 'idle';
        this._input = '';
        this.output = '';
        this.events = [];
        this._contextId = null;
        this._taskId = null;
        this._eventSource = null;
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopExecution();
    }

    async _startExecution() {
        if (!this.flowId || !this._input.trim()) return;
        
        this.status = 'running';
        this.output = '';
        this.events = [];
        
        const contextId = `ctx_${Date.now()}`;
        const taskId = `task_${Date.now()}`;
        this._contextId = contextId;
        this._taskId = taskId;

        this.emit('execution-started', { contextId, taskId });

        const baseUrl = window.__BASE_URL__ || '';
        const url = new URL(`${baseUrl}/a2a/${this.flowId}/stream`, window.location.origin);
        url.searchParams.set('message', this._input);
        url.searchParams.set('context_id', contextId);

        this._eventSource = new EventSource(url.toString());
        
        this._eventSource.onmessage = (event) => {
            this._handleSSEMessage(event);
        };

        this._eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            this.status = 'error';
            this._addEvent('system', this.i18n.t('canvas_runner.sse_connection_error'));
            this._stopExecution();
        };
    }

    _handleSSEMessage(event) {
        const data = JSON.parse(event.data);
        
        if (data.type === 'artifact-update') {
            const parts = data.artifact?.parts || [];
            for (const part of parts) {
                if (part.type === 'text') {
                    this.output += part.text || '';
                }
            }
        }
        
        if (data.type === 'status-update') {
            const status = data.status?.state;
            const nodeId = data.metadata?.current_node;
            
            if (nodeId) {
                let nodeStatus = 'running';
                if (status === 'completed') nodeStatus = 'completed';
                if (status === 'failed') nodeStatus = 'error';
                
                this.emit('node-status-changed', { nodeId, status: nodeStatus });
                this._addEvent(nodeId, status);
            }
            
            if (status === 'completed' || status === 'failed') {
                this.status = status === 'completed' ? 'completed' : 'error';
                this._stopExecution();
            }
        }
    }

    _addEvent(nodeId, message) {
        const time = new Date().toLocaleTimeString();
        this.events = [...this.events, { time, nodeId, message }];
    }

    _stopExecution() {
        if (this._eventSource) {
            this._eventSource.close();
            this._eventSource = null;
        }
        
        if (this.status === 'running') {
            this.status = 'idle';
        }
        
        this.emit('execution-stopped');
    }

    _clearOutput() {
        this.output = '';
        this.events = [];
    }

    _onInputChange(e) {
        this._input = e.target.value;
    }

    render() {
        const isRunning = this.status === 'running';
        
        return html`
            <div class="runner-panel">
                <div class="runner-header">
                    <span class="runner-title">${this.i18n.t('execution_panel.sidebar_run_title')}</span>
                    <div class="runner-status">
                        <div class="status-dot ${this.status}"></div>
                        <span>${this.status}</span>
                    </div>
                </div>
                
                <div class="runner-body">
                    <div class="input-section">
                        <div class="input-label">${this.i18n.t('execution_panel.label_input')}</div>
                        <textarea 
                            class="input-textarea"
                            .value=${this._input}
                            @input=${this._onInputChange}
                            placeholder=${this.i18n.t('execution_panel.placeholder_message')}
                            ?disabled=${isRunning}
                        ></textarea>
                    </div>
                    
                    <button 
                        class="run-btn ${isRunning ? 'stop' : ''}"
                        @click=${isRunning ? this._stopExecution : this._startExecution}
                        ?disabled=${!this._input.trim() && !isRunning}
                    >
                        ${isRunning
                            ? html`<platform-icon name="stop" size="16"></platform-icon> ${this.i18n.t('execution_panel.stop')}`
                            : html`<platform-icon name="play" size="16"></platform-icon> ${this.i18n.t('execution_panel.run_start')}`
                        }
                    </button>
                    
                    ${this.output || this.events.length > 0 ? html`
                        <div class="output-section">
                            <div class="output-header">
                                <span class="output-label">${this.i18n.t('execution_panel.label_output')}</span>
                                <button class="output-clear" @click=${this._clearOutput}>${this.i18n.t('execution_panel.clear')}</button>
                            </div>
                            <div class="output-content">
                                ${this.output || this.i18n.t('execution_panel.waiting_for_response')}
                            </div>
                            
                            ${this.events.length > 0 ? html`
                                <div class="event-log">
                                    ${this.events.map(evt => html`
                                        <div class="event-item">
                                            <span class="event-time">${evt.time}</span>
                                            <span class="event-node">${evt.nodeId}</span>
                                            <span class="event-message">${evt.message}</span>
                                        </div>
                                    `)}
                                </div>
                            ` : ''}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('execution-runner', ExecutionRunner);


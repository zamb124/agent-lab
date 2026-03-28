/**
 * EditorHeader - header редактора flow
 * Кнопка назад, название flow, Draft badge, кнопки действий
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class EditorHeader extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .header {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-subtle);
                height: 56px;
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .back-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                border-radius: var(--radius-md);
                background: transparent;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .back-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            
            .flow-name-input {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                background: transparent;
                border: none;
                outline: none;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                min-width: 200px;
            }
            
            .flow-name-input:hover {
                background: var(--glass-tint-subtle);
            }
            
            .flow-name-input:focus {
                background: var(--glass-tint-medium);
            }
            
            .status-badge {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-sm);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            .header-center {
                flex: 1;
                display: flex;
                justify-content: center;
                gap: var(--space-2);
            }
            
            .mode-toggle {
                display: flex;
                align-items: center;
                padding: var(--space-1);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-full);
                gap: var(--space-1);
            }
            
            .mode-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .mode-btn.active {
                background: var(--bg-elevated);
                color: var(--text-primary);
                box-shadow: var(--glass-shadow-subtle);
            }

            .mode-btn.active.agent-stop {
                background: var(--bg-elevated);
                color: var(--error, #ef4444);
                box-shadow: var(--glass-shadow-subtle);
            }

            .mode-btn.active.agent-stop:hover {
                background: var(--error-bg, rgba(239, 68, 68, 0.12));
                color: var(--error, #ef4444);
            }
            
            .mode-btn:hover:not(.active) {
                color: var(--text-secondary);
            }
            
            .header-right {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .header-btn {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .header-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            
            .header-btn.primary {
                background: var(--accent);
                color: white;
            }
            
            .header-btn.primary:hover {
                background: var(--accent-hover);
            }
            
            .header-btn.primary:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            
            .icon-btn {
                width: 36px;
                height: 36px;
                padding: 0;
                justify-content: center;
            }
        `
    ];

    static properties = {
        flowName: { type: String, attribute: 'flow-name' },
        saving: { type: Boolean },
        mode: { type: String },
        agentExecutionRunning: { type: Boolean, attribute: 'agent-execution-running' },
    };

    constructor() {
        super();
        this.flowName = 'New Flow';
        this.saving = false;
        this.mode = 'visual';
        this.agentExecutionRunning = false;
    }

    getFlowName() {
        const root = this.shadowRoot || this;
        const input = root.querySelector('.flow-name-input');
        return input?.value || this.flowName;
    }

    _onNameChange(e) {
        this.emit('name-changed', { name: e.target.value });
    }

    _onBack() {
        this.emit('close');
    }

    _onSave() {
        this.emit('save');
    }

    _setMode(mode) {
        this.mode = mode;
        this.emit('mode-changed', { mode });
    }

    _onRunModeButtonClick(e) {
        if (this.agentExecutionRunning) {
            e.preventDefault();
            e.stopPropagation();
            this.emit('stop-agent-requested');
            return;
        }
        this._setMode('run');
    }

    _onShowCode() {
        this.emit('show-code');
    }

    render() {
        return html`
            <header class="header">
                <div class="header-left">
                    <button class="back-btn" @click=${this._onBack} title="Назад">
                        <platform-icon name="arrow-left" size="20"></platform-icon>
                    </button>
                    
                    <input
                        type="text"
                        class="flow-name-input"
                        .value=${this.flowName}
                        @change=${this._onNameChange}
                        placeholder="Flow name"
                    />
                    
                    <span class="status-badge">Draft</span>
                </div>
                
                <div class="header-center">
                    <div class="mode-toggle">
                        <button 
                            type="button"
                            class="mode-btn ${this.mode === 'visual' ? 'active' : ''}"
                            @click=${() => this._setMode('visual')}
                            title="Visual Editor"
                        >
                            <platform-icon name="edit" size="18"></platform-icon>
                        </button>
                        <button 
                            type="button"
                            class="mode-btn ${this.mode === 'run' ? 'active' : ''} ${this.agentExecutionRunning ? 'agent-stop' : ''}"
                            @click=${this._onRunModeButtonClick}
                            title=${this.agentExecutionRunning ? 'Остановить' : 'Run'}
                        >
                            <platform-icon
                                name="${this.agentExecutionRunning ? 'stop' : 'play'}"
                                size="18"
                            ></platform-icon>
                        </button>
                    </div>
                </div>
                
                <div class="header-right">
                    <button class="header-btn" @click=${this._onShowCode} title="Code">
                        <platform-icon name="code" size="16"></platform-icon>
                        Code
                    </button>
                    
                    <button 
                        class="header-btn primary"
                        @click=${this._onSave}
                        ?disabled=${this.saving}
                    >
                        ${this.saving 
                            ? html`<platform-spinner size="16"></platform-spinner>`
                            : html`<platform-icon name="save" size="16"></platform-icon>`
                        }
                        Publish
                    </button>
                </div>
            </header>
        `;
    }
}

customElements.define('editor-header', EditorHeader);


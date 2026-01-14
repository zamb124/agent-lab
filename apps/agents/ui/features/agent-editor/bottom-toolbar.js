/**
 * BottomToolbar - плавающий toolbar внизу canvas
 * Инструменты: курсор, добавить ноду, undo/redo
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AgentsStore } from '../../store/agents.store.js';

export class BottomToolbar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                bottom: var(--space-4);
                left: 50%;
                transform: translateX(-50%);
                z-index: 10;
            }
            
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2);
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-full);
                box-shadow: var(--glass-shadow-medium);
            }
            
            .toolbar-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border-radius: var(--radius-full);
                background: transparent;
                border: none;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .toolbar-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            
            .toolbar-btn.active {
                background: var(--bg-elevated);
                color: var(--accent);
                box-shadow: var(--glass-shadow-subtle);
            }
            
            .toolbar-btn:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }
            
            .separator {
                width: 1px;
                height: 24px;
                background: var(--border-subtle);
                margin: 0 var(--space-1);
            }
        `
    ];

    constructor() {
        super();
        this.state = this.use(s => ({
            activeTool: s.editor.activeTool,
            canUndo: s.editor.canUndo,
            canRedo: s.editor.canRedo,
        }));
    }

    _setTool(tool) {
        AgentsStore.setActiveTool(tool);
    }

    _onUndo() {
        if (this.state.value.canUndo) {
            AgentsStore.undo();
        }
    }

    _onRedo() {
        if (this.state.value.canRedo) {
            AgentsStore.redo();
        }
    }

    _onToggleVariables() {
        AgentsStore.toggleVariablesPanel();
    }

    render() {
        const { activeTool, canUndo, canRedo } = this.state.value;
        
        return html`
            <div class="toolbar">
                <button 
                    class="toolbar-btn ${activeTool === 'select' ? 'active' : ''}"
                    @click=${() => this._setTool('select')}
                    title="Select (V)"
                >
                    <platform-icon name="cursor" size="20"></platform-icon>
                </button>
                
                <button 
                    class="toolbar-btn ${activeTool === 'add' ? 'active' : ''}"
                    @click=${() => this._setTool('add')}
                    title="Add Node (A)"
                >
                    <platform-icon name="plus" size="20"></platform-icon>
                </button>
                
                <div class="separator"></div>
                
                <button 
                    class="toolbar-btn"
                    @click=${this._onUndo}
                    ?disabled=${!canUndo}
                    title="Undo (Cmd+Z)"
                >
                    <platform-icon name="undo" size="18"></platform-icon>
                </button>
                
                <button 
                    class="toolbar-btn"
                    @click=${this._onRedo}
                    ?disabled=${!canRedo}
                    title="Redo (Cmd+Shift+Z)"
                >
                    <platform-icon name="redo" size="18"></platform-icon>
                </button>
                
                <div class="separator"></div>
                
                <button 
                    class="toolbar-btn"
                    @click=${this._onToggleVariables}
                    title="Variables"
                >
                    <platform-icon name="code" size="18"></platform-icon>
                </button>
            </div>
        `;
    }
}

customElements.define('bottom-toolbar', BottomToolbar);


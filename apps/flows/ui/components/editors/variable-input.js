/**
 * VariableInput - инпут с автокомплитом переменных при вводе @
 * Показывает dropdown со списком переменных агента
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class VariableInput extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: relative;
            }
            
            .input-wrapper {
                position: relative;
            }
            
            input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-family: var(--font-mono);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            input:focus {
                border-color: var(--accent);
                background: var(--glass-tint-medium);
            }
            
            input::placeholder {
                color: var(--text-tertiary);
            }
            
            .dropdown {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                margin-top: 4px;
                background: #1a1a2e;
                border: 1px solid #333;
                border-radius: var(--radius-md);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
                max-height: 200px;
                overflow-y: auto;
                z-index: 10000;
            }
            
            .dropdown-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                transition: background var(--duration-fast) var(--easing-default);
            }
            
            .dropdown-item:hover,
            .dropdown-item.selected {
                background: #2a2a4e;
            }
            
            .dropdown-item-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: #e0e0e0;
                font-family: var(--font-mono);
            }
            
            .dropdown-item-type {
                font-size: var(--text-xs);
                color: #888;
                margin-left: auto;
            }
            
            .dropdown-empty {
                padding: var(--space-3);
                font-size: var(--text-sm);
                color: #888;
                text-align: center;
            }
            
            .dropdown-header {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: #888;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                border-bottom: 1px solid #333;
            }
        `
    ];

    static properties = {
        value: { type: String },
        name: { type: String },
        placeholder: { type: String },
        variables: { type: Array },
        _showDropdown: { type: Boolean, state: true },
        _selectedIndex: { type: Number, state: true },
        _filterText: { type: String, state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.name = '';
        this.placeholder = '';
        this.variables = [];
        this._showDropdown = false;
        this._selectedIndex = 0;
        this._filterText = '';
        this._cursorPosition = 0;
    }

    get _filteredVariables() {
        if (!this._filterText) {
            return this.variables;
        }
        const filter = this._filterText.toLowerCase();
        return this.variables.filter(v => 
            v.name.toLowerCase().includes(filter) ||
            (v.description || '').toLowerCase().includes(filter)
        );
    }

    _onInput(e) {
        const input = e.target;
        const value = input.value;
        const cursorPos = input.selectionStart;
        
        this.value = value;
        this._cursorPosition = cursorPos;
        
        // Проверяем, вводится ли @ или @var:
        const beforeCursor = value.substring(0, cursorPos);
        const atMatch = beforeCursor.match(/@(var:)?(\w*)$/);
        
        if (atMatch) {
            this._filterText = atMatch[2] || '';
            this._showDropdown = true;
            this._selectedIndex = 0;
        } else {
            this._showDropdown = false;
            this._filterText = '';
        }
        
        this.emit('input', { value });
        this.dispatchEvent(new Event('change', { bubbles: true }));
    }

    _onKeyDown(e) {
        if (!this._showDropdown) return;
        
        const filtered = this._filteredVariables;
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this._selectedIndex = Math.min(this._selectedIndex + 1, filtered.length - 1);
                break;
            case 'ArrowUp':
                e.preventDefault();
                this._selectedIndex = Math.max(this._selectedIndex - 1, 0);
                break;
            case 'Enter':
            case 'Tab':
                if (filtered.length > 0) {
                    e.preventDefault();
                    this._selectVariable(filtered[this._selectedIndex]);
                }
                break;
            case 'Escape':
                this._showDropdown = false;
                break;
        }
    }

    _selectVariable(variable) {
        const input = this.shadowRoot.querySelector('input');
        const value = input.value;
        const cursorPos = this._cursorPosition;
        
        // Найти начало @ паттерна
        const beforeCursor = value.substring(0, cursorPos);
        const atMatch = beforeCursor.match(/@(var:)?(\w*)$/);
        
        if (atMatch) {
            const startPos = cursorPos - atMatch[0].length;
            const replacement = `@var:${variable.name}`;
            const newValue = value.substring(0, startPos) + replacement + value.substring(cursorPos);
            
            this.value = newValue;
            this._showDropdown = false;
            
            this.emit('input', { value: newValue });
            this.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Установить курсор после вставленной переменной
            requestAnimationFrame(() => {
                const newCursorPos = startPos + replacement.length;
                input.setSelectionRange(newCursorPos, newCursorPos);
                input.focus();
            });
        }
    }

    _onBlur() {
        // Небольшая задержка чтобы успел сработать клик по dropdown
        setTimeout(() => {
            this._showDropdown = false;
        }, 150);
    }

    _renderDropdown() {
        if (!this._showDropdown) return null;
        
        const filtered = this._filteredVariables;
        
        if (filtered.length === 0) {
            return html`
                <div class="dropdown">
                    <div class="dropdown-empty">${this.i18n.t('variables_panel.empty')}</div>
                </div>
            `;
        }
        
        return html`
            <div class="dropdown">
                <div class="dropdown-header">${this.i18n.t('variables_panel.dropdown_header')}</div>
                ${filtered.map((variable, index) => html`
                    <div 
                        class="dropdown-item ${index === this._selectedIndex ? 'selected' : ''}"
                        @click=${() => this._selectVariable(variable)}
                        @mouseenter=${() => this._selectedIndex = index}
                    >
                        <span class="dropdown-item-name">@var:${variable.name}</span>
                        <span class="dropdown-item-type">${variable.type || 'string'}</span>
                    </div>
                `)}
            </div>
        `;
    }

    render() {
        return html`
            <div class="input-wrapper">
                <input
                    type="text"
                    .name=${this.name}
                    .value=${this.value}
                    placeholder=${this.placeholder}
                    @input=${this._onInput}
                    @keydown=${this._onKeyDown}
                    @blur=${this._onBlur}
                />
                ${this._renderDropdown()}
            </div>
        `;
    }
}

customElements.define('variable-input', VariableInput);

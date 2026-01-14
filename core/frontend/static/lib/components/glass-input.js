/**
 * Glass Input Component
 * Поле ввода с glass morphism эффектом
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';

export class GlassInput extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .input-wrapper {
                position: relative;
                display: flex;
                align-items: center;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                transition: all var(--duration-fast) var(--easing-default);
                backdrop-filter: blur(var(--glass-blur-subtle));
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
            }
            
            .input-wrapper:focus-within {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            
            .input-wrapper.error {
                border-color: var(--error);
            }
            
            input {
                flex: 1;
                padding: var(--space-3) var(--space-4);
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                outline: none;
            }
            
            input::placeholder {
                color: var(--text-tertiary);
            }
            
            input:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .prefix,
            .suffix {
                display: flex;
                align-items: center;
                padding: 0 var(--space-3);
                color: var(--text-tertiary);
            }
            
            .has-prefix input {
                padding-left: 0;
            }
            
            .has-suffix input {
                padding-right: 0;
            }
        `
    ];

    static properties = {
        type: { type: String },
        name: { type: String },
        value: { type: String },
        placeholder: { type: String },
        disabled: { type: Boolean },
        required: { type: Boolean },
        error: { type: Boolean },
        prefix: { type: String },
        suffix: { type: String },
    };

    constructor() {
        super();
        this.type = 'text';
        this.name = '';
        this.value = '';
        this.placeholder = '';
        this.disabled = false;
        this.required = false;
        this.error = false;
        this.prefix = '';
        this.suffix = '';
    }

    get inputEl() {
        return this.shadowRoot?.querySelector('input');
    }

    _onInput(e) {
        this.value = e.target.value;
        this.dispatchEvent(new CustomEvent('input', { 
            detail: { value: this.value },
            bubbles: true,
            composed: true 
        }));
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', { 
            detail: { value: this.value },
            bubbles: true,
            composed: true 
        }));
    }

    focus() {
        this.inputEl?.focus();
    }

    render() {
        const wrapperClasses = {
            'input-wrapper': true,
            'has-prefix': !!this.prefix,
            'has-suffix': !!this.suffix,
            'error': this.error,
        };

        return html`
            <div class=${classMap(wrapperClasses)}>
                ${this.prefix ? html`
                    <span class="prefix">${this.prefix}</span>
                ` : ''}
                
                <input
                    type=${this.type}
                    name=${this.name}
                    .value=${this.value}
                    placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    ?required=${this.required}
                    @input=${this._onInput}
                    @change=${this._onChange}
                />
                
                ${this.suffix ? html`
                    <span class="suffix">${this.suffix}</span>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('glass-input', GlassInput);


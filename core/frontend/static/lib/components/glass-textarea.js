/**
 * Glass Textarea Component
 * Многострочное поле ввода с glass эффектом
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '../platform-element/index.js';

export class GlassTextarea extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .textarea-wrapper {
                position: relative;
                display: flex;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                transition: all var(--duration-fast) var(--easing-default);
                backdrop-filter: blur(var(--glass-blur-subtle));
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
            }
            
            .textarea-wrapper:focus-within {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            
            .textarea-wrapper.error {
                border-color: var(--error);
            }
            
            textarea {
                flex: 1;
                padding: var(--space-3) var(--space-4);
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: var(--font-sans);
                line-height: var(--leading-normal);
                outline: none;
                resize: vertical;
                min-height: 100px;
            }
            
            textarea::placeholder {
                color: var(--text-tertiary);
            }
            
            textarea:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `
    ];

    static properties = {
        name: { type: String },
        value: { type: String },
        placeholder: { type: String },
        disabled: { type: Boolean },
        required: { type: Boolean },
        error: { type: Boolean },
        rows: { type: Number },
    };

    constructor() {
        super();
        this.name = '';
        this.value = '';
        this.placeholder = '';
        this.disabled = false;
        this.required = false;
        this.error = false;
        this.rows = 4;
    }

    get textareaEl() {
        return this.shadowRoot?.querySelector('textarea');
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
        this.textareaEl?.focus();
    }

    render() {
        const wrapperClasses = {
            'textarea-wrapper': true,
            'error': this.error,
        };

        return html`
            <div class=${classMap(wrapperClasses)}>
                <textarea
                    name=${this.name}
                    .value=${this.value}
                    placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    ?required=${this.required}
                    rows=${this.rows}
                    @input=${this._onInput}
                    @change=${this._onChange}
                ></textarea>
            </div>
        `;
    }
}

customElements.define('glass-textarea', GlassTextarea);


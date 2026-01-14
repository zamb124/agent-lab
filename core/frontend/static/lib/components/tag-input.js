/**
 * TagInput - редактор тегов с поддержкой Enter, запятой и Backspace
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class TagInput extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .tag-container {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2);
                min-height: 40px;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: text;
            }
            
            .tag-container:focus-within {
                border-color: var(--accent);
            }
            
            .tag {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--accent-subtle);
                border-radius: var(--radius-sm);
            }
            
            .tag-remove {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 14px;
                height: 14px;
                font-size: 12px;
                color: var(--text-secondary);
                background: none;
                border: none;
                border-radius: 50%;
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tag-remove:hover {
                color: var(--error);
                background: var(--error-bg);
            }
            
            .tag-input {
                flex: 1;
                min-width: 100px;
                padding: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: transparent;
                border: none;
                outline: none;
            }
            
            .tag-input::placeholder {
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        tags: { type: Array },
        placeholder: { type: String },
        readonly: { type: Boolean },
    };

    constructor() {
        super();
        this.tags = [];
        this.placeholder = 'Добавить тег...';
        this.readonly = false;
    }

    _getTags() {
        return Array.isArray(this.tags) ? this.tags : [];
    }

    getTags() {
        return [...this._getTags()];
    }

    setTags(tags) {
        this.tags = Array.isArray(tags) ? [...tags] : [];
    }

    _addTag(tag) {
        const trimmed = tag.trim().toLowerCase();
        const currentTags = this._getTags();
        if (trimmed && !currentTags.includes(trimmed)) {
            this.tags = [...currentTags, trimmed];
            this.emit('change', { tags: this.tags });
        }
    }

    _removeTag(index) {
        const currentTags = this._getTags();
        this.tags = currentTags.filter((_, i) => i !== index);
        this.emit('change', { tags: this.tags });
    }

    _onKeyDown(e) {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const input = e.target;
            if (input.value.trim()) {
                this._addTag(input.value);
                input.value = '';
            }
        } else if (e.key === 'Backspace' && !e.target.value) {
            const tags = this._getTags();
            if (tags.length > 0) {
                this._removeTag(tags.length - 1);
            }
        }
    }

    _onBlur(e) {
        if (e.target.value.trim()) {
            this._addTag(e.target.value);
            e.target.value = '';
        }
    }

    _onContainerClick() {
        const input = this.shadowRoot.querySelector('.tag-input');
        if (input) input.focus();
    }

    render() {
        const tags = this._getTags();
        return html`
            <div class="tag-container" @click=${this._onContainerClick}>
                ${tags.map((tag, i) => html`
                    <span class="tag">
                        ${tag}
                        ${!this.readonly ? html`
                            <button 
                                type="button" 
                                class="tag-remove" 
                                @click=${(e) => { e.stopPropagation(); this._removeTag(i); }}
                            >×</button>
                        ` : ''}
                    </span>
                `)}
                ${!this.readonly ? html`
                    <input
                        type="text"
                        class="tag-input"
                        placeholder=${tags.length === 0 ? this.placeholder : ''}
                        @keydown=${this._onKeyDown}
                        @blur=${this._onBlur}
                    />
                ` : ''}
            </div>
        `;
    }
}

customElements.define('tag-input', TagInput);

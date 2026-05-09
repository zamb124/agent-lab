/**
 * TagInput — редактор тегов с поддержкой Enter, запятой и Backspace.
 * Pill-режим единственный (атрибут `flat` удалён в PHASE 1.5).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class TagInput extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                width: 100%;
            }

            .tag-container {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                align-items: center;
                padding: 0;
                min-height: var(--field-pill-number-spin-height);
                box-sizing: border-box;
                background: transparent;
                border: none;
                border-radius: 0;
                cursor: text;
            }

            .tag-container:focus-within {
                outline: none;
                border: none;
                box-shadow: none;
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
                padding: 2px 0;
                font-size: var(--field-pill-input-size);
                font-weight: var(--field-pill-input-weight);
                color: var(--field-pill-input-color);
                background: transparent;
                border: none;
                outline: none;
            }

            .tag-input::placeholder {
                color: var(--field-pill-muted-color);
                font-weight: var(--font-normal);
            }
        `,
    ];

    static properties = {
        tags: { type: Array },
        placeholder: { type: String },
        readonly: { type: Boolean },
        /** Если true — только trim без toLowerCase (контракт platform-field-array `config.preserve_case`). По умолчанию lower-case как в CRM. */
        preserveCase: { type: Boolean, attribute: 'preserve-case' },
    };

    constructor() {
        super();
        this.tags = [];
        this.placeholder = '';
        this.readonly = false;
        this.preserveCase = false;
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

    _normalizeIncomingTag(tag) {
        const trimmed = typeof tag === 'string' ? tag.trim() : '';
        if (this.preserveCase) {
            return trimmed;
        }
        return trimmed.toLowerCase();
    }

    _addTag(tag) {
        const trimmed = this._normalizeIncomingTag(tag);
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
                        data-canon="tag-input"
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

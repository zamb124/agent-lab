/**
 * platform-markdown-editor — Gmail-like rich compose surface (UI Kit).
 * WYSIWYG contenteditable; наружу htmlValue + textValue. Не путать с prompt-editor.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formatFileSize } from '../utils/format-file-size.js';
import './platform-icon.js';
import './platform-button.js';

export const MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

const ALLOWED_TAGS = new Set([
    'P', 'BR', 'STRONG', 'B', 'EM', 'I', 'U', 'S', 'STRIKE',
    'UL', 'OL', 'LI', 'BLOCKQUOTE', 'A', 'DIV', 'SPAN',
]);

/**
 * @param {string} rawHtml
 * @returns {string}
 */
export function sanitizeMarkdownEditorHtml(rawHtml) {
    if (typeof rawHtml !== 'string' || rawHtml.length === 0) {
        return '';
    }
    const template = document.createElement('template');
    template.innerHTML = rawHtml;
    const walk = (node) => {
        const children = Array.from(node.childNodes);
        for (const child of children) {
            if (child.nodeType === Node.TEXT_NODE) {
                continue;
            }
            if (child.nodeType !== Node.ELEMENT_NODE) {
                child.remove();
                continue;
            }
            const el = /** @type {HTMLElement} */ (child);
            if (!ALLOWED_TAGS.has(el.tagName)) {
                const parent = el.parentNode;
                if (!parent) {
                    el.remove();
                    continue;
                }
                while (el.firstChild) {
                    parent.insertBefore(el.firstChild, el);
                }
                el.remove();
                continue;
            }
            if (el.tagName === 'A') {
                const href = el.getAttribute('href');
                for (const attr of Array.from(el.attributes)) {
                    el.removeAttribute(attr.name);
                }
                if (typeof href === 'string' && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:'))) {
                    el.setAttribute('href', href);
                }
            } else {
                for (const attr of Array.from(el.attributes)) {
                    el.removeAttribute(attr.name);
                }
            }
            walk(el);
        }
    };
    walk(template.content);
    return template.innerHTML;
}

export class PlatformMarkdownEditor extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        htmlValue: { type: String, attribute: false },
        placeholder: { type: String },
        primaryLabel: { type: String, attribute: 'primary-label' },
        showPrimary: { type: Boolean, attribute: 'show-primary' },
        showAttach: { type: Boolean, attribute: 'show-attach' },
        showDiscard: { type: Boolean, attribute: 'show-discard' },
        showFormatToggle: { type: Boolean, attribute: 'show-format-toggle' },
        primaryDisabled: { type: Boolean, attribute: 'primary-disabled' },
        readonly: { type: Boolean, reflect: true },
        attachments: { type: Array, attribute: false },
        _formatOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: var(--markdown-editor-min-height, 160px);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                overflow: hidden;
            }

            .body-wrap {
                position: relative;
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }

            .editor-body {
                flex: 1 1 auto;
                min-height: var(--markdown-editor-body-min-height, 120px);
                max-height: var(--markdown-editor-body-max-height, none);
                overflow: auto;
                padding: var(--space-4) var(--space-4) var(--space-3);
                outline: none;
                line-height: 1.55;
                font-size: 0.9375rem;
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }

            .editor-body:empty::before {
                content: attr(data-placeholder);
                color: var(--text-tertiary);
                pointer-events: none;
            }

            .format-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 2px;
                padding: var(--space-1) var(--space-2);
                border-top: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                flex-shrink: 0;
            }

            .format-toolbar[hidden] {
                display: none;
            }

            .fmt-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 32px;
                height: 32px;
                padding: 0 var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font: inherit;
                font-weight: 650;
                font-size: 0.8125rem;
            }

            .fmt-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }

            .attachments {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3) 0;
                flex-shrink: 0;
            }

            .att-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                max-width: 100%;
                padding: var(--space-1) var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                font-size: 0.75rem;
            }

            .att-chip-name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 180px;
            }

            .att-chip-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
                display: inline-flex;
            }

            .action-bar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--markdown-editor-action-bar-height, 48px);
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                background: var(--bg-surface);
                flex-shrink: 0;
            }

            .action-bar-end {
                margin-left: auto;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }

            .file-input {
                display: none;
            }

            :host([readonly]) {
                border: none;
                border-radius: 0;
                background: transparent;
            }

            :host([readonly]) .editor-body {
                cursor: default;
            }
        `,
    ];

    constructor() {
        super();
        this.htmlValue = '';
        this.placeholder = '';
        this.primaryLabel = '';
        this.showPrimary = true;
        this.showAttach = false;
        this.showDiscard = true;
        this.showFormatToggle = true;
        this.primaryDisabled = false;
        this.readonly = false;
        this.attachments = [];
        this._formatOpen = false;
        this._skipNextHtmlSync = false;
        /** @type {HTMLElement | null} */
        this._editorEl = null;
    }

    get textValue() {
        if (!this._editorEl) {
            const tmp = document.createElement('div');
            tmp.innerHTML = sanitizeMarkdownEditorHtml(this.htmlValue || '');
            return tmp.innerText || '';
        }
        return this._editorEl.innerText || '';
    }

    firstUpdated() {
        this._editorEl = this.renderRoot.querySelector('.editor-body');
        this._syncEditorFromProp();
    }

    updated(changed) {
        if (changed.has('htmlValue') && !this._skipNextHtmlSync) {
            const focused = this._editorEl && this.renderRoot.activeElement === this._editorEl;
            if (!focused) {
                this._syncEditorFromProp();
            }
        }
        this._skipNextHtmlSync = false;
    }

    _syncEditorFromProp() {
        if (!this._editorEl) {
            this._editorEl = this.renderRoot.querySelector('.editor-body');
        }
        if (!this._editorEl) return;
        const next = sanitizeMarkdownEditorHtml(typeof this.htmlValue === 'string' ? this.htmlValue : '');
        if (this._editorEl.innerHTML !== next) {
            this._editorEl.innerHTML = next;
        }
    }

    _emitChange() {
        if (!this._editorEl) return;
        const htmlValue = sanitizeMarkdownEditorHtml(this._editorEl.innerHTML);
        const textValue = this._editorEl.innerText || '';
        this._skipNextHtmlSync = true;
        this.htmlValue = htmlValue;
        this.emit('change', { htmlValue, textValue });
    }

    _onInput() {
        if (this.readonly) {
            return;
        }
        this._emitChange();
    }

    /**
     * @param {string} command
     * @param {string} [value]
     */
    _format(command, value) {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: format unavailable in readonly mode');
        }
        this._editorEl?.focus();
        const ok = document.execCommand(command, false, value);
        if (!ok) {
            throw new Error(`platform-markdown-editor: execCommand failed for ${command}`);
        }
        this._emitChange();
    }

    _insertLink() {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: link unavailable in readonly mode');
        }
        const href = window.prompt(this.t('markdown_editor.link_prompt'));
        if (href === null) return;
        const trimmed = href.trim();
        if (!trimmed) {
            throw new Error('platform-markdown-editor: link href required');
        }
        if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://') && !trimmed.startsWith('mailto:')) {
            throw new Error('platform-markdown-editor: link must be http(s) or mailto');
        }
        this._format('createLink', trimmed);
    }

    _toggleFormat() {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: format toggle unavailable in readonly mode');
        }
        this._formatOpen = !this._formatOpen;
    }

    _onPrimary() {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: primary unavailable in readonly mode');
        }
        this.emit('primary', {
            htmlValue: sanitizeMarkdownEditorHtml(this._editorEl ? this._editorEl.innerHTML : this.htmlValue),
            textValue: this.textValue,
            attachments: Array.isArray(this.attachments) ? this.attachments : [],
        });
    }

    _onDiscard() {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: discard unavailable in readonly mode');
        }
        this.emit('discard', null);
    }

    _openFilePicker() {
        const input = this.renderRoot.querySelector('.file-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('platform-markdown-editor: file input missing');
        }
        input.click();
    }

    /**
     * @param {Event} event
     */
    async _onFilesSelected(event) {
        const input = event.target;
        if (!(input instanceof HTMLInputElement) || !input.files) {
            return;
        }
        const files = Array.from(input.files);
        input.value = '';
        const current = Array.isArray(this.attachments) ? [...this.attachments] : [];
        for (const file of files) {
            if (file.size > MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES) {
                this.toast('markdown_editor.attach_too_large', {
                    type: 'error',
                    vars: { filename: file.name, max_mb: 10 },
                    namespace: 'platform',
                });
                continue;
            }
            const buffer = await file.arrayBuffer();
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i += 1) {
                binary += String.fromCharCode(bytes[i]);
            }
            const contentType = file.type && file.type.length > 0 ? file.type : 'application/octet-stream';
            current.push({
                filename: file.name,
                content_type: contentType,
                content_base64: btoa(binary),
                size: file.size,
            });
        }
        this.attachments = current;
        this.emit('attachments-change', { attachments: current });
    }

    /**
     * @param {number} index
     */
    _removeAttachment(index) {
        if (!Array.isArray(this.attachments) || index < 0 || index >= this.attachments.length) {
            throw new Error('platform-markdown-editor: invalid attachment index');
        }
        const next = this.attachments.filter((_, i) => i !== index);
        this.attachments = next;
        this.emit('attachments-change', { attachments: next });
    }

    _renderFormatToolbar() {
        if (this.readonly || !this.showFormatToggle || !this._formatOpen) return nothing;
        return html`
            <div class="format-toolbar" role="toolbar" aria-label=${this.t('markdown_editor.format_toolbar')}>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.bold')} @click=${() => this._format('bold')}>B</button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.italic')} @click=${() => this._format('italic')}><em>I</em></button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.underline')} @click=${() => this._format('underline')}><u>U</u></button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.strikethrough')} @click=${() => this._format('strikeThrough')}><s>S</s></button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.ul')} @click=${() => this._format('insertUnorderedList')}>
                    <platform-icon name="list" size="14"></platform-icon>
                </button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.ol')} @click=${() => this._format('insertOrderedList')}>1.</button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.quote')} @click=${() => this._format('formatBlock', 'blockquote')}>"</button>
                <button type="button" class="fmt-btn" title=${this.t('markdown_editor.link')} @click=${() => this._insertLink()}>
                    <platform-icon name="link" size="14"></platform-icon>
                </button>
            </div>
        `;
    }

    render() {
        const placeholder = this.placeholder.length > 0
            ? this.placeholder
            : this.t('markdown_editor.placeholder');
        const primaryLabel = this.primaryLabel.length > 0
            ? this.primaryLabel
            : this.t('markdown_editor.primary');
        const atts = Array.isArray(this.attachments) ? this.attachments : [];
        const editable = !this.readonly;
        return html`
            <div class="body-wrap">
                <div
                    class="editor-body"
                    contenteditable=${editable ? 'true' : 'false'}
                    data-canon="composer"
                    data-placeholder=${placeholder}
                    @input=${() => this._onInput()}
                ></div>
            </div>
            ${!this.readonly && atts.length > 0 ? html`
                <div class="attachments">
                    ${atts.map((att, index) => html`
                        <div class="att-chip">
                            <platform-icon name="attach" size="12"></platform-icon>
                            <span class="att-chip-name">${att.filename}</span>
                            <span>${formatFileSize(att.size)}</span>
                            <button
                                type="button"
                                class="att-chip-remove"
                                .ariaLabel=${this.t('markdown_editor.attach_remove')}
                                @click=${() => this._removeAttachment(index)}
                            >
                                <platform-icon name="close" size="12"></platform-icon>
                            </button>
                        </div>
                    `)}
                </div>
            ` : nothing}
            ${this._renderFormatToolbar()}
            ${this.readonly ? nothing : html`
                <div class="action-bar">
                    ${this.showPrimary ? html`
                        <platform-button
                            variant="primary"
                            density="compact"
                            ?disabled=${this.primaryDisabled}
                            @click=${() => this._onPrimary()}
                        >
                            <platform-icon name="send" size="16"></platform-icon>
                            ${primaryLabel}
                        </platform-button>
                    ` : nothing}
                    <div class="action-bar-end">
                        ${this.showFormatToggle ? html`
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                .ariaLabel=${this.t('markdown_editor.format_toggle')}
                                @click=${() => this._toggleFormat()}
                            >
                                <span style="font-weight:700;font-size:0.75rem;">Aa</span>
                            </platform-button>
                        ` : nothing}
                        ${this.showAttach ? html`
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                .ariaLabel=${this.t('markdown_editor.attach')}
                                @click=${() => this._openFilePicker()}
                            >
                                <platform-icon name="attach" size="16"></platform-icon>
                            </platform-button>
                            <input
                                class="file-input"
                                type="file"
                                multiple
                                @change=${(e) => this._onFilesSelected(e)}
                            />
                        ` : nothing}
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            .ariaLabel=${this.t('markdown_editor.link')}
                            @click=${() => this._insertLink()}
                        >
                            <platform-icon name="link" size="16"></platform-icon>
                        </platform-button>
                        ${this.showDiscard ? html`
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                .ariaLabel=${this.t('markdown_editor.discard')}
                                @click=${() => this._onDiscard()}
                            >
                                <platform-icon name="trash" size="16"></platform-icon>
                            </platform-button>
                        ` : nothing}
                    </div>
                </div>
            `}
        `;
    }
}

customElements.define('platform-markdown-editor', PlatformMarkdownEditor);

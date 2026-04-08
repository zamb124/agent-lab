/**
 * Поле ввода сообщения в чате
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { resolveFileIconKey } from '@platform/services/icon.service.js';

export class ChatInput extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: var(--space-4) var(--space-6);
            }
            
            .input-container {
                display: flex;
                align-items: flex-end;
                gap: var(--space-3);
                max-width: 900px;
                margin: 0 auto;
                padding: var(--space-3);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-subtle));
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                box-shadow: var(--glass-shadow-subtle), var(--glass-inner-glow-subtle);
            }
            
            .input-container:focus-within {
                border-color: var(--accent);
                box-shadow: var(--glass-shadow-medium), var(--glass-inner-glow-medium), var(--hover-glow);
            }
            
            @media (max-width: 768px) {
                :host {
                    padding: var(--space-5) var(--space-4);
                    padding-bottom: var(--space-6);
                    background: var(--glass-solid-strong);
                    border-top-left-radius: 20px;
                    border-top-right-radius: 20px;
                    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
                }
                
                .input-container {
                    max-width: none;
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    backdrop-filter: none;
                    border: none;
                    border-radius: 0;
                    box-shadow: none;
                }
                
                .input-container:focus-within {
                    box-shadow: none;
                }
                
                textarea {
                    min-height: 44px;
                    background: transparent;
                }
            }
            
            .attach-button {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .attach-button:hover {
                color: var(--text-primary);
                background: var(--glass-solid-strong);
            }
            
            .input-wrapper {
                flex: 1;
                position: relative;
            }
            
            textarea {
                width: 100%;
                min-height: 40px;
                max-height: 180px;
                padding: var(--space-2) var(--space-1);
                font-family: var(--font-sans);
                font-size: var(--text-base);
                line-height: var(--leading-normal);
                color: var(--text-primary);
                background: transparent;
                border: none;
                resize: none;
                overflow-y: auto;
                outline: none;
            }
            
            textarea::placeholder {
                color: var(--text-tertiary);
            }
            
            textarea:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            
            .send-button {
                flex-shrink: 0;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-gradient);
                border: none;
                color: white;
                border-radius: var(--radius-xl);
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
                transition: all var(--duration-normal) var(--easing-default);
            }
            
            .send-button:hover:not(:disabled) {
                transform: translateY(-2px) scale(1.02);
                box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
            }
            
            .send-button:active:not(:disabled) {
                transform: translateY(0) scale(0.98);
            }
            
            .send-button:disabled {
                opacity: 0.4;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            
            .send-button.stop {
                background: var(--error, #ef4444);
                box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
            }
            
            .send-button.stop:hover {
                box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
            }
            
            .file-input {
                display: none;
            }
            
            .files-preview {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .file-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }
            
            .file-image-preview {
                width: 40px;
                height: 40px;
                object-fit: cover;
                border-radius: var(--radius-sm);
            }
            
            .file-info {
                flex: 1;
                min-width: 0;
            }
            
            .file-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .file-size {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            
            .file-remove {
                flex-shrink: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                background: transparent;
                border: none;
                border-radius: var(--radius-sm);
                transition: all var(--duration-fast) var(--easing-default);
                cursor: pointer;
            }
            
            .file-remove:hover {
                color: var(--error);
                background: var(--error-bg);
            }
        `
    ];

    static properties = {
        disabled: { type: Boolean },
        loading: { type: Boolean },
        placeholder: { type: String },
        maxLength: { type: Number },
        maxFileSize: { type: Number },
        _value: { state: true },
        _selectedFiles: { state: true },
    };

    constructor() {
        super();
        this.disabled = false;
        this.loading = false;
        this.placeholder = 'Send a message';
        this.maxLength = 10000;
        this.maxFileSize = 10 * 1024 * 1024; // 10MB
        this._value = '';
        this._selectedFiles = [];
    }

    get textareaEl() {
        return this.shadowRoot?.querySelector('textarea');
    }

    get fileInputEl() {
        return this.shadowRoot?.querySelector('.file-input');
    }

    _onInput(e) {
        this._value = e.target.value;
        this._adjustHeight();
    }

    _onKeyDown(e) {
        // Ctrl+Enter или Cmd+Enter для отправки
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            this._send();
        }
        // Просто Enter без Shift тоже отправляет
        else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._send();
        }
    }

    _adjustHeight() {
        const el = this.textareaEl;
        if (!el) return;
        
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }

    _send() {
        const text = this._value.trim();
        if ((!text && this._selectedFiles.length === 0) || this.disabled || this.loading) return;

        this.emit('send', { 
            message: text,
            files: this._selectedFiles 
        });
        this._value = '';
        this._selectedFiles = [];
        
        if (this.textareaEl) {
            this.textareaEl.style.height = 'auto';
        }
    }

    _onAttachClick() {
        this.fileInputEl?.click();
    }

    _onFilesSelected(e) {
        const files = Array.from(e.target.files || []);
        
        for (const file of files) {
            if (this._validateFile(file)) {
                this._selectedFiles = [...this._selectedFiles, file];
            }
        }
        
        if (this.fileInputEl) {
            this.fileInputEl.value = '';
        }
    }

    _validateFile(file) {
        if (file.size > this.maxFileSize) {
            this.error(
                this.i18n.t('chat_input.err_file_too_large', {
                    name: file.name,
                    max: this._formatFileSize(this.maxFileSize),
                })
            );
            return false;
        }

        const ft = this.services.fileTypes;
        if (!ft.isAllowedFile(file, ...ft.categories)) {
            this.error(this.i18n.t('chat_input.err_file_type', { name: file.name }));
            return false;
        }

        return true;
    }

    _removeFile(index) {
        this._selectedFiles = this._selectedFiles.filter((_, i) => i !== index);
    }

    _formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    _isImage(file) {
        return file.type.startsWith('image/');
    }

    focus() {
        this.textareaEl?.focus();
    }

    clear() {
        this._value = '';
        if (this.textareaEl) {
            this.textareaEl.style.height = 'auto';
        }
    }

    _stop() {
        this.emit('stop');
    }

    render() {
        const canSend = (this._value.trim().length > 0 || this._selectedFiles.length > 0) && !this.disabled && !this.loading;

        return html`
            ${this._selectedFiles.length > 0 ? html`
                <div class="files-preview">
                    ${this._selectedFiles.map((file, index) => this._renderFilePreview(file, index))}
                </div>
            ` : ''}
            
            <div class="input-container">
                <input 
                    type="file" 
                    class="file-input"
                    multiple
                    accept=${this.services.fileTypes.acceptStringFor(...this.services.fileTypes.categories)}
                    @change=${this._onFilesSelected}
                >
                
                <button 
                    class="attach-button" 
                    title=${this.i18n.t('chat_input.title_attach')}
                    @click=${this._onAttachClick}
                    ?disabled=${this.disabled || this.loading}
                >
                    <platform-icon name="paperclip" size="20"></platform-icon>
                </button>
                
                <div class="input-wrapper">
                    <textarea
                        .value=${this._value}
                        placeholder=${this.placeholder}
                        maxlength=${this.maxLength}
                        ?disabled=${this.disabled || this.loading}
                        @input=${this._onInput}
                        @keydown=${this._onKeyDown}
                        rows="1"
                    ></textarea>
                </div>
                
                ${this.loading ? html`
                    <button 
                        class="send-button stop"
                        @click=${this._stop}
                    >
                        <platform-icon name="stop" size="20" filled></platform-icon>
                    </button>
                ` : html`
                    <button 
                        class="send-button" 
                        ?disabled=${!canSend}
                        @click=${this._send}
                    >
                        <platform-icon name="send" size="20"></platform-icon>
                    </button>
                `}
            </div>
        `;
    }

    _renderFilePreview(file, index) {
        return html`
            <div class="file-item">
                ${this._isImage(file) ? html`
                    <img 
                        class="file-image-preview" 
                        src=${URL.createObjectURL(file)} 
                        alt=${file.name}
                    >
                ` : html`
                    <platform-icon
                        file-icon
                        name=${resolveFileIconKey(file.name || '', file.type || '')}
                        size="24"
                    ></platform-icon>
                `}
                
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${this._formatFileSize(file.size)}</div>
                </div>
                
                <button 
                    class="file-remove"
                    @click=${() => this._removeFile(index)}
                    title=${this.i18n.t('chat_input.title_remove_file')}
                >
                    <platform-icon name="close" size="16"></platform-icon>
                </button>
            </div>
        `;
    }
}

customElements.define('chat-input', ChatInput);

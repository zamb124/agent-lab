/**
 * MessageComposer — ввод и отправка сообщений (текст, изображение, эмодзи)
 * Полный паритет с sync1 Composer.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';

const EMOJIS = ['😀', '😅', '😉', '😍', '🤝', '🔥', '✅', '💡', '🧠', '🚀', '📌', '🧩', '⚠️', '❌', '👍', '👀'];

function randomUuidV4() {
    const c = globalThis.crypto;
    if (c && typeof c.randomUUID === 'function') {
        return c.randomUUID();
    }
    if (c && typeof c.getRandomValues === 'function') {
        const buf = new Uint8Array(16);
        c.getRandomValues(buf);
        buf[6] = (buf[6] & 0x0f) | 0x40;
        buf[8] = (buf[8] & 0x3f) | 0x80;
        const hex = Array.from(buf, (byte) => byte.toString(16).padStart(2, '0')).join('');
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    throw new Error('Web Crypto API недоступен: нельзя сгенерировать идентификатор команды.');
}

export class MessageComposer extends PlatformElement {
    static properties = {
        channelId: { type: String },
        _text: { state: true },
        _emojiOpen: { state: true },
        _focusedThreadId: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        formStyles,
        css`
            :host {
                display: block;
                flex-shrink: 0;
            }

            .composer {
                border-top: 1px solid var(--glass-border-subtle);
                padding: var(--space-3);
            }

            .row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                position: relative;
            }

            .icon-btn {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .icon-btn.send {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .icon-btn.send:hover {
                background: var(--accent);
                color: white;
            }

            .textarea {
                flex: 1;
                min-height: 44px;
                max-height: 200px;
                resize: none;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                outline: none;
                transition: border-color var(--duration-fast);
            }

            .textarea:focus {
                border-color: var(--accent);
            }

            .emoji-popup {
                position: absolute;
                bottom: calc(100% + 8px);
                right: 44px;
                width: 240px;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-2);
                box-shadow: var(--glass-shadow-strong);
                z-index: 50;
            }

            .emoji-grid {
                display: grid;
                grid-template-columns: repeat(8, 1fr);
                gap: var(--space-1);
            }

            .emoji-btn {
                background: transparent;
                border: none;
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: 18px;
                padding: 4px;
                transition: background var(--duration-fast);
                line-height: 1;
            }

            .emoji-btn:hover {
                background: var(--glass-solid-medium);
            }

            .thread-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-2);
            }

            input[type="file"] {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.channelId = null;
        this._text = '';
        this._emojiOpen = false;
        this._focusedThreadId = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._focusedThreadId = state.chat.focusedThreadId;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    async _sendText() {
        const text = this._text.trim();
        if (!text || !this.channelId) return;

        const ws = ServiceRegistry.get('syncWs');
        if (!ws) throw new Error('WebSocket не подключен.');

        const commandId = randomUuidV4();
        const auth = ServiceRegistry.auth;
        const userId = auth?.user?.id;
        if (!userId) throw new Error('Не удалось определить user_id.');

        const messageCreate = {
            thread_id: this._focusedThreadId,
            parent_message_id: null,
            contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
        };

        const pending = {
            id: `pending:${commandId}`,
            channel_id: this.channelId,
            thread_id: this._focusedThreadId,
            parent_message_id: null,
            sender: { id: userId, display_name: 'Вы', avatar_url: null },
            status: 'pending',
            sent_at: new Date().toISOString(),
            edited_at: null,
            contents: messageCreate.contents,
        };

        this._text = '';
        SyncStore.addPending(commandId, pending);

        try {
            ws.sendJson({
                id: commandId,
                type: 'messages.send',
                payload: { channel_id: this.channelId, body: messageCreate },
            });
        } catch (e) {
            SyncStore.failPending(commandId);
            throw e;
        }
    }

    async _pickImage(e) {
        const input = e.currentTarget;
        const files = input.files;
        if (!files || files.length === 0) return;
        if (!this.channelId) throw new Error('Выбери канал.');

        const file = files[0];
        input.value = '';

        const syncApi = ServiceRegistry.get('syncApi');
        const res = await syncApi.uploadFile(file);
        if (!res?.file?.id) throw new Error('Некорректный ответ загрузки файла.');

        const messageCreate = {
            thread_id: this._focusedThreadId,
            parent_message_id: null,
            contents: [{ type: 'mock/image', data: { file_id: res.file.id, alt_text: null }, order: 0 }],
        };

        await syncApi.sendMessage(this.channelId, messageCreate);
        await SyncStore.loadMessages(syncApi, this.channelId);
    }

    _insertEmoji(em) {
        if (!em.trim()) throw new Error('emoji обязателен.');
        this._text = this._text + em;
        this._emojiOpen = false;
    }

    _onKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._sendText();
        }
    }

    _openFilePicker() {
        this.shadowRoot?.querySelector('input[type="file"]')?.click();
    }

    render() {
        return html`
            <div class="composer">
                <div class="row">
                    <button class="icon-btn" title="Прикрепить изображение" @click=${this._openFilePicker}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path d="M12.5 6.5L6.4 12.6a4 4 0 105.7 5.7l7.1-7.1a6 6 0 10-8.5-8.5l-7.1 7.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>
                    <input type="file" accept="image/*" @change=${this._pickImage}>

                    <textarea
                        class="textarea"
                        rows="1"
                        placeholder="Сообщение..."
                        .value=${this._text}
                        @input=${(e) => { this._text = e.target.value; }}
                        @keydown=${this._onKeyDown}
                    ></textarea>

                    <button
                        class="icon-btn"
                        title="Эмодзи"
                        @click=${() => { this._emojiOpen = !this._emojiOpen; }}
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path d="M12 22a10 10 0 110-20 10 10 0 010 20z" stroke="currentColor" stroke-width="1.8"/>
                            <path d="M8.5 10.2h.01M15.5 10.2h.01" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>
                            <path d="M8.2 14.2c1.1 1.3 2.4 2 3.8 2s2.7-.7 3.8-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>

                    <button class="icon-btn send" title="Отправить" @click=${this._sendText}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                            <path d="M21.2 3.6L10.1 14.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M21.2 3.6l-7.2 19.2-3.3-7.7-7.7-3.3 18.2-8.2z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>

                    ${this._emojiOpen ? html`
                        <div class="emoji-popup">
                            <div class="emoji-grid">
                                ${EMOJIS.map(em => html`
                                    <button class="emoji-btn" @click=${() => this._insertEmoji(em)}>${em}</button>
                                `)}
                            </div>
                        </div>
                    ` : ''}
                </div>

                ${this._focusedThreadId ? html`
                    <div class="thread-hint">Фокус на тред: новые сообщения уйдут в выбранный thread_id.</div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('message-composer', MessageComposer);

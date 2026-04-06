import { LitElement, html, css } from 'lit';

export class EmbedChatInput extends LitElement {
    static properties = {
        loading: { type: Boolean },
        placeholder: { type: String },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        labels: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            border-top: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.12));
            padding: 12px;
            background: var(--embed-chat-input-bg, rgba(0, 0, 0, 0.2));
        }
        .row {
            display: flex;
            gap: 8px;
            align-items: flex-end;
        }
        textarea {
            flex: 1;
            min-height: 44px;
            max-height: 160px;
            resize: vertical;
            border-radius: 12px;
            border: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.15));
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.05));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.9));
            padding: 10px 12px;
            font-size: 14px;
            font-family: inherit;
        }
        button {
            border-radius: 10px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            background: var(--embed-chat-accent, #99a6f9);
            color: var(--embed-chat-on-accent, #0f0f12);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .icon-btn {
            padding: 10px 12px;
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.08));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.85));
        }
        .icon-btn.active {
            background: var(--embed-chat-accent-muted, rgba(153, 166, 249, 0.35));
        }
        input[type='file'] {
            display: none;
        }
    `;

    constructor() {
        super();
        this.loading = false;
        this.placeholder = '';
        this.enableVoice = true;
        this.labels = {};
        this._text = '';
        this._files = [];
        this._rec = null;
        this._listening = false;
    }

    _label(key, fallback) {
        const L = this.labels && typeof this.labels === 'object' ? this.labels : {};
        return L[key] != null && L[key] !== '' ? L[key] : fallback;
    }

    _onInput(e) {
        this._text = e.target.value;
    }

    _onSend() {
        const message = (this._text || '').trim();
        if ((!message && this._files.length === 0) || this.loading) {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('embed-send', {
                detail: { message, files: [...this._files] },
                bubbles: true,
                composed: true,
            }),
        );
        this._text = '';
        this._files = [];
        this.shadowRoot.querySelector('textarea').value = '';
        const fi = this.shadowRoot.querySelector('input[type=file]');
        if (fi) {
            fi.value = '';
        }
        this.requestUpdate();
    }

    _onKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._onSend();
        }
    }

    _onPickFiles(e) {
        this._files = Array.from(e.target.files || []);
        this.requestUpdate();
    }

    _openFilePicker() {
        const fi = this.shadowRoot.querySelector('input[type=file]');
        if (fi) {
            fi.click();
        }
    }

    _toggleVoice() {
        const SR = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
        if (!SR) {
            this.dispatchEvent(
                new CustomEvent('embed-toast', {
                    detail: { message: this._label('voiceNotSupported', 'Voice not supported') },
                    bubbles: true,
                    composed: true,
                }),
            );
            return;
        }
        if (this._listening && this._rec) {
            this._rec.stop();
            this._listening = false;
            this._rec = null;
            this.requestUpdate();
            return;
        }
        const rec = new SR();
        rec.lang = document.documentElement.lang || 'ru-RU';
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.onresult = (ev) => {
            const t = ev.results?.[0]?.[0]?.transcript;
            if (typeof t === 'string' && t.trim()) {
                const ta = this.shadowRoot.querySelector('textarea');
                const cur = ta.value;
                ta.value = cur ? `${cur.trim()} ${t.trim()}` : t.trim();
                this._text = ta.value;
            }
            this._listening = false;
            this._rec = null;
            this.requestUpdate();
        };
        rec.onerror = () => {
            this._listening = false;
            this._rec = null;
            this.requestUpdate();
        };
        rec.onend = () => {
            this._listening = false;
            this._rec = null;
            this.requestUpdate();
        };
        this._rec = rec;
        this._listening = true;
        rec.start();
        this.requestUpdate();
    }

    render() {
        const fileHint =
            this._files.length > 0 ? ` (${this._files.length} files)` : '';
        return html`
            <div class="row">
                <textarea
                    .value=${this._text}
                    placeholder=${this.placeholder}
                    @input=${this._onInput}
                    @keydown=${this._onKey}
                ></textarea>
                <input type="file" multiple @change=${this._onPickFiles} />
                <button type="button" class="icon-btn" ?disabled=${this.loading} @click=${this._openFilePicker}>
                    +
                </button>
                ${this.enableVoice
                    ? html`
                          <button
                              type="button"
                              class="icon-btn ${this._listening ? 'active' : ''}"
                              ?disabled=${this.loading}
                              @click=${this._toggleVoice}
                              title=${this._label('voiceTitle', 'Voice')}
                          >
                              ${this._listening ? '...' : 'Mic'}
                          </button>
                      `
                    : ''}
                <button type="button" ?disabled=${this.loading} @click=${this._onSend}>
                    ${this._label('send', 'Send')}
                </button>
            </div>
            ${fileHint ? html`<div style="font-size:11px;margin-top:6px;opacity:0.7;">${fileHint}</div>` : ''}
        `;
    }
}

customElements.define('embed-chat-input', EmbedChatInput);

import { LitElement, html, css } from './lit-shim.js';

export class EmbedChatInput extends LitElement {
    static properties = {
        loading: { type: Boolean },
        cancelBusy: { type: Boolean, attribute: 'cancel-busy' },
        placeholder: { type: String },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        voiceDuplex: { type: Boolean, attribute: 'voice-duplex' },
        voiceActive: { type: Boolean, attribute: 'voice-active' },
        voiceStatus: { type: String, attribute: 'voice-status' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        labels: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            border-top: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.12));
            padding: 12px 0 0;
            background: transparent;
            --embed-radius: 25px;
            --embed-composer-bg: var(
                --embed-chat-composer-bg,
                rgba(255, 255, 255, 0.07)
            );
        }
        .composer {
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 6px;
            min-height: 52px;
            padding: 6px 8px 6px 10px;
            box-sizing: border-box;
            border-radius: var(--embed-radius);
            border: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.14));
            background: var(--embed-composer-bg);
        }
        .grow {
            flex: 1;
            min-width: 0;
            display: flex;
            align-items: center;
        }
        textarea {
            width: 100%;
            min-height: 40px;
            max-height: 140px;
            resize: none;
            border: none;
            outline: none;
            background: transparent;
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            padding: 8px 4px;
            font-size: 15px;
            line-height: 1.4;
            font-family: inherit;
        }
        textarea::placeholder {
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.45));
        }
        .circle-btn {
            flex-shrink: 0;
            width: 40px;
            height: 40px;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            border: none;
            cursor: pointer;
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.1));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.88));
        }
        .circle-btn:hover:not(:disabled) {
            background: var(--embed-chat-surface-hover, rgba(255, 255, 255, 0.14));
        }
        .circle-btn.active {
            background: var(--embed-chat-accent-muted, rgba(153, 166, 249, 0.35));
        }
        .circle-btn:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }
        .send-btn {
            background: var(--embed-chat-accent, #99a6f9);
            color: var(--embed-chat-on-accent, #0f0f12);
        }
        .send-btn:not(:disabled):hover {
            filter: brightness(1.05);
        }
        .circle-btn.stop {
            background: rgba(229, 57, 53, 0.9);
            color: #fff;
        }
        .circle-btn.stop:not(:disabled):hover {
            filter: brightness(1.06);
        }
        .send-btn.muted {
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.12));
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.5));
        }
        .locale {
            flex-shrink: 0;
            max-width: 140px;
        }
        .locale select {
            max-width: 100%;
            border: none;
            background: transparent;
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.55));
            font-size: 13px;
            cursor: pointer;
            padding: 6px 4px;
            font-family: inherit;
        }
        .locale select:focus {
            outline: none;
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.85));
        }
        .disclaimer {
            margin-top: 10px;
            text-align: center;
            font-size: 11px;
            line-height: 1.35;
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.42));
        }
        input[type='file'] {
            display: none;
        }
        .attachments-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 0 0 8px;
            padding: 0;
        }
        .attach-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            max-width: 100%;
            padding: 4px 8px;
            border-radius: 999px;
            font-size: 12px;
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.1));
            border: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.14));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
        }
        .attach-chip-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 200px;
        }
        .attach-chip-remove {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            padding: 0;
            margin: 0;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            font-size: 16px;
            line-height: 1;
            background: transparent;
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.55));
        }
        .attach-chip-remove:hover {
            background: var(--embed-chat-input-bg, rgba(0, 0, 0, 0.2));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
        }
        .attachments-clear-all {
            align-self: flex-end;
            margin: 0 0 6px;
            padding: 2px 0;
            border: none;
            background: none;
            cursor: pointer;
            font-size: 12px;
            color: var(--embed-chat-accent, #99a6f9);
            font-family: inherit;
        }
        .attachments-clear-all:hover {
            text-decoration: underline;
        }
        svg {
            display: block;
        }
    `;

    constructor() {
        super();
        this.loading = false;
        this.cancelBusy = false;
        this.placeholder = '';
        this.enableVoice = true;
        this.voiceDuplex = false;
        this.voiceActive = false;
        this.voiceStatus = 'idle';
        this.showLocaleControl = false;
        this.interfaceLocale = 'auto';
        this.labels = {};
        this._text = '';
        this._files = [];
        this._rec = null;
        this._listening = false;
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('interfaceLocale')) {
            const sel = this.shadowRoot?.querySelector('.locale select');
            if (sel) {
                sel.value = this.interfaceLocale || 'auto';
            }
        }
    }

    _label(key, fallback) {
        const L = this.labels && typeof this.labels === 'object' ? this.labels : {};
        return L[key] != null && L[key] !== '' ? L[key] : fallback;
    }

    _speechLang() {
        const il = String(this.interfaceLocale || '').toLowerCase();
        if (il === 'en') {
            return 'en-US';
        }
        if (il === 'ru') {
            return 'ru-RU';
        }
        const doc = document.documentElement.lang || 'ru-RU';
        return doc.startsWith('en') ? 'en-US' : 'ru-RU';
    }

    _canSend() {
        const message = (this._text || '').trim();
        return (message.length > 0 || this._files.length > 0) && !this.loading;
    }

    _onInput(e) {
        this._text = e.target.value;
        this.requestUpdate();
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
        const ta = this.shadowRoot?.querySelector('textarea');
        if (ta) {
            ta.value = '';
        }
        const fi = this.shadowRoot?.querySelector('input[type=file]');
        if (fi) {
            fi.value = '';
        }
        this.requestUpdate();
    }

    _onKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (this.loading) {
                return;
            }
            this._onSend();
        }
    }

    _syncFileInputFromFiles() {
        const fi = this.shadowRoot?.querySelector('input[type=file]');
        if (!fi) {
            return;
        }
        if (this._files.length === 0) {
            fi.value = '';
            return;
        }
        const dt = new DataTransfer();
        for (const f of this._files) {
            dt.items.add(f);
        }
        fi.files = dt.files;
    }

    _removeFileAt(index) {
        if (index < 0 || index >= this._files.length) {
            return;
        }
        this._files = this._files.filter((_, j) => j !== index);
        this._syncFileInputFromFiles();
        this.requestUpdate();
    }

    _removeAllAttachments() {
        this._files = [];
        const fi = this.shadowRoot?.querySelector('input[type=file]');
        if (fi) {
            fi.value = '';
        }
        this.requestUpdate();
    }

    _openFilePicker() {
        const fi = this.shadowRoot.querySelector('input[type=file]');
        if (fi) {
            fi.click();
        }
    }

    _onPickFiles(e) {
        const raw = e.target && e.target.files ? e.target.files : null;
        const picked = raw ? Array.from(raw) : [];
        if (picked.length === 0) {
            return;
        }
        this._files = [...this._files, ...picked];
        this._syncFileInputFromFiles();
        this.requestUpdate();
        const fi = this.shadowRoot?.querySelector('input[type=file]');
        if (fi) {
            fi.value = '';
        }
    }

    _embedStop() {
        if (this.cancelBusy) {
            return;
        }
        if (!this.loading) {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('embed-stop', {
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onLocaleSelect(e) {
        const v = e.target.value;
        if (v !== 'auto' && v !== 'ru' && v !== 'en') {
            return;
        }
        this.interfaceLocale = v;
        this.dispatchEvent(
            new CustomEvent('embed-locale-change', {
                detail: { locale: v },
                bubbles: true,
                composed: true,
            }),
        );
        this.requestUpdate();
    }

    _composerMicVisible() {
        return this.voiceDuplex === true || this.enableVoice === true;
    }

    _composerMicDuplexIdleOff() {
        return (
            this.voiceDuplex === true &&
            this.voiceActive !== true &&
            (this.voiceStatus === 'idle' || this.voiceStatus === 'closed')
        );
    }

    _voiceStatusHintVisible() {
        if (this.voiceDuplex !== true) {
            return false;
        }
        return (
            this.voiceActive === true ||
            (this.voiceStatus !== 'idle' && this.voiceStatus !== 'closed')
        );
    }

    _voiceStatusHintText() {
        const vs = typeof this.voiceStatus === 'string' ? this.voiceStatus : 'idle';
        const key = `voice_status_${vs}`;
        const L = this.labels && typeof this.labels === 'object' ? this.labels : {};
        if (typeof L[key] === 'string' && L[key].trim() !== '') {
            return L[key];
        }
        return this._label('voice_status_idle', 'Voice mode: idle');
    }

    _composerDuplexMicTitle() {
        const LOff = this._label('voice_off', 'Disable voice');
        const LOn = this._label('voice_on', 'Enable voice');
        const base = this.voiceActive === true ? LOff : LOn;
        if (this._voiceStatusHintVisible() !== true) {
            return base;
        }
        return `${base}. ${this._voiceStatusHintText()}`;
    }

    _onComposerMicClick() {
        if (this.voiceDuplex === true) {
            this.dispatchEvent(
                new CustomEvent('voice-toggle', {
                    bubbles: true,
                    composed: true,
                }),
            );
            return;
        }
        this._toggleSpeechDictation();
    }

    _toggleSpeechDictation() {
        const SR = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
        if (!SR) {
            this.dispatchEvent(
                new CustomEvent('embed-toast', {
                    detail: { message: this._label('voice_not_supported', 'Voice not supported') },
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
        rec.lang = this._speechLang();
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.onresult = (ev) => {
            const t = ev.results?.[0]?.[0]?.transcript;
            if (typeof t === 'string' && t.trim()) {
                const ta = this.shadowRoot.querySelector('textarea');
                const cur = ta && typeof ta.value === 'string' ? ta.value.trim() : '';
                const next = cur !== '' ? `${cur} ${t.trim()}` : t.trim();
                if (ta) {
                    ta.value = next;
                }
                this._text = next;
                this._listening = false;
                this._rec = null;
                this.requestUpdate();
                this._onSend();
                return;
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

    /**
     * @param {string} text
     */
    setDraft(text) {
        if (typeof text !== 'string') {
            throw new TypeError('embed-chat-input.setDraft expects a string');
        }
        this._text = text;
        this.requestUpdate();
        void this.updateComplete.then(() => {
            const ta = this.shadowRoot?.querySelector('textarea');
            if (!(ta instanceof HTMLTextAreaElement)) {
                throw new Error('embed-chat-input: textarea missing');
            }
            ta.focus();
            const len = text.length;
            ta.setSelectionRange(len, len);
        });
    }

    render() {
        const canSend = this._canSend();
        const locVal = this.interfaceLocale || 'auto';
        const micTitleDuplex = this._composerDuplexMicTitle();
        const micActive =
            this.voiceDuplex === true
                ? this.voiceActive === true ||
                  this.voiceStatus === 'listening' ||
                  this.voiceStatus === 'speaking' ||
                  this.voiceStatus === 'error'
                : this._listening === true;
        const duplexIdleOffVisible = this._composerMicDuplexIdleOff() === true;
        const ariaMic =
            this.voiceDuplex === true
                ? micTitleDuplex
                : this._label('voice_title', 'Voice');
        const duplexMicSvgIdle = html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                      d="M12 14c1.66 0 3-1.34 3-3V6a3 3 0 1 0-6 0v5c0 1.66 1.34 3 3 3Z"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linejoin="round"
                  />
                  <path
                      d="M19 11a7 7 0 1 1-14 0"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                  />
                  <path d="M4 4l16 16" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>`;
        const duplexMicSvgOn = html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                      d="M12 14c1.66 0 3-1.34 3-3V6a3 3 0 1 0-6 0v5c0 1.66 1.34 3 3 3Z"
                      fill="currentColor"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linejoin="round"
                  />
                  <path
                      d="M19 11a7 7 0 1 1-14 0"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                  />
              </svg>`;
        const duplexMicSvg = duplexIdleOffVisible === true ? duplexMicSvgIdle : duplexMicSvgOn;
        const speechMicSvg = html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M12 14a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v4a3 3 0 0 0 3 3z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linejoin="round"
            />
            <path
                d="M8 11v1a4 4 0 0 0 8 0v-1M12 18v3M9 21h6"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
            />
        </svg>`;
        const chips =
            this._files.length > 0
                ? html`
                      <div class="attachments-row" role="list" aria-label=${this._label('attach', 'Attachments')}>
                          ${this._files.map(
                              (f, i) => html`
                                  <span class="attach-chip" role="listitem">
                                      <span class="attach-chip-name" title=${f.name}>${f.name}</span>
                                      <button
                                          type="button"
                                          class="attach-chip-remove"
                                          @click=${() => this._removeFileAt(i)}
                                          aria-label=${this._label('attachment_remove', 'Remove file')}
                                      >
                                          ×
                                      </button>
                                  </span>
                              `,
                          )}
                      </div>
                      ${this._files.length > 1
                          ? html`
                                <button
                                    type="button"
                                    class="attachments-clear-all"
                                    @click=${() => this._removeAllAttachments()}
                                >
                                    ${this._label('attachment_clear_all', 'Remove all attachments')}
                                </button>
                            `
                          : ''}
                  `
                : '';
        return html`
            ${chips}
            <div class="composer">
                <input type="file" multiple @change=${this._onPickFiles} />
                <button
                    type="button"
                    class="circle-btn"
                    ?disabled=${this.loading}
                    @click=${this._openFilePicker}
                    title=${this._label('attach', 'Attachments')}
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path
                            d="M12 5v14M5 12h14"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                        />
                    </svg>
                </button>
                <div class="grow">
                    <textarea
                        rows="1"
                        .value=${this._text}
                        placeholder=${this.placeholder}
                        ?disabled=${this.loading}
                        @input=${this._onInput}
                        @keydown=${this._onKey}
                    ></textarea>
                </div>
                ${this.showLocaleControl
                    ? html`
                          <div class="locale">
                              <select .value=${locVal} @change=${this._onLocaleSelect}>
                                  <option value="auto">${this._label('locale_auto', 'Auto')}</option>
                                  <option value="ru">${this._label('locale_ru', 'Russian')}</option>
                                  <option value="en">${this._label('locale_en', 'English')}</option>
                              </select>
                          </div>
                      `
                    : ''}
                ${this._composerMicVisible() === true
                    ? html`
                          <button
                              type="button"
                              class="circle-btn ${micActive ? 'active' : ''}"
                              ?disabled=${this.loading}
                              @click=${this._onComposerMicClick}
                              title=${ariaMic}
                              aria-label=${ariaMic}
                              aria-pressed=${this.voiceDuplex === true && this.voiceActive === true ? 'true' : 'false'}
                          >
                              ${this.voiceDuplex === true ? duplexMicSvg : speechMicSvg}
                          </button>
                      `
                    : ''}
                ${this.loading
                    ? html`
                          <button
                              type="button"
                              class="circle-btn stop"
                              ?disabled=${this.cancelBusy}
                              @click=${this._embedStop}
                              title=${this.cancelBusy
                                  ? this._label('title_stop_pending', 'Stopping response…')
                                  : this._label('title_stop', 'Stop response')}
                              aria-label=${this.cancelBusy
                                  ? this._label('title_stop_pending', 'Stopping response…')
                                  : this._label('title_stop', 'Stop response')}
                          >
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                  <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
                              </svg>
                          </button>
                      `
                    : html`
                <button
                    type="button"
                    class="circle-btn send-btn ${canSend ? '' : 'muted'}"
                    ?disabled=${!canSend}
                    @click=${this._onSend}
                    title=${this._label('send', 'Send')}
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path
                            d="M12 5v12M6 11l6-6 6 6"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        />
                    </svg>
                </button>
            `}
            </div>
            <div class="disclaimer">
                ${this._label(
                    'ai_disclaimer',
                    'AI-generated content may be inaccurate.',
                )}
            </div>
        `;
    }
}

customElements.define('embed-chat-input', EmbedChatInput);

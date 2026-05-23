/**
 * <platform-assistant-message-actions> — действия над текстом сообщения:
 * озвучить (TTS через voice synthesize), копировать; опционально «исправить»
 * (событие compose-edit для подстановки текста в композер родителя).
 *
 * Презентационный компонент core UI Kit. Не знает про A2A, flows и чат-UI.
 *
 * Подключается в:
 *   - `apps/flows/ui/` — assistant и user сообщения в `chat-message`;
 *   - `core/frontend/static/lib/flows-chat/flows-chat-message.js` — assistant/user.
 *
 * Contract:
 *   - `text` (string, required);
 *   - `voice-base-url` (string, optional) — origin сервиса voice без финального "/" (напр. `https://host/voice`); если задан, POST `/api/v1/synthesize` + Blob в `<audio>`;
 *   - `get-headers` (function, optional);
 *   - `credentials` ('omit'|'include', default 'omit');
 *   - `show-edit` (boolean) — показать кнопку редактирования текста композера;
 *   - `tone` ('default'|'user', default 'default') — стиль кнопок (user-бабл).
 *
 * События (bubbles + composed): `copy`, `play-started`, `play-ended`
 * (в том числе при остановке пользователем — отмена HTTP и audio),
 * `compose-edit` при клике «исправить» с detail `{ text: string }`.
 * Глобальный `platform-tts-barge-in` (window) при `stopStreamTtsPlayback()` — прерывает воспроизведение с кнопки на бабле при новом сообщении в чате.
 */

import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

export class PlatformAssistantMessageActions extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        text: { type: String },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        credentials: { type: String },
        getHeaders: { attribute: false },
        showEdit: { type: Boolean, attribute: 'show-edit', reflect: true },
        tone: { type: String, reflect: true },
        _busyPlay: { state: true },
        _busyCopy: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                gap: var(--assistant-msg-actions-gap, 6px);
            }
            :host(:not([tone='user'])) .action-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.12));
                color: var(--text-secondary, #9ca3af);
            }
            :host(:not([tone='user'])) .action-btn:hover:not([disabled]) {
                background: var(--glass-solid-subtle, rgba(255, 255, 255, 0.05));
                color: var(--text-primary, #f4f4f5);
                border-color: var(--glass-border-medium, rgba(255, 255, 255, 0.18));
            }
            :host([tone='user']) .action-btn {
                background: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.36);
                color: rgba(255, 255, 255, 0.95);
            }
            :host([tone='user']) .action-btn:hover:not([disabled]) {
                background: rgba(255, 255, 255, 0.28);
                border-color: rgba(255, 255, 255, 0.55);
                color: #fff;
            }
            :host(:not([tone='user'])) .action-btn.action-btn--tts-stop {
                color: var(--error, #f43f5e);
                border-color: var(--error-border, rgba(244, 63, 94, 0.35));
                background: var(--error-bg, rgba(244, 63, 94, 0.12));
            }
            :host(:not([tone='user'])) .action-btn.action-btn--tts-stop:hover:not([disabled]) {
                color: var(--error, #f43f5e);
                border-color: var(--error, #f43f5e);
                background: rgba(244, 63, 94, 0.18);
            }
            :host([tone='user']) .action-btn.action-btn--tts-stop {
                color: #fecdd3;
                border-color: rgba(251, 113, 133, 0.7);
                background: rgba(244, 63, 94, 0.28);
            }
            :host([tone='user']) .action-btn.action-btn--tts-stop:hover:not([disabled]) {
                color: #fff;
                border-color: #fb7185;
                background: rgba(244, 63, 94, 0.42);
            }
            .action-btn {
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 30px;
                height: 30px;
                padding: 0;
                margin: 0;
                border-radius: var(--radius-md, 8px);
                font: inherit;
                line-height: 0;
                cursor: pointer;
                transition:
                    background 120ms ease,
                    color 120ms ease,
                    border-color 120ms ease,
                    opacity 120ms ease;
            }
            .action-btn[disabled] {
                opacity: 0.48;
                cursor: default;
            }
            platform-icon {
                display: inline-flex;
            }
            :host([tone='user']) platform-icon {
                color: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this.text = '';
        this.voiceBaseUrl = '';
        this.credentials = 'omit';
        this.getHeaders = null;
        this.showEdit = false;
        this.tone = '';
        this._busyPlay = false;
        this._busyCopy = false;
        this._audio = null;
        this._playAbort = null;
        this._objectUrl = null;
        this._playSessionReject = null;
    }

    _playButtonTitle() {
        return this._busyPlay
            ? this.t('assistant_message_actions.stop')
            : this.t('assistant_message_actions.play');
    }

    _playButtonAria() {
        return this._busyPlay
            ? this.t('assistant_message_actions.stop_aria')
            : this.t('assistant_message_actions.play_aria');
    }

    _editCompose() {
        const raw = typeof this.text === 'string' ? this.text : '';
        if (raw.trim() === '') return;
        this.dispatchEvent(
            new CustomEvent('compose-edit', {
                bubbles: true,
                composed: true,
                detail: { text: raw },
            }),
        );
    }

    async _copy() {
        if (this._busyCopy) return;
        const text = typeof this.text === 'string' ? this.text : '';
        if (text === '') return;
        this._busyCopy = true;
        try {
            await this.copyToClipboard(text, {
                success_i18n_key: 'platform:assistant_message_actions.toast_copied',
                error_i18n_key: 'platform:assistant_message_actions.toast_copy_failed',
            });
            this.dispatchEvent(new CustomEvent('copy', { bubbles: true, composed: true }));
        } finally {
            this._busyCopy = false;
        }
    }

    _finishPlaySession() {
        this._playAbort = null;
        this._playSessionReject = null;
        const audio = this._audio;
        this._audio = null;
        if (audio) {
            audio.pause();
            audio.removeAttribute('src');
            audio.load();
        }
        if (this._objectUrl) {
            URL.revokeObjectURL(this._objectUrl);
            this._objectUrl = null;
        }
        if (this._busyPlay) {
            this._busyPlay = false;
            this.dispatchEvent(new CustomEvent('play-ended', { bubbles: true, composed: true }));
        }
    }

    _cancelPlay() {
        if (this._playAbort) {
            this._playAbort.abort();
        }
        if (this._audio) {
            this._audio.pause();
        }
        if (this._playSessionReject) {
            const sessionReject = this._playSessionReject;
            this._playSessionReject = null;
            sessionReject(new DOMException('Aborted', 'AbortError'));
        }
    }

    _onPlayButtonClick() {
        if (this._busyPlay) {
            this._cancelPlay();
            return;
        }
        void this._runPlay();
    }

    async _runPlay() {
        const text = typeof this.text === 'string' ? this.text : '';
        if (text === '') return;
        if (typeof this.voiceBaseUrl !== 'string' || this.voiceBaseUrl === '') {
            return;
        }
        if (this._busyPlay) return;

        const ac = new AbortController();
        this._playAbort = ac;
        this._busyPlay = true;
        this.dispatchEvent(new CustomEvent('play-started', { bubbles: true, composed: true }));

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (typeof this.getHeaders === 'function') {
                Object.assign(headers, await this.getHeaders());
            }
            const resp = await fetch(
                `${this.voiceBaseUrl.replace(/\/$/, '')}/api/v1/synthesize`,
                {
                    method: 'POST',
                    headers,
                    credentials: this.credentials === 'include' ? 'include' : 'omit',
                    body: JSON.stringify({ text }),
                    signal: ac.signal,
                },
            );
            if (!resp.ok) {
                throw new Error(`synthesize failed: HTTP ${resp.status}`);
            }
            const blob = await resp.blob();
            if (!(blob instanceof Blob) || blob.size === 0) {
                throw new Error('synthesize returned empty audio');
            }
            const objectUrl = URL.createObjectURL(blob);
            this._objectUrl = objectUrl;
            const audioEl = new Audio(objectUrl);
            this._audio = audioEl;

            await new Promise((resolve, reject) => {
                const sessionReject = (err) => {
                    this._playSessionReject = null;
                    reject(err);
                };
                this._playSessionReject = sessionReject;
                audioEl.onended = () => {
                    this._playSessionReject = null;
                    resolve();
                };
                audioEl.onerror = () => sessionReject(new Error('audio playback failed'));
                void audioEl.play().catch(sessionReject);
            });
        } catch (err) {
            const aborted = err && typeof err === 'object' && err.name === 'AbortError';
            if (!aborted) {
                this.toast('platform:assistant_message_actions.toast_play_failed', {
                    type: 'error',
                    vars: { detail: err && err.message ? err.message : String(err) },
                });
            }
        } finally {
            this._finishPlaySession();
        }
    }

    render() {
        const canPlay = typeof this.voiceBaseUrl === 'string' && this.voiceBaseUrl !== '';
        const textOk = typeof this.text === 'string' && this.text.trim() !== '';
        const btnCls = 'action-btn';
        const playBtnCls = this._busyPlay ? `${btnCls} action-btn--tts-stop` : btnCls;
        const playLabel = this._playButtonTitle();
        const speakIcon = html`<platform-icon
            name=${this._busyPlay ? 'stop' : 'volume-up'}
            size="18"
        ></platform-icon>`;

        const copyLabel = this.t('assistant_message_actions.copy');

        const editBtn = this.showEdit
            ? html`<button
                  type="button"
                  class=${btnCls}
                  ?disabled=${!textOk}
                  @click=${this._editCompose}
                  title=${this.t('assistant_message_actions.edit')}
                  aria-label=${this.t('assistant_message_actions.edit_aria')}
              >
                  <platform-icon name="edit" size="18"></platform-icon>
              </button>`
            : '';

        return html`
            ${canPlay
                ? html`<button
                      type="button"
                      class=${playBtnCls}
                      ?disabled=${!textOk}
                      @click=${this._onPlayButtonClick}
                      title=${playLabel}
                      aria-label=${this._playButtonAria()}
                  >
                      ${speakIcon}
                  </button>`
                : ''}
            <button
                type="button"
                class=${btnCls}
                ?disabled=${!textOk || this._busyCopy}
                @click=${this._copy}
                title=${copyLabel}
                aria-label=${this.t('assistant_message_actions.copy_aria')}
            >
                <platform-icon name="copy" size="18"></platform-icon>
            </button>
            ${editBtn}
        `;
    }
}

customElements.define('platform-assistant-message-actions', PlatformAssistantMessageActions);

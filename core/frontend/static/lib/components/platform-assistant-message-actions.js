/**
 * <platform-assistant-message-actions> — набор действий над сообщением
 * ассистента: Copy и Play (озвучить).
 *
 * Презентационный компонент core UI Kit. Не знает про A2A, flows и чат-UI.
 *
 * Подключается в:
 *   - `apps/flows/ui/` в шаблоне assistant-сообщения;
 *   - `core/frontend/static/lib/embed-chat/platform-embed-chat.js` в шаблоне
 *     assistant-сообщения для embed-чата.
 *
 * Contract:
 *   - `text` (string, required) — текст сообщения;
 *   - `voice-base-url` (string, optional) — origin + prefix сервиса voice
 *     без завершающего "/" (например `https://host/voice`); если задан,
 *     показывается кнопка Play, кликом которой делается POST
 *     `/api/v1/synthesize` и Blob проигрывается через `<audio>`;
 *   - `get-headers` (function, optional) — async провайдер доп.
 *     заголовков (Authorization);
 *   - `credentials` ('omit'|'include', default 'omit').
 *
 * События (DOM, composed): `copy` после успешного копирования,
 * `play-started` / `play-ended` вокруг воспроизведения.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class PlatformAssistantMessageActions extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        text: { type: String },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        credentials: { type: String },
        getHeaders: { attribute: false },
        _busyPlay: { state: true },
        _busyCopy: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                gap: 6px;
            }
            button {
                background: transparent;
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.12));
                color: var(--text-secondary, #9ca3af);
                font: inherit;
                font-size: 12px;
                line-height: 1;
                padding: 4px 8px;
                border-radius: 999px;
                cursor: pointer;
                transition: background 120ms, color 120ms, border-color 120ms;
            }
            button[disabled] { opacity: 0.5; cursor: default; }
            button:hover:not([disabled]) {
                background: var(--glass-solid-subtle, rgba(255,255,255,0.05));
                color: var(--text-primary, #f4f4f5);
            }
        `,
    ];

    constructor() {
        super();
        this.text = '';
        this.voiceBaseUrl = '';
        this.credentials = 'omit';
        this.getHeaders = null;
        this._busyPlay = false;
        this._busyCopy = false;
        this._audio = null;
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

    async _play() {
        if (this._busyPlay) return;
        const text = typeof this.text === 'string' ? this.text : '';
        if (text === '') return;
        if (typeof this.voiceBaseUrl !== 'string' || this.voiceBaseUrl === '') {
            return;
        }
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
            const audioEl = new Audio(objectUrl);
            try {
                this._audio = audioEl;
                await new Promise((resolve, reject) => {
                    audioEl.onended = () => resolve();
                    audioEl.onerror = () => reject(new Error('audio playback failed'));
                    audioEl.play().catch(reject);
                });
            } finally {
                URL.revokeObjectURL(objectUrl);
                if (this._audio === audioEl) {
                    this._audio = null;
                }
            }
        } catch (err) {
            this.toast('platform:assistant_message_actions.toast_play_failed', {
                type: 'error',
                vars: { detail: err && err.message ? err.message : String(err) },
            });
        } finally {
            this._busyPlay = false;
            this.dispatchEvent(new CustomEvent('play-ended', { bubbles: true, composed: true }));
        }
    }

    render() {
        const canPlay = typeof this.voiceBaseUrl === 'string' && this.voiceBaseUrl !== '';
        const textOk = typeof this.text === 'string' && this.text !== '';
        return html`
            ${canPlay
                ? html`<button
                        type="button"
                        ?disabled=${!textOk || this._busyPlay}
                        @click=${this._play}
                        title=${this.t('assistant_message_actions.play')}
                    >
                        ${this._busyPlay
                            ? this.t('assistant_message_actions.play_busy')
                            : this.t('assistant_message_actions.play')}
                    </button>`
                : ''}
            <button
                type="button"
                ?disabled=${!textOk || this._busyCopy}
                @click=${this._copy}
                title=${this.t('assistant_message_actions.copy')}
            >
                ${this.t('assistant_message_actions.copy')}
            </button>
        `;
    }
}

customElements.define('platform-assistant-message-actions', PlatformAssistantMessageActions);

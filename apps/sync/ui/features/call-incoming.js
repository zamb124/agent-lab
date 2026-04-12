/**
 * CallIncoming — баннер входящего звонка.
 *
 * Получает данные через атрибуты:
 *   call-id, call-type, channel-name, caller-name
 *
 * Испускает события:
 *   call-accept  — пользователь принял
 *   call-decline — пользователь отклонил
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/platform-icon.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';

class CallIncoming extends PlatformElement {
    static properties = {
        callId:      { type: String, attribute: 'call-id' },
        callType:    { type: String, attribute: 'call-type' },
        channelName: { type: String, attribute: 'channel-name' },
        callerName:  { type: String, attribute: 'caller-name' },
        _ringing: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
        :host {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: var(--platform-modal-layer-z, var(--z-max, 9999));
        }

        .banner {
            background: var(--glass-solid-strong, rgba(20,20,30,0.92));
            border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.14));
            border-radius: 20px;
            padding: 20px 24px;
            min-width: 280px;
            max-width: 340px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            backdrop-filter: blur(20px);
            box-shadow: 0 16px 40px rgba(0,0,0,0.5);
            animation: slide-in 0.25s ease;
        }

        @keyframes slide-in {
            from { transform: translateX(120%); opacity: 0; }
            to   { transform: translateX(0); opacity: 1; }
        }

        .top {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .icon {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: var(--accent-primary, #6366f1);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            flex-shrink: 0;
            animation: pulse 1.2s ease infinite;
        }

        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0.5); }
            50%       { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
        }

        .info { min-width: 0; }

        .label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-tertiary, rgba(255,255,255,0.4));
            margin-bottom: 2px;
        }

        .title {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-primary, #fff);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .subtitle {
            font-size: 13px;
            color: var(--text-secondary, rgba(255,255,255,0.55));
        }

        .actions {
            display: flex;
            gap: 10px;
        }

        .btn {
            flex: 1;
        }

        .btn-accept {
            background: #22c55e;
            color: #fff;
        }
        .btn-accept:hover { background: #16a34a; }

        .btn-decline {
            background: rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.7);
            border: 1px solid rgba(255,255,255,0.12);
        }
        .btn-decline:hover { background: rgba(239,68,68,0.25); color: #fff; }
    `,
    ];

    constructor() {
        super();
        this._ringing = true;
        this._audio = null;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this.style.setProperty(
            '--platform-modal-layer-z',
            String(nextModalLayerZIndex()),
        );
        this._startRinging();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._stopRinging();
    }

    _startRinging() {
        try {
            this._audio = new Audio('/static/core/assets/sounds/call-ringtone.mp3');
            this._audio.loop = true;
            this._audio.volume = 0.6;
            this._audio.play().catch(() => {});
        } catch { /* optional sound */ }
    }

    _stopRinging() {
        if (this._audio) { this._audio.pause(); this._audio = null; }
    }

    _accept() {
        this._stopRinging();
        this.dispatchEvent(new CustomEvent('call-accept', {
            bubbles: true, composed: true, detail: { callId: this.callId },
        }));
    }

    _decline() {
        this._stopRinging();
        this.dispatchEvent(new CustomEvent('call-decline', {
            bubbles: true, composed: true, detail: { callId: this.callId },
        }));
    }

    render() {
        return html`
            <div class="banner">
                <div class="top">
                    <div class="icon" aria-hidden="true">
                        <platform-icon name="phone-call" size="22" filled aria-hidden="true"></platform-icon>
                    </div>
                    <div class="info">
                        <div class="label">${this._tp('call_incoming.incoming_label')}</div>
                        <div class="title">${this.channelName ?? this._tp('chat_view.call')}</div>
                        <div class="subtitle">${this.callerName}</div>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-accept" @click=${this._accept}>${this._tp('call_incoming.accept')}</button>
                    <button class="btn btn-decline" @click=${this._decline}>${this._tp('call_incoming.decline')}</button>
                </div>
            </div>
        `;
    }
}

customElements.define('call-incoming', CallIncoming);

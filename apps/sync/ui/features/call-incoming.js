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
import { html, css, LitElement } from 'lit';

class CallIncoming extends LitElement {
    static properties = {
        callId:      { type: String, attribute: 'call-id' },
        callType:    { type: String, attribute: 'call-type' },
        channelName: { type: String, attribute: 'channel-name' },
        callerName:  { type: String, attribute: 'caller-name' },
        _ringing: { state: true },
    };

    static styles = css`
        :host {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
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
            padding: 10px;
            border-radius: 12px;
            border: none;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.15s;
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
    `;

    constructor() {
        super();
        this._ringing = true;
        this._audio = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._startRinging();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopRinging();
    }

    _startRinging() {
        try {
            this._audio = new Audio('/static/core/assets/sounds/call-ringtone.mp3');
            this._audio.loop = true;
            this._audio.volume = 0.6;
            this._audio.play().catch(() => {});
        } catch { /* звук необязателен */ }
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
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
                        </svg>
                    </div>
                    <div class="info">
                        <div class="label">Входящий звонок</div>
                        <div class="title">${this.channelName ?? 'Звонок'}</div>
                        <div class="subtitle">${this.callerName}</div>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-accept" @click=${this._accept}>Принять</button>
                    <button class="btn btn-decline" @click=${this._decline}>Отклонить</button>
                </div>
            </div>
        `;
    }
}

customElements.define('call-incoming', CallIncoming);

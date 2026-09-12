/**
 * Chrome toast stack for Flow UI turn activity on non-conversation pages.
 * Presentational only — no document mutation, no platform EventBus toast bus.
 */
import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';

const AUTO_DISMISS_MS = 8000;

export class FlowUITurnToasts extends LitElement {
    static properties = {
        toasts: { attribute: false },
        locale: { type: String },
        _dismissedIds: { state: true },
    };

    static styles = css`
        :host {
            position: absolute;
            inset: auto 12px 12px auto;
            z-index: 20;
            display: grid;
            gap: var(--flow-ui-space-2, 8px);
            width: min(360px, calc(100% - 24px));
            pointer-events: none;
        }
        .toast {
            pointer-events: auto;
            display: grid;
            gap: 6px;
            padding: 12px 14px;
            border: 1px solid var(--flow-ui-border, var(--border-subtle));
            border-radius: var(--flow-ui-radius-lg, 16px);
            background: var(--flow-ui-panel-strong, var(--glass-solid-medium, rgba(22, 33, 62, 0.94)));
            color: var(--flow-ui-text, var(--text-primary));
            box-shadow: var(--flow-ui-panel-shadow, 0 10px 28px color-mix(in srgb, #000 28%, transparent));
            backdrop-filter: blur(14px);
            animation: toast-in 160ms ease;
        }
        .toast[data-kind='error'] {
            border-color: color-mix(in srgb, var(--flow-ui-danger, var(--error, #ff718d)) 55%, transparent);
        }
        .toast[data-kind='response'] {
            border-color: color-mix(in srgb, var(--flow-ui-accent, var(--accent)) 45%, transparent);
        }
        .head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 10px;
        }
        .title-row {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
            font-weight: 700;
            font-size: var(--flow-ui-font-size-xs, 12px);
            letter-spacing: 0.01em;
            color: var(--flow-ui-heading, var(--text-primary));
        }
        .pulse {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--flow-ui-accent, var(--accent));
            box-shadow: 0 0 0 0 color-mix(in srgb, var(--flow-ui-accent, var(--accent)) 55%, transparent);
            animation: pulse 1.2s ease infinite;
            flex-shrink: 0;
        }
        .toast[data-kind='error'] .pulse {
            background: var(--error, #ff718d);
            animation: none;
        }
        .body {
            margin: 0;
            color: var(--flow-ui-muted, var(--text-secondary));
            font-size: var(--flow-ui-font-size-xs, 12px);
            line-height: var(--flow-ui-line-height, 1.6);
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            max-height: 9.5em;
            overflow: auto;
        }
        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            justify-content: flex-end;
        }
        button {
            min-height: 30px;
            padding: 5px 10px;
            border: 1px solid var(--flow-ui-border, var(--border-subtle));
            border-radius: var(--flow-ui-radius-sm, 8px);
            background: transparent;
            color: var(--flow-ui-text, var(--text-primary));
            cursor: pointer;
            font: inherit;
            font-size: 11px;
            font-weight: 650;
            transition: var(--flow-ui-transition);
        }
        button.primary {
            background: var(--flow-ui-accent, var(--accent));
            border-color: transparent;
            color: var(--flow-ui-on-accent, #fff);
        }
        button:focus-visible {
            outline: none;
            box-shadow: var(--flow-ui-focus-ring);
        }
        @keyframes toast-in {
            from { opacity: 0; transform: translateY(8px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--flow-ui-accent, var(--accent)) 45%, transparent); }
            70% { box-shadow: 0 0 0 8px transparent; }
            100% { box-shadow: 0 0 0 0 transparent; }
        }
        @media (prefers-reduced-motion: reduce) {
            .toast { animation: none; }
            .pulse { animation: none; }
            button { transition: none; }
        }
    `;

    constructor() {
        super();
        this.toasts = [];
        this.locale = 'en';
        this._dismissedIds = new Set();
        this._autoDismissTimers = new Map();
    }

    disconnectedCallback() {
        for (const timer of this._autoDismissTimers.values()) {
            clearTimeout(timer);
        }
        this._autoDismissTimers.clear();
        super.disconnectedCallback();
    }

    updated(changed) {
        if (!changed.has('toasts')) return;
        const visible = this._visibleToasts();
        const responseToast = visible.find((toast) => toast.kind === 'response' && toast.streaming === false);
        if (responseToast && !this._autoDismissTimers.has(responseToast.id)) {
            const timer = setTimeout(() => {
                this._dismiss(responseToast.id);
            }, AUTO_DISMISS_MS);
            this._autoDismissTimers.set(responseToast.id, timer);
        }
        for (const [id, timer] of [...this._autoDismissTimers.entries()]) {
            if (!visible.some((toast) => toast.id === id)) {
                clearTimeout(timer);
                this._autoDismissTimers.delete(id);
            }
        }
    }

    _visibleToasts() {
        const list = Array.isArray(this.toasts) ? this.toasts : [];
        return list.filter((toast) => toast && !this._dismissedIds.has(toast.id));
    }

    _dismiss(toastId) {
        if (typeof toastId !== 'string' || toastId === '') {
            throw new Error('flow-ui-turn-toasts: toast id required');
        }
        const next = new Set(this._dismissedIds);
        next.add(toastId);
        this._dismissedIds = next;
        const timer = this._autoDismissTimers.get(toastId);
        if (timer) {
            clearTimeout(timer);
            this._autoDismissTimers.delete(toastId);
        }
    }

    _cancel() {
        this.dispatchEvent(new CustomEvent('turn-toast-cancel', {
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        const locale = resolveFlowUILocale(this.locale);
        const toasts = this._visibleToasts();
        if (toasts.length === 0) return nothing;
        return html`${toasts.map((toast) => html`
            <article
                class="toast"
                data-kind=${toast.kind}
                role=${toast.kind === 'error' ? 'alert' : 'status'}
                aria-live=${toast.kind === 'error' ? 'assertive' : 'polite'}
            >
                <div class="head">
                    <div class="title-row">
                        ${toast.streaming ? html`<span class="pulse" aria-hidden="true"></span>` : nothing}
                        <span>${toast.title}</span>
                    </div>
                    <div class="actions">
                        ${toast.canCancel
                            ? html`<button type="button" class="primary" @click=${() => this._cancel()}>
                                ${flowUIText(locale, 'turn_toast_stop')}
                            </button>`
                            : nothing}
                        ${toast.dismissible
                            ? html`<button type="button" @click=${() => this._dismiss(toast.id)}>
                                ${flowUIText(locale, 'turn_toast_dismiss')}
                            </button>`
                            : nothing}
                    </div>
                </div>
                ${toast.body
                    ? html`<p class="body">${toast.body}</p>`
                    : nothing}
            </article>
        `)}`;
    }
}

if (!customElements.get('flow-ui-turn-toasts')) {
    customElements.define('flow-ui-turn-toasts', FlowUITurnToasts);
}

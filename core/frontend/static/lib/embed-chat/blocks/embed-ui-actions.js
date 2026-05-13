import { LitElement, html, css } from '../lit-shim.js';

export class EmbedUiActions extends LitElement {
    static properties = {
        buttons: { type: Array },
    };

    constructor() {
        super();
    }

    static styles = css`
        :host {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            position: relative;
            z-index: 2;
            pointer-events: auto;
        }
        button {
            position: relative;
            z-index: 1;
            pointer-events: auto;
            touch-action: manipulation;
            border-radius: var(--embed-radius, 25px);
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.2));
            background: var(--embed-chat-accent-muted, rgba(153, 166, 249, 0.2));
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
        }
        button:hover {
            background: var(--embed-chat-accent, rgba(153, 166, 249, 0.35));
        }
    `;

    disconnectedCallback() {
        this._clearNativeHandlers();
        super.disconnectedCallback();
    }

    firstUpdated(changedProps) {
        super.firstUpdated(changedProps);
        this._wireNativeButtonHandlers();
    }

    updated(changedProps) {
        super.updated(changedProps);
        this._wireNativeButtonHandlers();
    }

    _clearNativeHandlers() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        root.querySelectorAll('button[data-embed-action-index]').forEach((n) => {
            if (n instanceof HTMLButtonElement) {
                n.onclick = null;
            }
        });
    }

    /**
     * Явный `HTMLElement.onclick`: работает после Lit-render и не ломает доставку события
     * (capture + stopPropagation на shadowRoot блокируют клик до button — так кнопка «мёртвая»).
     */
    _wireNativeButtonHandlers() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        const btns = Array.isArray(this.buttons) ? this.buttons : [];
        root.querySelectorAll('button[data-embed-action-index]').forEach((node) => {
            if (!(node instanceof HTMLButtonElement) || node.type !== 'button' || node.disabled) {
                return;
            }
            const raw = node.getAttribute('data-embed-action-index');
            const idx = raw != null ? Number.parseInt(String(raw), 10) : Number.NaN;
            const payload = Number.isFinite(idx) ? btns[idx] : undefined;
            if (!payload || typeof payload !== 'object') {
                node.onclick = null;
                return;
            }
            node.onclick = (event) => {
                if (event && typeof event.stopPropagation === 'function') {
                    event.stopPropagation();
                }
                if (event && typeof event.preventDefault === 'function') {
                    event.preventDefault();
                }
                this._onClick(payload);
            };
        });
    }

    _onClick(btn) {
        const actionIdRaw = btn?.action_id;
        const actionKindRaw = btn?.action_kind;
        const actionId = typeof actionIdRaw === 'string' ? actionIdRaw.trim() : '';
        const actionKind = typeof actionKindRaw === 'string' ? actionKindRaw.trim() : '';
        if (!actionId || !actionKind) {
            this.dispatchEvent(
                new CustomEvent('embed-action-config-error', {
                    bubbles: true,
                    composed: true,
                    detail: {
                        reason: 'missing_action_id_or_kind',
                        message:
                            'Кнопка действия без action_id/action_kind — обновите ответ или повторите запрос.',
                    },
                }),
            );
            return;
        }
        this.dispatchEvent(
            new CustomEvent('embed-block-action', {
                bubbles: true,
                composed: true,
                detail: {
                    action_id: actionId,
                    action_kind: actionKind,
                    pending_action_id:
                        typeof btn?.pending_action_id === 'string' && btn.pending_action_id.trim()
                            ? btn.pending_action_id.trim()
                            : null,
                    arguments:
                        btn?.arguments && typeof btn.arguments === 'object' && !Array.isArray(btn.arguments)
                            ? btn.arguments
                            : {},
                    context:
                        btn?.context && typeof btn.context === 'object' && !Array.isArray(btn.context)
                            ? btn.context
                            : {},
                },
            }),
        );
    }

    render() {
        const btns = Array.isArray(this.buttons) ? this.buttons : [];
        return html`
            ${btns.map(
                (b, i) => html`
                    <button type="button" data-embed-action-index=${String(i)}>
                        ${b.label || b.action_id || 'Action'}
                    </button>
                `,
            )}
        `;
    }
}

customElements.define('embed-ui-actions', EmbedUiActions);

import { LitElement, html, css } from '../lit-shim.js';

export class EmbedUiActions extends LitElement {
    static properties = {
        buttons: { type: Array },
    };

    static styles = css`
        :host {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        button {
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

    _onClick(btn) {
        const actionIdRaw = btn?.action_id;
        const actionKindRaw = btn?.action_kind;
        const actionId = typeof actionIdRaw === 'string' ? actionIdRaw.trim() : '';
        const actionKind = typeof actionKindRaw === 'string' ? actionKindRaw.trim() : '';
        if (!actionId || !actionKind) {
            throw new Error('embed-ui-actions: button must include non-empty action_id and action_kind');
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
                (b) => html`
                    <button type="button" @click=${() => this._onClick(b)}>
                        ${b.label || b.action_id || 'Action'}
                    </button>
                `,
            )}
        `;
    }
}

customElements.define('embed-ui-actions', EmbedUiActions);

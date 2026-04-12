import { LitElement, html, css } from 'lit';

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
        this.dispatchEvent(
            new CustomEvent('embed-block-action', {
                bubbles: true,
                composed: true,
                detail: {
                    action_id: btn.action_id,
                    payload: btn.payload ?? {},
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

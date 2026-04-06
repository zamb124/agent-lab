import { LitElement, html, css } from 'lit';

export class EmbedUiFallback extends LitElement {
    static properties = {
        typeId: { type: String, attribute: 'type-id' },
        raw: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            font-size: 12px;
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.55));
            padding: 8px;
            border: 1px dashed var(--embed-chat-border, rgba(255, 255, 255, 0.2));
            border-radius: 8px;
        }
    `;

    render() {
        return html`<span>Unsupported block type: ${this.typeId || 'unknown'}</span>`;
    }
}

customElements.define('embed-ui-fallback', EmbedUiFallback);

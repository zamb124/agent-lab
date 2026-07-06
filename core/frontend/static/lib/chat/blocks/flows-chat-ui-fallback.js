import { LitElement, html, css } from '../../lit-shim.js';

export class FlowsChatUiFallback extends LitElement {
    static properties = {
        typeId: { type: String, attribute: 'type-id' },
        raw: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            font-size: 12px;
            color: var(--flows-chat-muted, rgba(255, 255, 255, 0.55));
            padding: 8px;
            border: 1px dashed var(--flows-chat-border, rgba(255, 255, 255, 0.2));
            border-radius: var(--flows-chat-radius, 8px);
        }
    `;

    render() {
        return html`<span>Unsupported block type: ${this.typeId || 'unknown'}</span>`;
    }
}

customElements.define('flows-chat-ui-fallback', FlowsChatUiFallback);

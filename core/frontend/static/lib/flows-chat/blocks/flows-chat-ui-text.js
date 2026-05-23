import { LitElement, html, css } from '../../lit-shim.js';

export class FlowsChatUiText extends LitElement {
    static properties = {
        text: { type: String },
    };

    static styles = css`
        :host {
            display: block;
            font-size: 14px;
            line-height: 1.45;
            color: var(--flows-chat-text, rgba(255, 255, 255, 0.88));
            white-space: pre-wrap;
        }
    `;

    render() {
        return html`${this.text || ''}`;
    }
}

customElements.define('flows-chat-ui-text', FlowsChatUiText);

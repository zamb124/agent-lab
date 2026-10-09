import { LitElement, css, html } from '../../lit-shim.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';

export class FlowUIErrorBoundary extends LitElement {
    declare error: Error | string | null;
    declare locale: string;

    static override properties = { error: { attribute: false }, locale: { type: String } };
    static override styles = css`
        :host { display: block; padding: 20px; }
        .error { padding: 18px; border: 1px solid rgba(255, 104, 130, .35); border-radius: 16px; background: rgba(115, 23, 47, .2); color: #ffd7df; }
        strong { display: block; margin-bottom: 5px; }
    `;
    constructor() { super(); this.error = null; this.locale = 'auto'; }
    override render() {
        const locale = resolveFlowUILocale(this.locale);
        return html`<div class="error" role="alert"><strong>${flowUIText(locale, 'interface_unavailable')}</strong>${this.error instanceof Error ? this.error.message : String(this.error || flowUIText(locale, 'unknown_error'))}</div>`;
    }
}
if (!customElements.get('flow-ui-error-boundary')) customElements.define('flow-ui-error-boundary', FlowUIErrorBoundary);

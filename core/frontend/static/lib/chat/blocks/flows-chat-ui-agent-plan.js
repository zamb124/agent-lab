/**
 * Chat block type=agent_plan — thin host над <platform-agent-plan>.
 */

import { LitElement, html, css, nothing } from '../../lit-shim.js';
import '../../components/platform-agent-plan.js';

export class FlowsChatUiAgentPlan extends LitElement {
    static properties = {
        plan: { attribute: false },
    };

    static styles = css`
        :host {
            display: block;
        }
        platform-agent-plan {
            --surface-elevated: var(--flows-chat-surface, rgba(255, 255, 255, 0.06));
            --border-subtle: var(--flows-chat-border, rgba(255, 255, 255, 0.12));
            --text-primary: var(--flows-chat-text, rgba(255, 255, 255, 0.92));
            --text-muted: var(--flows-chat-muted, rgba(255, 255, 255, 0.55));
        }
    `;

    render() {
        if (!this.plan || typeof this.plan !== 'object') {
            return nothing;
        }
        return html`<platform-agent-plan .plan=${this.plan} compact></platform-agent-plan>`;
    }
}

customElements.define('flows-chat-ui-agent-plan', FlowsChatUiAgentPlan);

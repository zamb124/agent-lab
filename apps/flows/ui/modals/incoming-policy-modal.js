/**
 * Выбор incoming_policy (fan-in): any | all для ноды с входящими связями.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class IncomingPolicyModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            .policy-subtitle {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin: 0 0 var(--space-5);
                font-family: var(--font-mono);
            }

            .policy-cards {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
            }

            @media (max-width: 520px) {
                .policy-cards {
                    grid-template-columns: 1fr;
                }
            }

            .policy-card {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-5);
                margin: 0;
                border-radius: var(--radius-lg);
                border: 2px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                cursor: pointer;
                text-align: center;
                transition:
                    border-color var(--duration-fast) var(--easing-default),
                    background var(--duration-fast) var(--easing-default),
                    box-shadow var(--duration-fast) var(--easing-default);
                color: var(--text-primary);
                font: inherit;
            }

            .policy-card:hover {
                border-color: var(--border-medium);
                background: var(--glass-tint-medium);
            }

            .policy-card.selected {
                border-color: var(--accent);
                box-shadow: 0 0 0 1px var(--accent-subtle);
                background: var(--accent-subtle);
            }

            .policy-card-icon {
                width: 72px;
                height: 72px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .policy-card.selected .policy-card-icon {
                color: var(--accent);
            }

            .policy-card-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .policy-card-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.45;
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        targetNodeId: { type: String },
        drawflowId: { type: String },
        selectedPolicy: { type: String },
    };

    constructor() {
        super();
        this.size = 'md';
        this.targetNodeId = '';
        this.drawflowId = '';
        this.selectedPolicy = 'any';
    }

    openFor({ nodeId, drawflowId, policy }) {
        this.targetNodeId = nodeId || '';
        this.drawflowId = drawflowId != null ? String(drawflowId) : '';
        this.selectedPolicy = policy === 'all' ? 'all' : 'any';
        this.requestUpdate();
        this.showModal();
    }

    renderHeader() {
        return this.i18n.t('flow_canvas.incoming_policy_modal.title');
    }

    _iconAny() {
        return html`
            
<svg id="icons" height="512" viewBox="0 0 24 24" width="512" xmlns="http://www.w3.org/2000/svg"><path d="m4 13h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z"/><path d="m20 5h-16a1 1 0 0 0 0 2h16a1 1 0 0 0 0-2z"/><path d="m4 19h16a1 1 0 0 0 0-2h-16a1 1 0 0 0 0 2z"/></svg>
        `;
    }

    _iconAll() {
        return html`
            

            <svg id="Layer_1" enable-background="new 0 0 24 24" height="512" viewBox="0 0 24 24" width="512" xmlns="http://www.w3.org/2000/svg"><path d="m20 14.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"/><path d="m20 6.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"/><path d="m20 22.3c1.2 0 2.3-1 2.3-2.3s-1-2.3-2.3-2.3-2.3 1-2.3 2.3 1.1 2.3 2.3 2.3z"/><path d="m4 14.3c1.2 0 2.3-1 2.3-2.3s-1.1-2.2-2.3-2.2-2.3 1-2.3 2.3 1.1 2.2 2.3 2.2z"/><path d="m19 12.8c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-7.3v-4.2c0-1.6.7-2.3 2.3-2.3h5c.4 0 .8-.3.8-.8s-.4-.6-.8-.6h-5c-2.4 0-3.8 1.3-3.8 3.8v4.3h-5.2c-.4 0-.8.3-.8.8s.3.8.8.8h5.3v4c0 2.4 1.3 3.8 3.8 3.8h5c.4 0 .8-.3.8-.8s-.3-.8-.8-.8h-5c-1.6 0-2.3-.7-2.3-2.3v-4.3h7.2z"/></svg>
        `;
    }

    _pick(policy) {
        this.emit('incoming-policy-saved', {
            nodeId: this.targetNodeId,
            drawflowId: this.drawflowId,
            incoming_policy: policy,
        });
        this.close();
    }

    renderBody() {
        const t = (k) => this.i18n.t(k);
        return html`
            <p class="policy-subtitle">${this.targetNodeId}</p>
            <div class="policy-cards">
                <button
                    type="button"
                    class="policy-card ${this.selectedPolicy === 'any' ? 'selected' : ''}"
                    @click=${() => this._pick('any')}
                >
                    <div class="policy-card-icon">${this._iconAny()}</div>
                    <span class="policy-card-title">${t('flow_canvas.incoming_policy_modal.option_any_title')}</span>
                    <span class="policy-card-desc">${t('flow_canvas.incoming_policy_modal.option_any_desc')}</span>
                </button>
                <button
                    type="button"
                    class="policy-card ${this.selectedPolicy === 'all' ? 'selected' : ''}"
                    @click=${() => this._pick('all')}
                >
                    <div class="policy-card-icon">${this._iconAll()}</div>
                    <span class="policy-card-title">${t('flow_canvas.incoming_policy_modal.option_all_title')}</span>
                    <span class="policy-card-desc">${t('flow_canvas.incoming_policy_modal.option_all_desc')}</span>
                </button>
            </div>
        `;
    }

    renderFooter() {
        return html``;
    }
}

customElements.define('incoming-policy-modal', IncomingPolicyModal);

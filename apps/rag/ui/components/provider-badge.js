/**
 * Provider Badge - индикатор текущего провайдера в sidebar
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class ProviderBadge extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                margin-bottom: var(--space-4);
            }
            
            .badge {
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
            }
            
            .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .provider-info {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .status {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 8px var(--success);
            }
            
            .provider-name {
                font-weight: 600;
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
        `
    ];
    
    constructor() {
        super();
        this.state = this.use(s => ({
            currentProvider: s.providers.current,
        }));
    }
    
    render() {
        const { currentProvider } = this.state.value;
        
        return html`
            <div class="badge">
                <div class="label">Provider</div>
                <div class="provider-info">
                    <span class="status"></span>
                    <span class="provider-name">${currentProvider}</span>
                </div>
            </div>
        `;
    }
}

customElements.define('provider-badge', ProviderBadge);

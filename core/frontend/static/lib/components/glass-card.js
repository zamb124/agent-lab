/**
 * Компонент Glass Card
 * Карточка с glass morphism-эффектом
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class GlassCard extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                box-shadow: var(--glass-shadow-medium), var(--glass-inner-glow-medium);
                transition: var(--motion-transition-interactive);
            }
            
            :host([interactive]:hover) {
                border-color: var(--glass-border-glow);
                box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-medium), var(--hover-glow);
                transform: translateY(-2px);
            }
            
            :host([compact]) {
                padding: var(--space-4);
            }
        `
    ];

    static properties = {
        interactive: { type: Boolean },
        compact: { type: Boolean },
    };

    constructor() {
        super();
        this.interactive = false;
        this.compact = false;
    }

    render() {
        return html`<slot></slot>`;
    }
}

customElements.define('glass-card', GlassCard);

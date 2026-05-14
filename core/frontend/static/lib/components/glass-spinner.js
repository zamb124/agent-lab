/**
 * Glass Spinner Component
 * Индикатор загрузки
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class GlassSpinner extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                vertical-align: middle;
            }
            
            .spinner {
                box-sizing: border-box;
                flex-shrink: 0;
                width: var(--spinner-size, 24px);
                height: var(--spinner-size, 24px);
                min-width: var(--spinner-size, 24px);
                min-height: var(--spinner-size, 24px);
                border: 2px solid var(--glass-border-medium);
                border-top-color: var(--accent);
                border-radius: 50%;
                animation: spin 0.6s linear infinite;
            }
            
            :host([size="sm"]) .spinner {
                --spinner-size: 16px;
                border-width: 2px;
            }
            
            :host([size="md"]) .spinner {
                --spinner-size: 24px;
                border-width: 2px;
            }
            
            :host([size="lg"]) .spinner {
                --spinner-size: 32px;
                border-width: 3px;
            }
            
            @keyframes spin {
                to {
                    transform: rotate(360deg);
                }
            }
        `
    ];

    static properties = {
        size: { type: String },
    };

    constructor() {
        super();
        this.size = 'md';
    }

    render() {
        return html`<div class="spinner"></div>`;
    }
}

customElements.define('glass-spinner', GlassSpinner);


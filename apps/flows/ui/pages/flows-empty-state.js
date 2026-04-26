/**
 * FlowsEmptyState — заглушка-приветствие, когда не выбран flow.
 * Используется на корневом маршруте `/flows`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsEmptyState extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8);
                box-sizing: border-box;
                color: var(--text-secondary);
                font-size: var(--text-base);
            }
            .wrapper {
                max-width: 480px;
                text-align: center;
            }
            h1 {
                font-size: var(--text-2xl);
                color: var(--text-primary);
                margin: 0 0 var(--space-3);
            }
            p {
                margin: 0;
                line-height: 1.6;
            }
        `,
    ];

    render() {
        return html`
            <div class="wrapper">
                <h1>${this.t('flows_empty_state.title')}</h1>
                <p>${this.t('flows_empty_state.body')}</p>
            </div>
        `;
    }
}

customElements.define('flows-empty-state', FlowsEmptyState);

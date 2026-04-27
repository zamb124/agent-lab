/**
 * FlowsEmptyState — заглушка-приветствие, когда не выбран flow.
 * Используется на корневом маршруте `/flows`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';

export class FlowsEmptyState extends PlatformElement {
    static i18nNamespace = 'flows';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
                box-sizing: border-box;
                color: var(--text-secondary);
                font-size: var(--text-base);
            }
            .body {
                flex: 1;
                min-height: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8);
                box-sizing: border-box;
            }
            .wrapper {
                max-width: 480px;
                text-align: center;
            }
            .lead {
                font-size: var(--text-2xl);
                color: var(--text-primary);
                margin: 0 0 var(--space-3);
                font-weight: var(--font-semibold);
            }
            p {
                margin: 0;
                line-height: 1.6;
            }
        `,
    ];

    render() {
        return html`
            <page-header title=${this.t('flows_empty_state.header_title')}></page-header>
            <div class="body">
                <div class="wrapper">
                    <div class="lead">${this.t('flows_empty_state.title')}</div>
                    <p>${this.t('flows_empty_state.body')}</p>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-empty-state', FlowsEmptyState);

/**
 * WorktrackerPageHeader — unified page title + toolbar actions.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-breadcrumbs.js';

export class WorktrackerPageHeader extends PlatformElement {
    static properties = {
        title: { type: String },
        showBreadcrumbs: { type: Boolean, attribute: 'show-breadcrumbs' },
        breadcrumbLabel: { type: String, attribute: 'breadcrumb-label' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                flex-shrink: 0;
                margin-bottom: var(--space-4);
            }
            .row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: 40px;
            }
            .title {
                font-size: var(--text-2xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                letter-spacing: var(--tracking-tight);
                margin: 0;
                flex: 1;
                min-width: 0;
            }
            .actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.title = '';
        this.showBreadcrumbs = false;
        this.breadcrumbLabel = '';
    }

    render() {
        const breadcrumb = typeof this.breadcrumbLabel === 'string' && this.breadcrumbLabel.length > 0
            ? this.breadcrumbLabel
            : this.title;
        return html`
            ${this.showBreadcrumbs ? html`
                <platform-breadcrumbs current-label=${breadcrumb}></platform-breadcrumbs>
            ` : nothing}
            <div class="row">
                <h1 class="title">${this.title}</h1>
                <div class="actions">
                    <slot name="actions"></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('worktracker-page-header', WorktrackerPageHeader);

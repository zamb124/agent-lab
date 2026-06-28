/**
 * Frontend Console — страница переменных компании.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/variables/platform-company-variables-panel.js';

export class FrontendCompanyVariablesPage extends PlatformPage {
    static i18nNamespace = 'company_variables';

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }
            .info-banner {
                display: flex;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-left: 3px solid var(--info);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    render() {
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                .title=${this.t('page_title')}
                .subtitle=${this.t('page_subtitle')}
            ></page-header>
            <div class="info-banner">${this.t('info_banner')}</div>
            <platform-company-variables-panel></platform-company-variables-panel>
        `;
    }
}

customElements.define('frontend-company-variables-page', FrontendCompanyVariablesPage);

/**
 * Полноэкранная витрина сервисов: крошки + сетка плиток.
 */

import { html, css } from 'lit';
import { PlatformPage } from './PlatformPage.js';
import '../components/platform-breadcrumbs.js';
import '../components/platform-services-launcher.js';

export class PlatformServicesPage extends PlatformPage {
    static i18nNamespace = 'platform';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
            }
            .wrap {
                padding: 0;
            }
            .intro {
                margin-bottom: var(--space-4);
            }
            .title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                margin: 0 0 var(--space-2);
                color: var(--text-primary);
            }
            .subtitle {
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
        `,
    ];

    render() {
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <div class="wrap">
                <div class="intro">
                    <h1 class="title">${this.t('services_page.title')}</h1>
                    <p class="subtitle">${this.t('services_page.subtitle')}</p>
                </div>
                <platform-services-launcher layout="page"></platform-services-launcher>
            </div>
        `;
    }
}

customElements.define('platform-services-page', PlatformServicesPage);

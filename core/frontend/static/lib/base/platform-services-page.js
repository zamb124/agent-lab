/**
 * Полноэкранная витрина сервисов: хедер с бургером (mobile), крошки + сетка плиток.
 */

import { html, css } from 'lit';
import { PlatformPage } from './PlatformPage.js';
import '../components/platform-breadcrumbs.js';
import '../components/layout/page-header.js';
import '../components/platform-services-launcher.js';

export class PlatformServicesPage extends PlatformPage {
    static i18nNamespace = 'platform';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }
            .wrap {
                padding: var(--space-4);
                min-width: 0;
            }
        `,
    ];

    render() {
        return html`
            <page-header
                title=${this.t('services_page.title')}
                subtitle=${this.t('services_page.subtitle')}
            ></page-header>
            <platform-breadcrumbs></platform-breadcrumbs>
            <div class="wrap">
                <platform-services-launcher layout="page"></platform-services-launcher>
            </div>
        `;
    }
}

customElements.define('platform-services-page', PlatformServicesPage);

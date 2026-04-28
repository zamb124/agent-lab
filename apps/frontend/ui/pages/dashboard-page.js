/**
 * Dashboard page — главная страница консоли. Тонкая композиция четырёх
 * атомарных секций: hero, strip метрик, витрина сервисов, быстрые действия.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import {
    replaceLocationToLastVisitedNonFrontendService,
    hasInviteDashboardQuery,
    stripInviteDashboardQuery,
} from '@platform/lib/utils/last-visited-service.js';
import '../components/dashboard/dashboard-hero.js';
import '../components/dashboard/dashboard-stat-strip.js';
import '../components/dashboard/dashboard-services-grid.js';
import '../components/dashboard/dashboard-quick-actions.js';

export class DashboardPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
            }
            section { margin-bottom: var(--space-8); }
            section:last-child { margin-bottom: 0; }
            @media (min-width: 768px) {
                .section--hero { order: 1; }
                .section--stats { order: 2; }
                .section--services { order: 3; }
                .section--quick { order: 4; }
            }
            @media (max-width: 767px) {
                :host { padding: var(--space-3); }
                section { margin-bottom: var(--space-6); }
                .section--services { order: 1; }
                .section--hero { order: 2; }
                .section--stats { order: 3; }
                .section--quick { order: 4; }
            }
        `,
    ];

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && hasInviteDashboardQuery(window.location)) {
            stripInviteDashboardQuery(window.location);
            return;
        }
        replaceLocationToLastVisitedNonFrontendService();
    }

    render() {
        return html`
            <section class="section--hero"><dashboard-hero></dashboard-hero></section>
            <section class="section--stats"><dashboard-stat-strip></dashboard-stat-strip></section>
            <section class="section--services"><dashboard-services-grid></dashboard-services-grid></section>
            <section class="section--quick"><dashboard-quick-actions></dashboard-quick-actions></section>
        `;
    }
}

customElements.define('dashboard-page', DashboardPage);

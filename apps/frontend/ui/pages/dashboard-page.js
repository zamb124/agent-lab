/**
 * Dashboard page — главная страница консоли. Тонкая композиция четырёх
 * атомарных секций: hero, strip метрик, витрина сервисов, быстрые действия.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '../components/dashboard/dashboard-hero.js';
import '../components/dashboard/dashboard-stat-strip.js';
import '../components/dashboard/dashboard-services-grid.js';
import '../components/dashboard/dashboard-quick-actions.js';

export class DashboardPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; padding: var(--space-4); }
            section { margin-bottom: var(--space-8); }
            section:last-child { margin-bottom: 0; }
        `,
    ];

    render() {
        return html`
            <section><dashboard-hero></dashboard-hero></section>
            <section><dashboard-stat-strip></dashboard-stat-strip></section>
            <section><dashboard-services-grid></dashboard-services-grid></section>
            <section><dashboard-quick-actions></dashboard-quick-actions></section>
        `;
    }
}

customElements.define('dashboard-page', DashboardPage);

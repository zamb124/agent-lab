/**
 * LinnexModelsApp — корневой компонент реестра системных моделей Linnex.
 *
 * Полностью event-driven canon: домен описан фабриками в
 * `events/resources/*.resource.js` и регистрируется через `static factories`.
 * Маршрутизация — через core router.effect; SPA сервится по `/litserve`.
 *
 * Маршруты:
 *   /litserve            -> models
 */

import { html, css, type TemplateResult } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { linnexModelsResource, linnexModelRetryOp } from '../events/resources/models.resource.js';
import { buildLitserveAssistantContext } from '../_helpers/platform-assistant-context.js';

import '@platform/lib/components/layout/platform-island.js';
import '../components/litserve-sidebar.js';
import '../pages/litserve-models-page.js';

const LINNEX_MODELS_ROUTES = [
    { key: 'models', path: '', titleKey: 'routes.models' },
    { key: 'platform_services', path: 'services', parent: 'models', titleKey: 'routes.platform_services' },
];

/** Mobile shell: реестр моделей + профиль/переключатель сервисов (как в RAG/Sync). */
const LINNEX_MODELS_BOTTOM_NAV_ITEMS = [
    { key: 'models', routeKey: 'models', icon: 'database', labelKey: 'bottom_nav.models' },
    { key: 'profile', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class LinnexModelsApp extends PlatformApp {
    static defaultI18nNamespace = 'litserve';
    static bottomNavItems = LINNEX_MODELS_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = [];
    static platformAssistant = {
        branchId: 'litserve',
        serviceId: 'litserve',
        showLauncher: true,
    };

    static factories = [
        linnexModelsResource,
        linnexModelRetryOp,
    ];

    static override styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
                background: transparent;
            }
            .main {
                flex: 1;
                min-width: 0;
                height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            @media (max-width: 767px) {
                .main { padding: 0; }
                .sidebar { position: absolute; width: 0; height: 0; overflow: visible; }
            }
        `,
    ];

    override getBaseUrl() { return '/litserve'; }

    override getRoutes() { return []; }

    override getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/litserve', routes: LINNEX_MODELS_ROUTES }),
        ];
    }

    override shouldRenderPlatformAssistant(_routeKey: string | null) {
        return true;
    }

    override async getPlatformAssistantContextVariables(routeKey: string, _params: Record<string, string>) {
        return buildLitserveAssistantContext(routeKey);
    }

    override renderRoute(routeKey: string | null) {
        const _key = routeKey === 'models' || !routeKey ? 'models' : routeKey;
        let content: TemplateResult;
        switch (_key) {
            case 'platform_services':
                content = html`<platform-services-page></platform-services-page>`;
                break;
            case 'models':
                content = html`<linnex-models-page></linnex-models-page>`;
                break;
            default:
                content = html`<linnex-models-page></linnex-models-page>`;
                break;
        }
        const useIslandFullBleed = _key === 'models';
        return html`
            <div class="sidebar"><litserve-sidebar></litserve-sidebar></div>
            <div class="main">
                <platform-island
                    padding=${useIslandFullBleed ? 'none' : 'md'}
                    ?safe-bottom=${useIslandFullBleed}
                >${content}</platform-island>
            </div>
        `;
    }
}

customElements.define('litserve-app', LinnexModelsApp);

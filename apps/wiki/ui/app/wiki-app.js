/**
 * WikiApp — корневой компонент базы знаний (`/wiki`).
 *
 * Раскладка повторяет привычную для документов: слева дерево страниц, справа
 * страница. Ширину дерева пользователь настраивает сам, поэтому она живёт в
 * `platform-resizable-split`, а не в фиксированном токене.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';

import {
    wikiPagesResource,
    wikiPageReadOp,
    wikiPageCreateOp,
    wikiPageSaveOp,
    wikiPagePropertiesOp,
    wikiPageMoveOp,
    wikiPageMoveNamespaceOp,
    wikiPageDeleteOp,
    wikiPageRestoreOp,
    wikiDeletedPagesOp,
    wikiPageMarkdownOp,
    wikiPageMarkdownImportOp,
    wikiPageMarkdownCreateOp,
    wikiMarkdownParseOp,
} from '../events/resources/pages.resource.js';
import {
    wikiAccessReadOp,
    wikiMemberAddOp,
    wikiMemberRemoveOp,
    wikiPublicLinkOp,
    wikiPublicPageOp,
    wikiPublicTreeOp,
    wikiPublicSitePageOp,
    wikiRevisionsOp,
    wikiRevisionReadOp,
    wikiRevisionRestoreOp,
    wikiCommentsOp,
    wikiCommentCreateOp,
    wikiCommentResolveOp,
    wikiSearchOp,
    wikiBacklinksOp,
} from '../events/resources/page-extras.resource.js';
import { wikiNamespacesResource } from '../events/resources/namespaces.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';

import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-command-palette.js';
import '@platform/lib/components/platform-resizable-split.js';
import '../components/wiki-sidebar.js';
import '../components/sheets/wiki-outline-sheet.js';
import '../components/sheets/wiki-tree-sheet.js';
import '../components/sheets/wiki-public-tree-sheet.js';
import '../pages/wiki-home-page.js';
import '../pages/wiki-page-view.js';
import '../pages/wiki-search-page.js';
import '../pages/wiki-history-page.js';
import '../pages/wiki-public-preview-page.js';
import '../modals/wiki-move-page-modal.js';
import '../modals/wiki-page-access-modal.js';
import '../modals/wiki-import-report-modal.js';

const WIKI_ROUTES = [
    { key: 'wiki_home',         path: '',                     titleKey: 'routes.wiki_home' },
    { key: 'wiki_page',         path: 'p/:pageId',            parent: 'wiki_home', titleKey: 'routes.wiki_page' },
    { key: 'wiki_page_history', path: 'p/:pageId/history',    parent: 'wiki_page', titleKey: 'routes.wiki_page_history' },
    { key: 'wiki_search',       path: 'search',               parent: 'wiki_home', titleKey: 'routes.wiki_search' },
    { key: 'wiki_public_preview', path: 's/:token',           titleKey: 'routes.wiki_public_preview' },
    { key: 'wiki_public_page',  path: 's/:token/p/:pageId',   parent: 'wiki_public_preview', titleKey: 'routes.wiki_public_page' },
];

const WIKI_BOTTOM_NAV_ITEMS = [
    { key: 'home',    routeKey: 'wiki_home',   icon: 'book-open', labelKey: 'bottom_nav.home' },
    { key: 'search',  routeKey: 'wiki_search', icon: 'search',    labelKey: 'bottom_nav.search' },
    { key: 'tree',    sheet: 'wiki.tree',      icon: 'trace-tree', labelKey: 'bottom_nav.tree' },
    { key: 'profile', sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

/** На публичном сайте нет ни сайдбара приложения, ни нижней навигации. */
const PUBLIC_ROUTE_KEY = 'wiki_public_preview';
const PUBLIC_PAGE_ROUTE_KEY = 'wiki_public_page';
const PUBLIC_ROUTE_KEYS = [PUBLIC_ROUTE_KEY, PUBLIC_PAGE_ROUTE_KEY];

export class WikiApp extends PlatformApp {
    static defaultI18nNamespace = 'wiki';
    static topBarEnabled = true;
    static bottomNavItems = WIKI_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = PUBLIC_ROUTE_KEYS;
    static platformAssistant = {
        branchId: 'wiki',
        serviceId: 'wiki',
        showLauncher: true,
    };

    static factories = [
        wikiNamespacesResource,
        wikiPagesResource,
        wikiPageReadOp,
        wikiPageCreateOp,
        wikiPageSaveOp,
        wikiPagePropertiesOp,
        wikiPageMoveOp,
        wikiPageMoveNamespaceOp,
        wikiPageDeleteOp,
        wikiPageRestoreOp,
        wikiDeletedPagesOp,
        wikiPageMarkdownOp,
        wikiPageMarkdownImportOp,
        wikiPageMarkdownCreateOp,
        wikiMarkdownParseOp,
        wikiAccessReadOp,
        wikiMemberAddOp,
        wikiMemberRemoveOp,
        wikiPublicLinkOp,
        wikiPublicPageOp,
        wikiPublicTreeOp,
        wikiPublicSitePageOp,
        wikiRevisionsOp,
        wikiRevisionReadOp,
        wikiRevisionRestoreOp,
        wikiCommentsOp,
        wikiCommentCreateOp,
        wikiCommentResolveOp,
        wikiSearchOp,
        wikiBacklinksOp,
        platformFileCreateOp,
    ];

    static properties = {
        _treeCollapsed: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: block;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }

            platform-resizable-split {
                width: 100%;
                height: var(--app-vh, 100vh);
            }

            .sidebar {
                height: 100%;
            }

            .main {
                height: 100%;
                min-width: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                padding: var(--space-4);
                padding-left: 0;
                box-sizing: border-box;
            }

            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }

            /* Прокрутку внутри сайта держит колонка чтения, чтобы навигация и
               путь оставались на месте. */
            .public {
                height: var(--app-vh, 100vh);
                overflow: hidden;
            }

            /* На мобиле дерево уезжает в bottom-sheet: две колонки на узком
               экране не помещаются, а нижняя навигация уже даёт вход в дерево. */
            @media (max-width: 767px) {
                platform-resizable-split {
                    display: block;
                }
                .sidebar {
                    display: none;
                }
                .main {
                    padding: 0;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._search = this.useOp('wiki/search');
        this._pages = this.useResource('wiki/pages');
        this._treeCollapsed = readShellSidebarCollapsed();
        this._onPaletteSelect = this._onPaletteSelect.bind(this);
        this._paletteProvider = this._paletteProvider.bind(this);
        this._onSidebarCollapseChange = this._onSidebarCollapseChange.bind(this);
    }

    getBaseUrl() { return '/wiki'; }

    getRoutes() { return []; }

    getServiceEffects() {
        return [createRouterEffect({ baseUrl: '/wiki', routes: WIKI_ROUTES })];
    }

    shouldRenderPlatformAssistant(routeKey) {
        return !PUBLIC_ROUTE_KEYS.includes(routeKey);
    }

    getPlatformAssistantContextVariables(routeKey, params) {
        return {
            wiki_route: routeKey,
            wiki_page_id: typeof params.pageId === 'string' ? params.pageId : '',
        };
    }

    /** Быстрый переход по Cmd+K: страницы дерева плюс переход к поиску. */
    async _paletteProvider(query) {
        const trimmed = query.trim();
        if (trimmed === '') {
            return this._pages.items.slice(0, 12).map((page) => ({
                id: page.wiki_page_id,
                label: page.title,
                icon: 'file',
                group: this.t('palette.recent'),
            }));
        }
        const result = await this._search.run({ query: trimmed, mode: 'auto', limit: 12 });
        const items = Array.isArray(result.items) ? result.items : [];
        return items.map((item) => ({
            id: item.wiki_page_id,
            label: item.title,
            description: item.snippet,
            icon: 'file',
            group: this.t('palette.pages'),
        }));
    }

    _onPaletteSelect(event) {
        this.navigate('wiki_page', { pageId: event.detail.id });
    }

    /** Свёрнутое дерево отдаёт свою ширину странице: split сжимается до полосы с логотипом. */
    _onSidebarCollapseChange(event) {
        const collapsed = event.detail.collapsed;
        if (typeof collapsed !== 'boolean') {
            throw new Error('wiki-app: collapse-change ожидает detail.collapsed boolean');
        }
        this._treeCollapsed = collapsed;
    }

    renderRoute(routeKey, params) {
        if (PUBLIC_ROUTE_KEYS.includes(routeKey)) {
            const publicPageId = typeof params.pageId === 'string' ? params.pageId : '';
            return html`
                <div class="public">
                    <wiki-public-preview-page
                        token=${params.token}
                        page-id=${publicPageId}
                    ></wiki-public-preview-page>
                    <wiki-public-tree-sheet></wiki-public-tree-sheet>
                </div>
            `;
        }

        const pageId = typeof params.pageId === 'string' ? params.pageId : '';
        return html`
            <platform-resizable-split
                storage-key="tree"
                storage-scope="wiki"
                min-size="200"
                max-size="480"
                ?collapsed=${this._treeCollapsed}
            >
                <div class="sidebar" slot="side">
                    <wiki-sidebar
                        active-page-id=${pageId}
                        @collapse-change=${this._onSidebarCollapseChange}
                    ></wiki-sidebar>
                </div>
                <div class="main">
                    <platform-island padding="none" ?content-no-scroll=${true}>
                        ${this._renderPage(routeKey, params)}
                    </platform-island>
                </div>
            </platform-resizable-split>
            <platform-command-palette
                .provider=${this._paletteProvider}
                @palette-select=${this._onPaletteSelect}
            ></platform-command-palette>
            <wiki-tree-sheet active-page-id=${pageId}></wiki-tree-sheet>
        `;
    }

    _renderPage(routeKey, params) {
        switch (routeKey) {
            case 'wiki_page':
                return html`<wiki-page-view page-id=${params.pageId}></wiki-page-view>`;
            case 'wiki_page_history':
                return html`<wiki-history-page page-id=${params.pageId}></wiki-history-page>`;
            case 'wiki_search':
                return html`<wiki-search-page></wiki-search-page>`;
            case 'wiki_home':
            default:
                return html`<wiki-home-page></wiki-home-page>`;
        }
    }
}

customElements.define('wiki-app', WikiApp);

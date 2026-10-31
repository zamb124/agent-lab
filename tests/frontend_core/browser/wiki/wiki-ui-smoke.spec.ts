/**
 * Wiki UI — регистрация компонентов и базовые контракты фабрик.
 */

import { expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/index.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

import { WikiApp } from '../../../../apps/wiki/ui/app/wiki-app.js';
import { WIKI_PANEL_TABS } from '../../../../apps/wiki/ui/components/wiki-page-panel.js';
import '../../../../apps/wiki/ui/components/wiki-sidebar.js';
import '../../../../apps/wiki/ui/pages/wiki-home-page.js';
import '../../../../apps/wiki/ui/pages/wiki-page-view.js';
import '../../../../apps/wiki/ui/pages/wiki-search-page.js';
import '../../../../apps/wiki/ui/pages/wiki-history-page.js';
import '../../../../apps/wiki/ui/pages/wiki-public-preview-page.js';
import '../../../../apps/wiki/ui/components/sheets/wiki-outline-sheet.js';
import '../../../../apps/wiki/ui/components/sheets/wiki-tree-sheet.js';
import '../../../../apps/wiki/ui/modals/wiki-move-page-modal.js';
import '../../../../apps/wiki/ui/modals/wiki-page-access-modal.js';
import '../../../../apps/wiki/ui/modals/wiki-import-report-modal.js';
import { buildLineDiff } from '../../../../apps/wiki/ui/pages/wiki-history-page.js';
import type { TestEl } from '../helpers/dom.js';

describe('wiki ui', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('регистрирует все элементы сервиса', () => {
        const tags = [
            'wiki-app',
            'wiki-sidebar',
            'wiki-home-page',
            'wiki-page-view',
            'wiki-search-page',
            'wiki-history-page',
            'wiki-public-preview-page',
            'wiki-move-page-modal',
            'wiki-page-access-modal',
            'wiki-import-report-modal',
            'wiki-outline-sheet',
            'wiki-tree-sheet',
            'wiki-page-panel',
        ];
        for (const tag of tags) {
            expect(customElements.get(tag), tag).to.exist;
        }
    });

    it('объявляет i18n namespace и ассистента сервиса', () => {
        expect(WikiApp.defaultI18nNamespace).to.equal('wiki');
        expect(WikiApp.platformAssistant.serviceId).to.equal('wiki');
        expect(WikiApp.platformAssistant.branchId).to.equal('wiki');
    });

    it('нижняя навигация ссылается на существующие маршруты и иконки', () => {
        const routeKeys = new Set(['wiki_home', 'wiki_page', 'wiki_page_history', 'wiki_search', 'wiki_public_preview']);
        for (const item of WikiApp.bottomNavItems) {
            if (typeof item.routeKey === 'string') {
                expect(routeKeys.has(item.routeKey), item.routeKey).to.be.true;
            }
            expect(typeof item.labelKey).to.equal('string');
            expect(typeof item.icon).to.equal('string');
            expect(item.icon).to.not.equal('list-tree');
            expect(item.icon).to.not.equal('more-horizontal');
        }
    });

    it('все фабрики сервиса собираются без конфликтов имён', () => {
        const collected = collectFactories(WikiApp.factories);
        expect(Object.keys(collected.slices).length).to.be.greaterThan(0);
    });

    it('каждая фабрика имеет уникальное имя', () => {
        const names = WikiApp.factories.map((factory) => factory.name);
        expect(new Set(names).size).to.equal(names.length);
    });

    it('операции markdown зарегистрированы приложением', () => {
        const names = WikiApp.factories.map((factory) => factory.name);
        expect(names).to.include.members([
            'wiki/page_markdown',
            'wiki/page_markdown_import',
            'wiki/page_markdown_create',
            'wiki/markdown_parse',
        ]);
    });

    it('browse Documents для picker — owner office/*', () => {
        const names = WikiApp.factories.map((factory) => factory.name);
        expect(names).to.include.members([
            'office/catalogs_list',
            'office/documents_list',
            'office/documents_search',
        ]);
    });

    it('операции доступа зарегистрированы приложением', () => {
        const names = WikiApp.factories.map((factory) => factory.name);
        expect(names).to.include.members([
            'wiki/access_read',
            'wiki/company_visible',
            'wiki/member_add',
            'wiki/member_remove',
            'wiki/public_link',
        ]);
    });

    it('модалка доступа создаётся при зарегистрированных фабриках', () => {
        resetPlatformState();
        bootstrapTestBus({ factories: WikiApp.factories });
        const modal = (document.createElement('wiki-page-access-modal') as TestEl);
        expect(customElements.get('wiki-page-access-modal')).to.exist;
        expect(modal.useOp).to.be.a('function');
        expect(modal._companyVisible).to.exist;
        expect(modal._access).to.exist;
    });
});

describe('wiki sidebar recent collapse', () => {
    const STORAGE_KEY = platformStorageKey('wiki', 'sidebar.recent');

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: WikiApp.factories });
        window.localStorage.removeItem(STORAGE_KEY);
    });

    afterEach(() => {
        window.localStorage.removeItem(STORAGE_KEY);
    });

    function createSidebar() {
        return (document.createElement('wiki-sidebar') as TestEl);
    }

    it('без сохранённого состояния Recent развёрнут', () => {
        const sidebar = createSidebar();
        expect(sidebar._recentCollapsed).to.equal(false);
    });

    it('сохранённое свёрнутое состояние восстанавливается', () => {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ collapsed: true }));
        const sidebar = createSidebar();
        expect(sidebar._recentCollapsed).to.equal(true);
    });

    it('битое состояние Recent — ошибка, а не тихий дефолт', () => {
        const sidebar = createSidebar();
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ collapsed: 'yes' }));
        expect(() => sidebar._readRecentCollapsed()).to.throw(/recent/);
    });

    it('переключение пишет состояние в storage', () => {
        const sidebar = createSidebar();
        sidebar._toggleRecent();
        expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).to.deep.equal({
            collapsed: true,
        });
        sidebar._toggleRecent();
        expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).to.deep.equal({
            collapsed: false,
        });
    });
});

describe('wiki page panel state', () => {
    const STORAGE_KEY = platformStorageKey('wiki', 'page.panel');

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: WikiApp.factories });
        window.localStorage.removeItem(STORAGE_KEY);
    });

    afterEach(() => {
        window.localStorage.removeItem(STORAGE_KEY);
    });

    function createPageView() {
        return (document.createElement('wiki-page-view') as TestEl);
    }

    it('без сохранённого состояния панель закрыта на оглавлении', () => {
        const view = createPageView();

        expect(view._panelOpen).to.equal(false);
        expect(view._panelTab).to.equal('outline');
    });

    it('сохранённое состояние восстанавливается при монтировании', () => {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ open: true, tab: 'history' }));

        const view = createPageView();

        expect(view._panelOpen).to.equal(true);
        expect(view._panelTab).to.equal('history');
    });

    it('битое состояние панели — ошибка, а не тихий дефолт', () => {
        const view = createPageView();
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ open: true, tab: 'unknown' }));

        expect(() => view._restorePanelState()).to.throw(/панели/);
    });

    it('переключение вкладок пишет состояние в storage', () => {
        const view = createPageView();

        view._panelTab = 'comments';
        view._panelOpen = true;
        view._persistPanelState();

        expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).to.deep.equal({
            open: true,
            tab: 'comments',
        });
    });

    it('вкладки панели объявлены единым списком без дублей', () => {
        expect(WIKI_PANEL_TABS).to.deep.equal(['outline', 'backlinks', 'comments', 'history']);
        expect(new Set(WIKI_PANEL_TABS).size).to.equal(WIKI_PANEL_TABS.length);
    });

    it('wiki-page-view открывает обложку через file picker helper', () => {
        const view = createPageView();
        expect(typeof view._openCoverPicker).to.equal('function');
        expect(typeof view._openFilePicker).to.equal('function');
        expect(typeof view._wikiFileCreateSpec).to.equal('function');
        expect(view._openCoverPicker.toString()).to.include('_openFilePicker');
        expect(view._openCoverPicker.toString()).to.not.include('prompt');
    });
});

describe('buildLineDiff', () => {
    it('одинаковый текст не даёт изменений', () => {
        const rows = buildLineDiff('первая\nвторая', 'первая\nвторая');
        expect(rows.every((row) => row.kind === 'same')).to.be.true;
    });

    it('отмечает добавленные строки', () => {
        const rows = buildLineDiff('первая', 'первая\nвторая');
        const added = rows.filter((row) => row.kind === 'added');
        expect(added.map((row) => row.text)).to.deep.equal(['вторая']);
    });

    it('отмечает удалённые строки', () => {
        const rows = buildLineDiff('первая\nвторая', 'первая');
        const removed = rows.filter((row) => row.kind === 'removed');
        expect(removed.map((row) => row.text)).to.deep.equal(['вторая']);
    });

    it('замена строки видна как удаление и добавление', () => {
        const rows = buildLineDiff('было', 'стало');
        expect(rows.map((row) => row.kind)).to.deep.equal(['removed', 'added']);
    });
});

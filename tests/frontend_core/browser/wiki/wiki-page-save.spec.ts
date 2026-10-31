/**
 * Wiki page — загрузка и сохранение через WS-команды.
 *
 * Регрессия на проде: `run()` резолвит `WikiPageResponse { page, can_edit,
 * can_admin }`, а не саму `WikiPage`. Компонент присваивал обёртку в `_page`,
 * и `content_update_requested` уходил на сервер без `content`
 * (`ws_invalid_payload`). Здесь ответы транспорта — каноническая проводная
 * форма: внутренняя страница живёт в `result.page`.
 */

import { expect, fixture, html, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { platformWs, WsTransportError } from '@platform/lib/events/effects/ws.effect.js';

import { WikiApp } from '../../../../apps/wiki/ui/app/wiki-app.js';
import {
    wikiPageReadOp,
    wikiPageSaveOp,
    wikiPageCreateOp,
} from '../../../../apps/wiki/ui/events/resources/pages.resource.js';
import { WikiPageView } from '../../../../apps/wiki/ui/pages/wiki-page-view.js';
import '../../../../apps/wiki/ui/pages/wiki-home-page.js';
import '../../../../apps/wiki/ui/components/wiki-sidebar.js';

const PAGE_CONTENT = {
    type: 'doc',
    content: [{ type: 'paragraph', content: [{ type: 'text', text: 'текст' }] }],
};

function buildPage(id, overrides = {}) {
    return {
        wiki_page_id: id,
        company_id: 'cmp_1',
        namespace: 'default',
        title: 'Заголовок',
        content: PAGE_CONTENT,
        icon: '',
        cover_url: '',
        is_published: true,
        is_full_width: false,
        is_template: false,
        parent_page_id: null,
        root_page_id: id,
        depth: 0,
        position: 0,
        created_by_user_id: 'usr_1',
        last_edited_by_user_id: 'usr_1',
        created_at: '2026-10-08T00:00:00Z',
        updated_at: '2026-10-08T00:00:00Z',
        text_markdown: 'текст',
        company_visible: true,
        link_enabled: false,
        link_permission: 'viewer',
        revision_count: 0,
        deleted_at: null,
        published_at: null,
        ...overrides,
    };
}

const PAGE = buildPage('wpg_1');
const PAGE_RESPONSE = { page: PAGE, can_edit: true, can_admin: true };
const EMPTY_LIST = { items: [], total: 0, limit: 100, offset: 0 };

// WS-стаб: один оригинал, вызовы пишутся в wsCalls, ответы берутся из wsHandlers.
const realRequest = platformWs.request;
let wsCalls = [];
let wsHandlers = {};

function installWs() {
    wsCalls = [];
    wsHandlers = {};
    platformWs.request = (opts) => {
        wsCalls.push({ type: opts.type, payload: opts.payload });
        const handler = wsHandlers[opts.type];
        if (handler !== undefined) {
            return typeof handler === 'function' ? handler(opts.payload) : Promise.resolve(handler);
        }
        if (opts.type === 'wiki/pages/list_requested') return Promise.resolve(EMPTY_LIST);
        if (opts.type === 'wiki/pages/item_requested') return Promise.resolve(PAGE_RESPONSE);
        return Promise.reject(new WsTransportError(`unexpected command ${opts.type}`, 'ws_stub'));
    };
}

function uninstallWs() {
    platformWs.request = realRequest;
}

// Поллинг готовности редактора — не предмет spec'а: подмена на прототипе
// детерминирована относительно _loadPage, который стартует из updated().
const realRefreshOutline = WikiPageView.prototype._refreshOutlineWhenEditorReady;
function stubOutlineRefresh() {
    WikiPageView.prototype._refreshOutlineWhenEditorReady = async () => {};
}
function restoreOutlineRefresh() {
    WikiPageView.prototype._refreshOutlineWhenEditorReady = realRefreshOutline;
}

/**
 * Смонтировать страницу и дождаться загрузки: `updateComplete` у Lit резолвится
 * только для подключённого элемента.
 */
async function mountPageView(pageId = 'wpg_1') {
    const view = await fixture(html`<wiki-page-view page-id=${pageId}></wiki-page-view>`);
    await waitUntil(() => view._page !== null);
    return view;
}

describe('wiki page save — WS транспорт и форма ответа', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: WikiApp.factories });
        installWs();
        stubOutlineRefresh();
    });

    afterEach(() => {
        restoreOutlineRefresh();
        uninstallWs();
    });

    it('операции страницы объявлены как ws-команды', () => {
        for (const op of [wikiPageReadOp, wikiPageSaveOp, wikiPageCreateOp]) {
            expect(op.transport).to.equal('ws', op.name);
        }
        expect(wikiPageReadOp.commandType).to.equal('wiki/pages/item_requested');
        expect(wikiPageSaveOp.commandType).to.equal('wiki/pages/content_update_requested');
        expect(wikiPageCreateOp.commandType).to.equal('wiki/pages/create_requested');
    });

    it('_loadPage разворачивает WikiPageResponse — _page это внутренняя страница', async () => {
        const view = await mountPageView();

        expect(view._page).to.equal(PAGE);
        expect(view._page.content).to.deep.equal(PAGE_CONTENT);
        expect(view._page.page).to.equal(undefined);
    });

    it('сохранение шлёт content страницы — правка заголовка не теряет документ', async () => {
        const saved = buildPage('wpg_1', { title: 'Новый заголовок' });
        wsHandlers['wiki/pages/content_update_requested'] = {
            page: saved,
            can_edit: true,
            can_admin: true,
        };
        const view = await mountPageView();

        view._pendingTitle = 'Новый заголовок';
        await view._commitSave();

        const saveCall = wsCalls.find((c) => c.type === 'wiki/pages/content_update_requested');
        expect(saveCall, 'content_update_requested').to.exist;
        expect(saveCall.payload.wiki_page_id).to.equal('wpg_1');
        expect(saveCall.payload.content).to.deep.equal(PAGE_CONTENT);
        expect(saveCall.payload.title).to.equal('Новый заголовок');
        expect(saveCall.payload.create_revision).to.equal(true);
        expect(view._page.title).to.equal('Новый заголовок');
        expect(view._saveState).to.equal('done');
    });

    it('неудачное сохранение оставляет правки в pending и помечает failed', async () => {
        wsHandlers['wiki/pages/content_update_requested'] = () =>
            Promise.reject(new WsTransportError('сокет оборвался', 'ws_disconnected'));
        const view = await mountPageView();

        view._pendingTitle = 'Неотправленное';
        await view._commitSave();

        expect(view._saveState).to.equal('failed');
        expect(view._pendingTitle).to.equal('Неотправленное');
        expect(view._page.title).to.equal('Заголовок');
    });

    it('правки за время полёта сохранения не затираются ответом', async () => {
        let releaseSave;
        wsHandlers['wiki/pages/content_update_requested'] = () =>
            new Promise((resolve) => {
                releaseSave = resolve;
            });
        const view = await mountPageView();

        view._pendingTitle = 'Первый';
        const saving = view._commitSave();
        // Юзер продолжил печатать, пока команда в полёте.
        view._pendingTitle = 'Второй';
        await waitUntil(() => releaseSave !== undefined);
        releaseSave({ page: buildPage('wpg_1', { title: 'Первый' }), can_edit: true, can_admin: true });
        await saving;

        expect(view._pendingTitle).to.equal('Второй');
        expect(view._page.title).to.equal('Второй');
        expect(view._saveState).to.not.equal('done');
    });

    it('смена pageId досылает правки прежней страницы с её id', async () => {
        const view = await mountPageView();

        view._pendingTitle = 'Черновик первой страницы';
        view._scheduleSave();
        expect(view._saveTimer).to.not.equal(null);

        view.pageId = 'wpg_2';
        await aTimeout(0);

        const saveCall = wsCalls.find((c) => c.type === 'wiki/pages/content_update_requested');
        expect(saveCall, 'досохранение старой страницы').to.exist;
        expect(saveCall.payload.wiki_page_id).to.equal('wpg_1');
        expect(saveCall.payload.title).to.equal('Черновик первой страницы');
        expect(saveCall.payload.content).to.deep.equal(PAGE_CONTENT);
        const loadSecond = wsCalls.filter(
            (c) => c.type === 'wiki/pages/item_requested' && c.payload.wiki_page_id === 'wpg_2',
        );
        expect(loadSecond.length).to.equal(1);
    });

    it('поздний ответ досохранения не трогает экран новой страницы', async () => {
        let releaseSave;
        wsHandlers['wiki/pages/content_update_requested'] = () =>
            new Promise((resolve) => {
                releaseSave = resolve;
            });
        const view = await mountPageView();
        const saving = view._commitSave('wpg_1');

        view.pageId = 'wpg_2';
        await view._loadPage();
        releaseSave({ page: buildPage('wpg_1', { title: 'Старое' }), can_edit: true, can_admin: true });
        await saving;

        expect(view.pageId).to.equal('wpg_2');
        expect(view._page).to.equal(PAGE);
        expect(view._saveState).to.equal('idle');
    });
});

describe('wiki create — навигация по развёрнутому ответу', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: WikiApp.factories });
        installWs();
        wsHandlers['wiki/pages/create_requested'] = {
            page: buildPage('wpg_new'),
            can_edit: true,
            can_admin: true,
        };
    });

    afterEach(() => {
        uninstallWs();
    });

    it('wiki-home-page переходит на созданную страницу по её id', async () => {
        const home = document.createElement('wiki-home-page');
        let navigated = null;
        home.navigate = (routeKey, params) => {
            navigated = { routeKey, params };
        };
        await home._createRootPage();

        expect(navigated).to.not.equal(null);
        expect(navigated.routeKey).to.equal('wiki_page');
        expect(navigated.params.pageId).to.equal('wpg_new');
    });

    it('wiki-sidebar переходит на созданную корневую страницу по её id', async () => {
        const sidebar = document.createElement('wiki-sidebar');
        let navigated = null;
        sidebar.navigate = (routeKey, params) => {
            navigated = { routeKey, params };
        };
        await sidebar._createRootPage();

        expect(navigated).to.not.equal(null);
        expect(navigated.params.pageId).to.equal('wpg_new');
    });

    it('wiki-sidebar переходит на созданную дочернюю страницу по её id', async () => {
        const sidebar = document.createElement('wiki-sidebar');
        let navigated = null;
        sidebar.navigate = (routeKey, params) => {
            navigated = { routeKey, params };
        };
        await sidebar._createChildPage('wpg_parent');

        const createCall = wsCalls.find((c) => c.type === 'wiki/pages/create_requested');
        expect(createCall.payload.parent_page_id).to.equal('wpg_parent');
        expect(navigated.params.pageId).to.equal('wpg_new');
    });
});

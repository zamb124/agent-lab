/**
 * platform-breadcrumbs: цепочка маршрутов, путь внутри маршрута через trail,
 * навигация по крошке.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-breadcrumbs.js';

const ROUTES = [
    { key: 'wiki_home', path: '' },
    { key: 'wiki_page', path: 'p/:pageId', parent: 'wiki_home' },
];

function seedRouter(routeKey, params) {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTES_REGISTERED, { routes: ROUTES });
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey, params });
}

function labels(el) {
    return [...el.shadowRoot.querySelectorAll('.breadcrumb-item')].map((node) =>
        node.textContent.trim(),
    );
}

describe('platform-breadcrumbs', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('без trail показывает цепочку маршрутов', async () => {
        seedRouter('wiki_page', { pageId: 'p1' });

        const el = await fixture(html`<platform-breadcrumbs></platform-breadcrumbs>`);
        await elementUpdated(el);

        expect(labels(el)).to.deep.equal(['routes.wiki_home', 'routes.wiki_page']);
    });

    it('trail встаёт между маршрутами и подписью текущей страницы', async () => {
        seedRouter('wiki_page', { pageId: 'child' });

        const el = await fixture(html`<platform-breadcrumbs></platform-breadcrumbs>`);
        el.trail = [
            { label: 'Раздел', routeKey: 'wiki_page', params: { pageId: 'root' } },
            { label: 'Подраздел', routeKey: 'wiki_page', params: { pageId: 'mid' } },
        ];
        el.currentLabel = 'Текущая';
        await elementUpdated(el);

        expect(labels(el)).to.deep.equal([
            'routes.wiki_home',
            'Раздел',
            'Подраздел',
            'Текущая',
        ]);
    });

    it('последняя крошка не кликабельна', async () => {
        seedRouter('wiki_page', { pageId: 'child' });

        const el = await fixture(html`<platform-breadcrumbs></platform-breadcrumbs>`);
        el.trail = [{ label: 'Раздел', routeKey: 'wiki_page', params: { pageId: 'root' } }];
        el.currentLabel = 'Текущая';
        await elementUpdated(el);

        const buttons = el.shadowRoot.querySelectorAll('button.breadcrumb-item');
        expect(buttons.length).to.equal(2);
        expect(el.shadowRoot.querySelector('.breadcrumb-current').textContent.trim()).to.equal(
            'Текущая',
        );
    });

    it('клик по крошке trail ведёт на её страницу', async () => {
        seedRouter('wiki_page', { pageId: 'child' });
        const el = await fixture(html`<platform-breadcrumbs></platform-breadcrumbs>`);
        el.trail = [{ label: 'Раздел', routeKey: 'wiki_page', params: { pageId: 'root' } }];
        el.currentLabel = 'Текущая';
        await elementUpdated(el);
        const events = [];
        getPlatformBus().subscribeAny((event) => events.push(event));

        el.shadowRoot.querySelectorAll('button.breadcrumb-item')[1].click();

        const navigate = events.find((event) => event.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        expect(navigate).to.exist;
        expect(navigate.payload).to.deep.equal({
            routeKey: 'wiki_page',
            params: { pageId: 'root' },
        });
    });

    it('крошки для корневого маршрута без хвоста не рисуются', async () => {
        seedRouter('wiki_home', {});

        const el = await fixture(html`<platform-breadcrumbs></platform-breadcrumbs>`);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.breadcrumbs')).to.equal(null);
    });

    it('элемент trail без routeKey — ошибка, а не молчаливый пропуск', () => {
        seedRouter('wiki_page', { pageId: 'child' });
        // Элемент не подключаем: render не должен успеть бросить в микротаске,
        // проверяем валидацию напрямую.
        const el = document.createElement('platform-breadcrumbs');

        el.trail = [{ label: 'Раздел', params: {} }];

        expect(() => el._trailSegments()).to.throw(/routeKey/);
    });
});

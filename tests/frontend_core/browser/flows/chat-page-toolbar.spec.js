/**
 * flows-chat-page mounts production `<platform-flow-ui>` for SPA profile
 * and builds breadcrumbs from flow/branch names (not routes.flow_chat="Flow").
 */
import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { flowsResource } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/pages/flows-chat-page.js';

const FLOWS_CHAT_ROUTES = [
    { key: 'list', path: '', titleKey: 'routes.list' },
    { key: 'flow_chat', path: ':flowId', parent: 'list', titleKey: 'routes.flow_chat' },
    { key: 'flow_chat_branch', path: ':flowId/branch/:branchId', parent: 'list', titleKey: 'routes.flow_chat_branch' },
];

function seedRouter(routeKey, params) {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTES_REGISTERED, { routes: FLOWS_CHAT_ROUTES });
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey, params, pathname: '/', search: '' });
}

function seedFlow(bus, flow) {
    bus.dispatch('flows/flows/list_loaded', { items: [flow] });
}

function crumbLabels(chatPage) {
    const crumbs = chatPage.shadowRoot.querySelector('platform-breadcrumbs');
    return [...crumbs.shadowRoot.querySelectorAll('.breadcrumb-item')].map((node) =>
        node.textContent.trim(),
    );
}

describe('flows-chat-page Flow UI mount', () => {
    beforeEach(async () => {
        await resetPlatformState();
        bootstrapTestBus({ factories: [flowsResource] });
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('mounts platform-flow-ui display=page profile=spa', async () => {
        const el = await fixture(html`
            <flows-chat-page flow-id="demo-flow" branch-id="base"></flows-chat-page>
        `);
        await elementUpdated(el);
        const surface = el.shadowRoot.querySelector('platform-flow-ui');
        expect(surface).to.not.equal(null);
        expect(surface.getAttribute('display')).to.equal('page');
        expect(surface.getAttribute('profile')).to.equal('spa');
        expect(surface.getAttribute('flow-id')).to.equal('demo-flow');
    });

    it('breadcrumbs use flow name and branch name, not generic Flow/Flow', async () => {
        const bus = getPlatformBus();
        seedRouter('flow_chat_branch', { flowId: 'example_graph', branchId: 'orders_only' });
        seedFlow(bus, {
            flow_id: 'example_graph',
            name: 'Пример графового агента',
            branches: {
                orders_only: { name: 'Только заказы', description: 'orders' },
            },
        });

        const el = await fixture(html`
            <flows-chat-page
                flow-id="example_graph"
                branch-id="orders_only"
            ></flows-chat-page>
        `);
        await elementUpdated(el);
        await elementUpdated(el.shadowRoot.querySelector('platform-breadcrumbs'));

        expect(crumbLabels(el)).to.deep.equal([
            'routes.list',
            'Пример графового агента',
            'Только заказы',
        ]);
    });
});

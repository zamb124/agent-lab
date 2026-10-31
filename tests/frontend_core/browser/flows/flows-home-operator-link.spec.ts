import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import { flowsResource, flowStoreBundlesOp } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import { sessionsResource } from '../../../../apps/flows/ui/events/resources/sessions.resource.js';
import { resourcesBundleResource } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { mcpServersResource } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import { toolsResource, toolsAllOp } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import { integrationsListOp } from '../../../../apps/flows/ui/events/resources/integrations.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { workItemCountsOp } from '@platform/lib/events/resources/work-items.resource.js';
import { agentSkillsResource } from '../../../../apps/flows/ui/events/resources/agent-skills.resource.js';
import '../../../../apps/flows/ui/pages/flows-home-page.js';

const FACTORIES = [
    flowsResource,
    flowStoreBundlesOp,
    sessionsResource,
    resourcesBundleResource,
    mcpServersResource,
    toolsResource,
    toolsAllOp,
    integrationsListOp,
    secretsVariablesResource,
    workItemCountsOp,
    agentSkillsResource,
];

function bootstrapHomeBus() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    return bootstrapTestBus({ slices: collected.slices, effects: collected.effects });
}

const EMPTY_PAGE = { items: [], total: 0, limit: 200, offset: 0 };

const HOME_WS_LISTS = new Set([
    'flows/flows/list_requested',
    'flows/sessions/list_requested',
    'flows/resources/list_requested',
    'flows/mcp_servers/list_requested',
    'flows/agent_skills/list_requested',
    'flows/tools/list_requested',
    'flows/flows/store_bundles_requested',
    'flows/integrations/credentials_list_requested',
    'secrets/variables/list_requested',
]);

describe('flows-home-page HITL / operator link to worktracker', () => {
    let originalFetch;
    let originalWsRequest;

    beforeEach(() => {
        resetPlatformState();
        originalFetch = window.fetch;
        originalWsRequest = platformWs.request;
        window.fetch = async () => new Response(
            JSON.stringify(EMPTY_PAGE),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
        platformWs.request = async (opts) => {
            if (!opts || typeof opts.type !== 'string') {
                throw new Error('home ws stub: opts.type required');
            }
            if (opts.type === 'worktracker/work_items/mine_summary_requested') {
                return { assigned_open_count: 3, queue_inbox_count: 4 };
            }
            if (HOME_WS_LISTS.has(opts.type)) {
                return EMPTY_PAGE;
            }
            throw new Error(`unexpected ws: ${opts.type}`);
        };
    });

    afterEach(() => {
        window.fetch = originalFetch;
        platformWs.request = originalWsRequest;
        fixtureCleanup();
    });

    it('quick action "operator" ведёт в worktracker inbox', async () => {
        bootstrapHomeBus();
        const el = await fixture(html`<flows-home-page></flows-home-page>`);
        await elementUpdated(el);

        expect(el._worktrackerInboxHref()).to.include('/worktracker');

        let openedHref = null;
        el._openOperatorInbox = () => {
            openedHref = el._worktrackerInboxHref();
        };

        el._openQuickAction('operator');
        expect(openedHref).to.include('/worktracker');
    });

    it('activity row показывает суммарный счётчик открытых задач из summary', async () => {
        bootstrapHomeBus();
        const el = await fixture(html`<flows-home-page></flows-home-page>`);
        await waitUntil(
            () => el._workItemCounts.state.total_open_count === 7,
            'work_item_counts summary should resolve to total 7',
        );
        await elementUpdated(el);

        const rows = el.shadowRoot.querySelectorAll('.readiness-row-link');
        expect(rows.length).to.equal(1);
        expect(rows[0].querySelector('.metric-value').textContent.trim()).to.equal('7');
    });
});

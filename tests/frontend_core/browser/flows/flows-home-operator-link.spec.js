import { fixture, fixtureCleanup, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { flowsResource, flowStoreBundlesOp } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import { sessionsResource } from '../../../../apps/flows/ui/events/resources/sessions.resource.js';
import { resourcesBundleResource } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { mcpServersResource } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import { toolsAllOp } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import { integrationsListOp } from '../../../../apps/flows/ui/events/resources/integrations.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { platformWorkItemCountsOp } from '@platform/lib/events/resources/platform-work-item.resource.js';
import { agentSkillsResource } from '../../../../apps/flows/ui/events/resources/agent-skills.resource.js';
import '../../../../apps/flows/ui/pages/flows-home-page.js';

const FACTORIES = [
    flowsResource,
    flowStoreBundlesOp,
    sessionsResource,
    resourcesBundleResource,
    mcpServersResource,
    toolsAllOp,
    integrationsListOp,
    secretsVariablesResource,
    platformWorkItemCountsOp,
    agentSkillsResource,
];

function bootstrapHomeBus() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    return bootstrapTestBus({ slices: collected.slices, effects: collected.effects });
}

describe('flows-home-page HITL / operator link to worktracker', () => {
    let originalFetch;

    beforeEach(() => {
        resetPlatformState();
        originalFetch = window.fetch;
        window.fetch = async (input) => {
            const url = typeof input === 'string' ? input : input.url;
            if (url.includes('/worktracker/api/v1/work-items/mine/summary')) {
                return new Response(
                    JSON.stringify({ assigned_open_count: 3, queue_inbox_count: 4 }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } },
                );
            }
            return new Response(
                JSON.stringify({ items: [], total: 0, limit: 200, offset: 0 }),
                { status: 200, headers: { 'Content-Type': 'application/json' } },
            );
        };
    });

    afterEach(() => {
        window.fetch = originalFetch;
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

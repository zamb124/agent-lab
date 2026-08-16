/**
 * Fullscreen WorkItem page (layout=page) must give HITL chat a specified height.
 * Conversation shell is height:100%; min-height on the wrapper does not resolve %.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents, TEAM_EVENTS } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { workItemsResource } from '../../../../apps/worktracker/ui/events/resources/work-items.resource.js';
import { WorktrackerApp } from '../../../../apps/worktracker/ui/app/worktracker-app.js';
import worktrackerEn from '../../../../core/i18n/translations/en/worktracker.json' with { type: 'json' };
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import '../../../../apps/worktracker/ui/components/work-item-detail-editor.js';

const WORK_ITEM_ID = 'wi_hitl_page_height';

const HANDOFF_ITEM = {
    work_item_id: WORK_ITEM_ID,
    title: 'HITL page chat',
    description: '',
    kind: 'operator_handoff',
    state: 'open',
    priority: 'normal',
    created_at: '2026-08-16T12:00:00Z',
    updated_at: '2026-08-16T12:00:00Z',
    interaction_policy: {
        mode: 'single_reply',
        can_send: true,
        can_complete: true,
        conversation: {
            flow_id: 'flow_hitl',
            context_id: 'ctx_hitl',
            session_id: 'flow_hitl:ctx_hitl',
            a2a_task_id: 'task_hitl',
        },
    },
};

function seedI18n() {
    const bus = getPlatformBus();
    const prevEn = bus.getState().i18n.translations.en;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        {
            locale: 'en',
            bundle: {
                ...prevEn,
                ...platformEn,
                platform: platformEn,
                worktracker: worktrackerEn,
            },
        },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'worktracker' },
        { source: 'system' },
    );
}

function jsonResponse(body) {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });
}

describe('work-item-detail-editor HITL page chat height', () => {
    let originalFetch;

    beforeEach(() => {
        resetPlatformState();
        setDefaultI18nNamespace('worktracker');
        bootstrapTestBus({ factories: WorktrackerApp.factories });
        seedI18n();
        getPlatformBus().dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items: [] }, { source: 'local' });
        getPlatformBus().dispatch(
            workItemsResource.events.ITEM_LOADED,
            { item: HANDOFF_ITEM },
            { source: 'local' },
        );

        originalFetch = window.fetch;
        window.fetch = async (input) => {
            const url = typeof input === 'string' ? input : input.url;
            if (url.includes(`/work-items/${WORK_ITEM_ID}/comments`)) {
                return jsonResponse([]);
            }
            if (url.includes(`/work-items/${WORK_ITEM_ID}`) && !url.includes('/comments')) {
                return jsonResponse(HANDOFF_ITEM);
            }
            if (url.includes('/hitl/') && url.includes('/conversation')) {
                return jsonResponse({ turns: [] });
            }
            if (url.includes('/api/team/members')) {
                return jsonResponse({ items: [] });
            }
            return jsonResponse({});
        };
    });

    afterEach(() => {
        window.fetch = originalFetch;
        fixtureCleanup();
    });

    it('layout=page: platform-flow-ui fills .wt-hitl-chat (not 0px)', async () => {
        const el = await fixture(html`
            <work-item-detail-editor
                layout="page"
                work-item-id=${WORK_ITEM_ID}
            ></work-item-detail-editor>
        `);
        await elementUpdated(el);
        await aTimeout(0);

        const chat = el.shadowRoot.querySelector('.wt-hitl-chat');
        expect(chat, '.wt-hitl-chat').to.exist;
        const flowUi = chat.querySelector('platform-flow-ui');
        expect(flowUi, 'platform-flow-ui').to.exist;

        expect(chat.clientHeight).to.be.greaterThan(200);
        expect(flowUi.clientHeight).to.be.greaterThan(200);
        expect(Math.abs(flowUi.clientHeight - chat.clientHeight)).to.be.lessThan(8);
    });
});

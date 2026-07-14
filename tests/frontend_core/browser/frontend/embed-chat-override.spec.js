/**
 * Smoke: create-embed-modal — inherit/override toggle для chat_override.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { embedConfigsResource } from '../../../../apps/frontend/ui/events/resources/embed.resource.js';
import { flowsCatalogOp } from '../../../../apps/frontend/ui/events/resources/flows-catalog.resource.js';
import '../../../../apps/frontend/ui/modals/create-embed-modal.js';

const FACTORIES = [embedConfigsResource, flowsCatalogOp];

const FLOW_WITH_CHAT = {
    flow_id: 'demo_flow',
    name: 'Demo flow',
    type: 'local',
    branches: { default: { name: 'Default' } },
    chat: {
        show_reasoning: false,
        tool_calls_display: 'compact',
        show_activity: true,
        show_skill_loads: true,
        errors_display: 'generic',
        show_run_trace: false,
        show_trace_actions: false,
        show_browser_previews: true,
        show_files_panel: true,
        allow_cancel: true,
        greeting_message: null,
        suggested_prompts: [],
    },
};

describe('frontend-create-embed-modal chat override', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('без override показывает read-only platform-chat-settings-fields', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        const bus = bootstrapTestBus({ slices: collected.slices, effects: [] });
        bus.dispatch('frontend/flows_catalog/succeeded', {
            result: { flows: [FLOW_WITH_CHAT], tools: [] },
        });

        const el = await fixture(html`
            <frontend-create-embed-modal .open=${true}></frontend-create-embed-modal>
        `);
        await elementUpdated(el);

        el._flowId = 'demo_flow';
        el._name = 'Widget';
        await elementUpdated(el);

        const fields = el.shadowRoot.querySelector('platform-chat-settings-fields');
        expect(fields).to.not.equal(null);
        expect(fields.disabled).to.equal(true);
        expect(el._chatOverrideEnabled).to.equal(false);
    });

    it('toggle override включает редактирование и сохраняет partial patch', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        const bus = bootstrapTestBus({ slices: collected.slices, effects: [] });
        bus.dispatch('frontend/flows_catalog/succeeded', {
            result: { flows: [FLOW_WITH_CHAT], tools: [] },
        });

        const el = await fixture(html`
            <frontend-create-embed-modal .open=${true}></frontend-create-embed-modal>
        `);
        await elementUpdated(el);

        el._flowId = 'demo_flow';
        el._name = 'Widget';
        await elementUpdated(el);

        const toggle = el.shadowRoot.querySelector('.chat-policy-section input[type="checkbox"]');
        expect(toggle).to.not.equal(null);
        toggle.click();
        await elementUpdated(el);

        expect(el._chatOverrideEnabled).to.equal(true);
        const fields = el.shadowRoot.querySelector('platform-chat-settings-fields');
        expect(fields.disabled).to.equal(false);

        fields.dispatchEvent(
            new CustomEvent('chat-changed', {
                detail: { patch: { show_reasoning: true } },
                bubbles: true,
                composed: true,
            }),
        );
        await elementUpdated(el);

        expect(el._buildChatOverridePayload()).to.deep.equal({ show_reasoning: true });

        const resetBtn = el.shadowRoot.querySelector('platform-button');
        expect(resetBtn).to.not.equal(null);
        resetBtn.click();
        await elementUpdated(el);

        expect(el._chatOverrideEnabled).to.equal(false);
        expect(el._buildChatOverridePayload()).to.equal(null);
    });
});

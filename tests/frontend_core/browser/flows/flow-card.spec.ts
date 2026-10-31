/**
 * flow-card: cover gradient uses platform tokens, action chrome on platform-button.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-button.js';
import '../../../../apps/flows/ui/components/flow-card.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

describe('flow-card design tokens', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ slices: {}, effects: [] });
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('avatar background uses --flows-cover-gradient token var', async () => {
        const el = await fixture<TestEl>(html`
            <flow-card .flow=${{
                flow_id: 'demo_flow',
                name: 'Demo Flow',
                branches: {},
            }}></flow-card>
        `);
        await elementUpdated(el);

        const avatar = q(shadow(el), '.flow-avatar');
        expect(avatar).to.not.equal(null);
        const background = avatar!.style.background;
        expect(background).to.include('var(--flows-cover-gradient-');
        expect(background).to.not.include('#');
    });

    it('flow actions render platform-button', async () => {
        const el = await fixture<TestEl>(html`
            <flow-card
                expanded
                .flow=${{
                    flow_id: 'demo_flow',
                    name: 'Demo Flow',
                    branches: { main: { name: 'Main' } },
                }}
            ></flow-card>
        `);
        await elementUpdated(el);

        const buttons = qsa(shadow(el), '.flow-actions platform-button');
        expect(buttons.length).to.equal(3);
    });
});

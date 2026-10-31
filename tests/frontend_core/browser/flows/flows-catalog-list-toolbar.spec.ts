/**
 * flows-catalog-list — inline help in search toolbar (no external .catalog-help).
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { flowsResource, branchRemoveOp } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/components/flows-catalog-list.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

const CATALOG_FACTORIES = [flowsResource, branchRemoveOp];

describe('flows-catalog-list search toolbar', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of CATALOG_FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(CATALOG_FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });
    });

    it('toolbar has search with inline help and create button only', async () => {
        const el = await fixture<TestEl>(html`
            <flows-catalog-list mode="sidebar"></flows-catalog-list>
        `);
        await el.updateComplete;

        const toolbar = q(shadow(el), '.flows-toolbar');
        expect(toolbar).to.not.equal(null);
        expect(q(toolbar!, '.catalog-help')).to.equal(null);
        expect(qsa(toolbar!, 'platform-modal-search-field').length).to.equal(1);
        expect(qsa(toolbar!, 'platform-button').length).to.equal(1);

        const search = q(toolbar!, 'platform-modal-search-field');
        const helpHint = q(toolbar!, 'platform-help-hint');
        expect(helpHint).to.not.equal(null);
        expect(search!.contains(helpHint)).to.equal(true);
    });
});

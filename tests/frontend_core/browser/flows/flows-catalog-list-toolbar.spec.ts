/**
 * flows-catalog-list — inline help in search toolbar (no external .catalog-help).
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { flowsResource, branchRemoveOp } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/components/flows-catalog-list.js';

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
        const el = await fixture(html`
            <flows-catalog-list mode="sidebar"></flows-catalog-list>
        `);
        await el.updateComplete;

        const toolbar = el.shadowRoot.querySelector('.flows-toolbar');
        expect(toolbar).to.not.equal(null);
        expect(toolbar.querySelector('.catalog-help')).to.equal(null);
        expect(toolbar.querySelectorAll('platform-modal-search-field').length).to.equal(1);
        expect(toolbar.querySelectorAll('platform-button').length).to.equal(1);

        const search = toolbar.querySelector('platform-modal-search-field');
        const helpHint = toolbar.querySelector('platform-help-hint');
        expect(helpHint).to.not.equal(null);
        expect(search.contains(helpHint)).to.equal(true);
    });
});

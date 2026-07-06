/**
 * Smoke: кнопка «Настройки агента» в flows-editor-header открывает flows.flow_edit.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    flowsResource,
    flowUpdateOp,
    flowReloadFromBundleOp,
} from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-editor-header.js';

const FACTORIES = [editorResource, flowsResource, flowUpdateOp, flowReloadFromBundleOp];

describe('flows-editor-header flow settings entry', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('кнопка flow-settings вызывает openModal(flows.flow_edit)', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo"></flows-editor-header>
        `);
        await elementUpdated(el);

        const btn = el.shadowRoot.querySelector('[data-action="flow-settings"]');
        expect(btn).to.not.equal(null);

        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        btn.click();
        await elementUpdated(el);

        expect(opened).to.deep.equal({ kind: 'flows.flow_edit', props: { flowId: 'flow-demo' } });
    });
});

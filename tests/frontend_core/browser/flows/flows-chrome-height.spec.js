/**
 * Flows chrome density contract — shared control heights on editor/evaluation surfaces.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, nextFrame } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import {
    flowsResource,
    flowUpdateOp,
    flowReloadFromBundleOp,
    branchRemoveOp,
} from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-editor-header.js';
import '../../../../apps/flows/ui/components/evaluation/flows-evaluation-run-toolbar.js';

const FACTORIES = [editorResource, flowsResource, flowUpdateOp, flowReloadFromBundleOp, branchRemoveOp];

function buttonHeight(platformButton) {
    return platformButton.shadowRoot.querySelector('button').getBoundingClientRect().height;
}

describe('flows chrome height canon', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('editor header icon-only buttons stay within chrome tier (28–32px)', async () => {
        for (const factory of FACTORIES) {
            registerFactory(factory);
        }
        const collected = collectFactories(FACTORIES);
        bootstrapTestBus({ slices: collected.slices, effects: [] });

        const el = await fixture(html`
            <flows-editor-header flow-id="flow-demo" branch-id="base"></flows-editor-header>
        `);
        await elementUpdated(el);

        const iconButtons = [...el.shadowRoot.querySelectorAll('platform-button[icon-only]')];
        expect(iconButtons.length).to.be.greaterThan(0);

        for (const btn of iconButtons) {
            const height = buttonHeight(btn);
            expect(height).to.be.at.least(27);
            expect(height).to.be.at.most(33);
        }

        const heights = iconButtons.map((btn) => buttonHeight(btn));
        const delta = Math.max(...heights) - Math.min(...heights);
        expect(delta).to.be.at.most(4);
    });

    it('evaluation run toolbar shell uses flows toolbar min-height token', async () => {
        bootstrapTestBus();

        const el = await fixture(html`
            <div style="--flows-toolbar-shell-min-height: 48px;">
                <flows-evaluation-run-toolbar
                    branch-id="base"
                    .selectedSuite=${{ suite_id: 's1', name: 'Suite' }}
                    .selectedCase=${{ case_id: 'c1', name: 'Case' }}
                    .caseTemplates=${[]}
                    run-scope="suite"
                    trials="1"
                    max-concurrency="1"
                ></flows-evaluation-run-toolbar>
            </div>
        `);
        await nextFrame();

        const toolbar = el.querySelector('flows-evaluation-run-toolbar').shadowRoot.querySelector('.toolbar');
        expect(toolbar).to.not.equal(null);

        const styles = getComputedStyle(toolbar);
        expect(parseFloat(styles.minHeight)).to.be.closeTo(48, 2);
    });
});

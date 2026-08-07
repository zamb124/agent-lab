/**
 * Browser: opening the Interface editor must settle.
 *
 * The editor has two feedback paths that mutate the document from a measurement
 * (grid-first migrate and row autofit). Each one is allowed exactly one pass, so
 * entering the editor emits a bounded number of `interface-change` events instead
 * of spinning the frame — a reboot loop there costs a page load per iteration.
 */

import { expect, fixture, fixtureCleanup, html } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import { interfaceEditorSlice } from '../../../../apps/flows/ui/events/resources/interface-editor.resource.js';
import { buildFlowUIPageTemplatePreviewDocument } from '@platform/lib/flow-ui/templates/gallery/preview-document.js';
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-editor.js';

function seedFlowsTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...previous, flows: flowsEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'flows' },
        { source: 'system' },
    );
}

/** Chat is the default template every flow opens with. */
function chatInterfaceConfig() {
    const document = buildFlowUIPageTemplatePreviewDocument('linnex.page.chat', 'en');
    return {
        template: { template_id: 'linnex.page.chat', document },
        policy: document.policy,
    };
}

async function settle(frames = 12) {
    for (let index = 0; index < frames; index += 1) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
    }
}

describe('flows-interface-editor settles on open', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: [interfaceEditorSlice] });
        seedFlowsTranslations();
    });
    afterEach(() => fixtureCleanup());

    it('emits a bounded number of interface-change events', async () => {
        let config = chatInterfaceConfig();
        let changes = 0;
        const editor = await fixture(html`
            <flows-interface-editor
                .interfaceConfig=${config}
                .flowId=${'flow-1'}
                .branchId=${'default'}
            ></flows-interface-editor>
        `);
        // Feed emitted configs back exactly like flow-editor-page does.
        editor.addEventListener('interface-change', (event) => {
            changes += 1;
            if (changes > 40) return;
            config = event.detail.config;
            editor.interfaceConfig = config;
        });
        await editor.updateComplete;
        await settle();

        expect(changes, `interface-change fired ${changes} times`).to.be.at.most(2);
    });

    it('does not re-run the grid migrate for a document it already normalized', async () => {
        const editor = await fixture(html`
            <flows-interface-editor
                .interfaceConfig=${chatInterfaceConfig()}
                .flowId=${'flow-1'}
                .branchId=${'default'}
            ></flows-interface-editor>
        `);
        let changes = 0;
        editor.addEventListener('interface-change', (event) => {
            changes += 1;
            editor.interfaceConfig = event.detail.config;
        });
        // Re-open with a fresh config so the listener sees the migrate of this document.
        editor.interfaceConfig = chatInterfaceConfig();
        await editor.updateComplete;
        await settle();
        const afterOpen = changes;
        expect(afterOpen).to.be.at.most(1);

        // Re-wrapping the settled config keeps the same document, so nothing re-runs.
        editor.interfaceConfig = { ...editor.interfaceConfig };
        await editor.updateComplete;
        await settle();
        expect(changes).to.equal(afterOpen);
    });
});

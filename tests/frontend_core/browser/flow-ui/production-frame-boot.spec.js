/**
 * Browser: the production frame boots once. Booting re-imports the whole runtime
 * bundle, fonts and tokens, so authoring edits must travel over the open
 * MessageChannel instead of rewriting `srcdoc` (otherwise every edit costs a full
 * page load worth of requests).
 */

import { expect, fixture, fixtureCleanup, html } from '../helpers/render.js';
import '@platform/lib/flow-ui/rendering/production-render-frame.js';

function documentAtRevision(revision) {
    return {
        schema_version: '1.0',
        document_id: 'doc-1',
        context_id: 'ctx-1',
        revision,
        active_page_id: 'main',
        pages: { main: { page_id: 'main', title: 'Main', root_surface_id: 'main' } },
        surfaces: {
            main: {
                surface_id: 'main',
                root_component_id: 'root',
                components: {
                    root: {
                        component_id: 'root',
                        type: 'PageShell',
                        kind: 'container',
                        children: [],
                        container_layout: {
                            mode: 'grid',
                            grid: { columns_by_band: { wide: 12, medium: 8, compact: 4 } },
                        },
                    },
                },
            },
        },
        values: {},
    };
}

/** Count srcdoc writes: one write == one full child bundle load. */
function watchBoots(frame) {
    const iframe = frame.renderRoot.querySelector('iframe');
    const state = { boots: 0 };
    const observer = new MutationObserver((records) => {
        for (const record of records) {
            if (record.attributeName === 'srcdoc' && iframe.hasAttribute('srcdoc')) state.boots += 1;
        }
    });
    observer.observe(iframe, { attributes: true, attributeFilter: ['srcdoc'] });
    state.stop = () => observer.disconnect();
    return state;
}

describe('flow-ui production frame boot cost', () => {
    afterEach(() => fixtureCleanup());

    it('boots once and pushes later documents over the channel', async () => {
        const frame = await fixture(html`
            <flow-ui-production-render-frame
                .document=${documentAtRevision(1)}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="en"
            ></flow-ui-production-render-frame>
        `);
        await frame.updateComplete;
        const watch = watchBoots(frame);

        for (let revision = 2; revision <= 6; revision += 1) {
            frame.document = documentAtRevision(revision);
            await frame.updateComplete;
        }
        watch.stop();
        expect(watch.boots).to.equal(0);
    });

    it('reboots when a boot-level input changes', async () => {
        const frame = await fixture(html`
            <flow-ui-production-render-frame
                .document=${documentAtRevision(1)}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="en"
            ></flow-ui-production-render-frame>
        `);
        await frame.updateComplete;
        const watch = watchBoots(frame);

        frame.locale = 'ru';
        await frame.updateComplete;
        frame.display = 'panel';
        await frame.updateComplete;
        watch.stop();
        expect(watch.boots).to.equal(2);
    });

    it('selection changes never reboot the frame', async () => {
        const frame = await fixture(html`
            <flow-ui-production-render-frame
                .document=${documentAtRevision(1)}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="en"
            ></flow-ui-production-render-frame>
        `);
        await frame.updateComplete;
        const watch = watchBoots(frame);

        frame.selectedComponentId = 'root';
        await frame.updateComplete;
        frame.selectedComponentId = '';
        await frame.updateComplete;
        watch.stop();
        expect(watch.boots).to.equal(0);
    });
});

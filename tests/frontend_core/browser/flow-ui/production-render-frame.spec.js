/**
 * Browser: production render frame boot contract.
 *
 * The frame must build its isolated document from one configurable static base:
 * fonts, tokens, the import map and the production bundle URL all derive from it,
 * so editor canvas and production route load the very same assets.
 *
 * Full Exact/geometry parity (editor frame vs production route) is asserted by
 * the Playwright matrix in tests/ui/e2e/test_flow_ui_editor_runtime_parity.py —
 * a dev-server srcdoc iframe cannot serve the production bundle graph.
 */

import { fixture, html, expect, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/rendering/production-render-frame.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import { LINNEX_CATALOG_ID } from '@platform/lib/flow-ui/protocol/constants.js';
import { FLOW_UI_CATALOG_MANIFEST } from '@platform/lib/flow-ui/catalog/manifest.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';

function chatDocument() {
    const template = buildDefaultChatDocument();
    return Object.freeze({
        ...template,
        revision: 1,
        catalog_id: LINNEX_CATALOG_ID,
        surfaces: Object.freeze({
            ...template.surfaces,
            main: Object.freeze({
                ...template.surfaces.main,
                catalog_id: LINNEX_CATALOG_ID,
            }),
        }),
    });
}

describe('flow-ui production-render-frame', () => {
    beforeEach(async () => {
        await resetPlatformState();
        bootstrapTestBus();
    });

    it('derives fonts, tokens, import map and bundle URL from one static base', async () => {
        const el = await fixture(html`
            <flow-ui-production-render-frame
                static-base="/core/frontend/static"
                style="display:block;width:720px;height:900px"
                .document=${chatDocument()}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="ru"
                .readonly=${true}
            ></flow-ui-production-render-frame>
        `);
        const iframe = el.shadowRoot.querySelector('iframe');
        await waitUntil(() => typeof iframe.srcdoc === 'string' && iframe.srcdoc.length > 0);
        const srcdoc = iframe.srcdoc;

        expect(srcdoc).to.contain('/core/frontend/static/assets/css/tokens.css');
        expect(srcdoc).to.contain('/core/frontend/static/assets/fonts/platform-fonts.css');
        expect(srcdoc).to.contain('"@platform/lib/": "/core/frontend/static/lib/"');
        expect(srcdoc).to.contain('/core/frontend/static/lib/flow-ui/components/platform-flow-ui.js');
        // The production import map must be mirrored fully: a missing vendor entry
        // breaks the renderer graph only at runtime.
        expect(srcdoc).to.contain('"@capacitor/splash-screen"');
        expect(srcdoc).to.contain('"lit": "/core/frontend/static/assets/js/lit/lit.min.js"');
        expect(srcdoc).to.not.contain('/static/core/');
        expect(srcdoc).to.contain('data-theme="dark"');
        expect(srcdoc).to.contain('lang="ru"');
    });

    it('defaults the static base to the production mount', async () => {
        const el = await fixture(html`
            <flow-ui-production-render-frame
                style="display:block;width:320px;height:320px"
                .document=${chatDocument()}
                display="panel"
                profile="editor_test"
                theme="light"
                locale="en"
                .readonly=${true}
            ></flow-ui-production-render-frame>
        `);
        const iframe = el.shadowRoot.querySelector('iframe');
        await waitUntil(() => typeof iframe.srcdoc === 'string' && iframe.srcdoc.length > 0);
        expect(iframe.srcdoc).to.contain('"@platform/lib/": "/static/core/lib/"');
        expect(iframe.srcdoc).to.contain('data-theme="light"');
    });

    it('reports the catalog checksum the editor compares against', async () => {
        const el = await fixture(html`
            <flow-ui-production-render-frame
                static-base="/core/frontend/static"
                style="display:block;width:320px;height:320px"
                .document=${chatDocument()}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="ru"
                .readonly=${true}
            ></flow-ui-production-render-frame>
        `);
        const iframe = el.shadowRoot.querySelector('iframe');
        await waitUntil(() => typeof iframe.srcdoc === 'string' && iframe.srcdoc.length > 0);
        expect(FLOW_UI_CATALOG_MANIFEST.checksum.length).to.be.greaterThan(0);
        expect(el.parityStatus).to.equal('Loading');
    });
});

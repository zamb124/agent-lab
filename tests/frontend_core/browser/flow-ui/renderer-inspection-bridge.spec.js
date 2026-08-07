/**
 * Browser: renderer inspection bridge collects geometry from platform-flow-ui.
 */

import { fixture, html, expect, waitUntil } from '../helpers/render.js';
import { inspectFlowUIRenderer } from '@platform/lib/flow-ui/rendering/renderer-inspection-bridge.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import { LINNEX_CATALOG_ID } from '@platform/lib/flow-ui/protocol/constants.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';

describe('flow-ui renderer-inspection-bridge', () => {
    beforeEach(async () => {
        await resetPlatformState();
        bootstrapTestBus();
    });

    it('collects component geometry from mounted platform-flow-ui', async () => {
        const template = buildDefaultChatDocument();
        const document = Object.freeze({
            ...template,
            revision: 2,
            catalog_id: LINNEX_CATALOG_ID,
            surfaces: Object.freeze({
                ...template.surfaces,
                main: Object.freeze({
                    ...template.surfaces.main,
                    catalog_id: LINNEX_CATALOG_ID,
                }),
            }),
        });
        const el = await fixture(html`
            <platform-flow-ui
                style="display:block;width:720px;height:640px"
                .initialDocument=${document}
                display="page"
                profile="editor_test"
                theme="dark"
                locale="ru"
                .readonly=${true}
            ></platform-flow-ui>
        `);
        await waitUntil(() => el.parityReady === true || el.hasAttribute('parity-ready'));
        const inspection = inspectFlowUIRenderer(el);
        expect(inspection.revision).to.equal(2);
        expect(inspection.components.length).to.be.at.least(1);
        expect(inspection.components[0].componentId).to.be.a('string');
        expect(inspection.components[0].rect.width).to.be.a('number');
    });

    it('raises when surface is missing', () => {
        const host = document.createElement('div');
        Object.defineProperty(host, 'shadowRoot', {
            value: document.createElement('div'),
        });
        expect(() => inspectFlowUIRenderer(host)).to.throw(/flow-ui-surface missing/);
    });
});

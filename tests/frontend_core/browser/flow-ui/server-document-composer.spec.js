import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import '@platform/lib/flow-ui/components/flow-ui-surface.js';

async function loadServerDocument() {
    const response = await fetch('/tmp/server-chat-doc.json');
    // file:// may not work; embed via import is better — use inline from buildDefault and mutate
    return null;
}

describe('flow-ui server-shaped document', () => {
    afterEach(() => fixtureCleanup());

    it('renders composer when placement has null size tokens like Python dump', async () => {
        const { buildDefaultChatDocument } = await import('@platform/lib/flow-ui/templates/chat-template.js');
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const surface = structuredClone(document.surfaces.main);
        // Mimic Python wire: null tokens on placement.base
        for (const component of Object.values(surface.components)) {
            if (!component.placement) continue;
            component.placement = {
                base: {
                    ...component.placement.base,
                    min_inline_size_token: null,
                    max_inline_size_token: null,
                },
                overrides: component.placement.overrides || {},
            };
        }
        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${surface}
                    .tasks=${[]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        await elementUpdated(host);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);
        const err = surfaceEl.shadowRoot.querySelector('[role="alert"]');
        expect(err, err ? err.textContent : '').to.not.exist;
        const composer = surfaceEl.shadowRoot.querySelector('.field-group--composer');
        expect(composer).to.exist;
        expect(composer.clientHeight).to.be.greaterThan(20);
    });
});

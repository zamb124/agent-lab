/**
 * Smoke: embed-code-modal — секции snippet, token how-to, origins, backend/client examples.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { embedCodeLoadOp } from '../../../../apps/frontend/ui/events/resources/embed.resource.js';
import '../../../../apps/frontend/ui/modals/embed-code-modal.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

const EMBED_ID = 'embed_modal_test';

const CODE_ENTRY = {
    embed_id: EMBED_ID,
    html_code: '<script type="module" src="https://cdn.linnex.io/lib/embed-flow-ui/flow-ui-embed-autoload.js"></script>',
    script_url: 'https://cdn.linnex.io/lib/embed-flow-ui/flow-ui-embed-autoload.js',
    token_endpoint: 'https://api.linnex.io/frontend/api/embed/configs/embed_modal_test/session-token',
    backend_proxy_code: 'async def issue_embed_session_token(...):',
    browser_to_host_backend_code: "await fetch('/api/flow-ui-token', { method: 'POST' })",
    allowed_origins: ['https://customer.example'],
};

describe('frontend-embed-code-modal', () => {
    beforeEach(() => {
        resetPlatformState();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('рендерит 5 секций с snippet, token how-to, origins и reference client example', async () => {
        registerFactory(embedCodeLoadOp);
        const collected = collectFactories([embedCodeLoadOp]);
        const bus = bootstrapTestBus({ slices: collected.slices, effects: collected.effects });

        const el = await fixture<TestEl>(html`
            <frontend-embed-code-modal .embedId=${EMBED_ID}></frontend-embed-code-modal>
        `);
        await elementUpdated(el);

        bus.dispatch('frontend/embed_code/succeeded', { result: CODE_ENTRY });
        el._loaded = true;
        el.open = true;
        await elementUpdated(el);

        const root = shadow(el);
        const sections = qsa(root!, '.section');
        expect(sections.length).to.equal(5);

        const htmlPre = qs(sections[0]!, 'pre');
        expect(htmlPre.textContent).to.include('flow-ui-embed-autoload.js');

        expect(sections[1]!.textContent).to.include('/session-token');
        expect(qsa(sections[1]!, 'li').length).to.equal(3);

        expect(sections[2]!.textContent).to.include('https://customer.example');

        expect(qs(sections[3]!, 'pre').textContent).to.include('issue_embed_session_token');

        const clientSection = sections[4];
        const clientDesc = q(clientSection!, '.section-desc');
        expect(clientDesc).to.not.equal(null);
        expect(clientDesc!.textContent).to.match(/data-token-url|client_backend_example_description/);
        expect(qs(clientSection!, 'pre').textContent).to.include("/api/flow-ui-token");

        expect(qsa(root!, '.copy-btn').length).to.be.at.least(4);
    });
});

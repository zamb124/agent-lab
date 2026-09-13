/**
 * Блок ``html``: iframe c opaque origin (``sandbox="allow-scripts"``), CSP в srcdoc, мост
 * ``flowUi`` — state по ``data-bind``, ``send`` → ``onAction``, ``setValue`` → ``onValue``,
 * ошибки автора видны под блоком.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/blocks/html.js';
import { FLOW_UI_HTML_CSP, FLOW_UI_HTML_MIN_HEIGHT, FLOW_UI_HTML_SANDBOX, readThemeTokens } from '@platform/lib/flow-ui/runtime/html-sandbox.js';

function htmlBlock(source, { field = null, height = 'auto', fields = [] } = {}) {
    return { block_id: 'custom', type: 'html', visible_when: null, source, height, fields, field };
}

async function mount(block, { state = {}, onAction = null, onValue = null, readonly = false } = {}) {
    const events = [];
    const element = await fixture(html`<flow-ui-html-block
        .block=${block}
        .state=${state}
        .onAction=${onAction}
        .onValue=${onValue}
        .onBridgeEvent=${(event) => events.push(event)}
        ?readonly=${readonly}
    ></flow-ui-html-block>`);
    const iframe = element.renderRoot.querySelector('iframe');
    await new Promise((resolve) => {
        if (iframe.contentDocument && iframe.contentDocument.readyState === 'complete' && iframe.contentDocument.body.childElementCount > 0) resolve();
        else iframe.addEventListener('load', () => resolve(), { once: true });
    });
    return { element, iframe, events };
}

describe('flow-ui-html-block', function () {
    this.timeout(10_000);

    afterEach(() => fixtureCleanup());

    it('renders an isolated iframe with the fixed CSP and binds state into the document', async () => {
        const { element, iframe, events } = await mount(
            htmlBlock('<p id="who" data-bind="customer.name"></p><p data-show="vip" id="vip">VIP</p>'),
            { state: { customer: { name: 'Анна' }, vip: false } },
        );
        expect(iframe.getAttribute('sandbox')).to.equal(FLOW_UI_HTML_SANDBOX);
        expect(FLOW_UI_HTML_SANDBOX).to.not.contain('allow-same-origin');
        expect(iframe.srcdoc).to.contain(`<meta http-equiv="Content-Security-Policy" content="${FLOW_UI_HTML_CSP}">`);
        expect(iframe.contentDocument, 'opaque origin must hide the document').to.equal(null);
        await waitUntil(() => element._height !== FLOW_UI_HTML_MIN_HEIGHT, 'iframe did not report its height', { timeout: 4000 });
        expect(events.filter((event) => event.kind === 'error')).to.deep.equal([]);
        expect(element.renderRoot.querySelector('.error')).to.equal(null);
    });

    it('routes flowUi.send and flowUi.setValue through the bridge and rejects them in readonly mode', async () => {
        const actions = [];
        const values = [];
        const source = '<script>flowUi.onChange((state) => { if (state.ready) { flowUi.send("save", { plan: "pro" }); flowUi.setValue(state.ready); } });</script>';
        const { element, events } = await mount(htmlBlock(source, { field: 'answer', fields: ['ready'] }), {
            state: { ready: 'yes' },
            onAction: (name, payload) => actions.push({ name, payload }),
            onValue: (value) => values.push(value),
        });
        await waitUntil(() => actions.length > 0 && values.length > 0, 'bridge messages did not arrive', { timeout: 4000 });
        expect(actions[0]).to.deep.equal({ name: 'save', payload: { plan: 'pro' } });
        expect(values[0]).to.equal('yes');
        expect(events.map((event) => event.kind)).to.include.members(['action', 'value']);

        element.readonly = true;
        element.state = { ready: 'again' };
        await elementUpdated(element);
        await waitUntil(() => events.filter((event) => event.kind === 'action').length >= 2, 'second action not observed', { timeout: 4000 });
        expect(actions).to.have.length(1);
    });

    it('surfaces author script errors under the block', async () => {
        const { element } = await mount(htmlBlock('<script>throw new Error("boom")</script>'));
        await waitUntil(() => element.renderRoot.querySelector('.error') !== null, 'error was not reported', { timeout: 4000 });
        expect(element.renderRoot.querySelector('.error').textContent).to.contain('boom');
    });

    it('reattaches the sandbox after the host is moved in the document', async () => {
        const { element } = await mount(
            htmlBlock('<p data-bind="title"></p><div style="height:72px">pad</div>'),
            { state: { title: 'Hi' } },
        );
        await waitUntil(() => element._height > FLOW_UI_HTML_MIN_HEIGHT, 'iframe did not report its height', { timeout: 4000 });
        const holder = document.createElement('div');
        document.body.appendChild(holder);
        holder.appendChild(element);
        await waitUntil(() => element._bridge !== null, 'bridge was not reattached after move');
        await waitUntil(() => element._height > FLOW_UI_HTML_MIN_HEIGHT, 'iframe did not report height after move', { timeout: 4000 });
        holder.remove();
    });

    it('reload() rebuilds srcdoc even when source is unchanged', async () => {
        const { element } = await mount(
            htmlBlock('<p data-bind="title"></p><div style="height:48px">pad</div>'),
            { state: { title: 'Hi' } },
        );
        element.reload();
        await elementUpdated(element);
        await waitUntil(
            () => (element.renderRoot.querySelector('iframe')?.srcdoc || '').includes('<!--r1-->'),
            'reload did not rewrite srcdoc',
            { timeout: 4000 },
        );
        expect(element.renderRoot.querySelector('iframe').srcdoc).to.contain('<p data-bind="title"></p>');
    });

    it('readThemeTokens falls back to documentElement when the host has no tokens', () => {
        document.documentElement.style.setProperty('--flow-ui-text', 'rgb(1, 2, 3)');
        const host = document.createElement('div');
        try {
            expect(readThemeTokens(host)['--flow-ui-text']).to.equal('rgb(1, 2, 3)');
        } finally {
            document.documentElement.style.removeProperty('--flow-ui-text');
        }
    });
});

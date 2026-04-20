/**
 * Smoke: flows-llm-config-editor — расширенные поля + advanced секция.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';
import { modelsListOp } from '../../../../apps/flows/ui/events/resources/models.resource.js';
import { codeCompletionsOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { providersListOp } from '../../../../apps/flows/ui/events/resources/providers.resource.js';
import '../../../../apps/flows/ui/components/editors/flows-llm-config-editor.js';

describe('flows-llm-config-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        registerFactory(modelsListOp);
        registerFactory(codeCompletionsOp);
        registerFactory(providersListOp);
        const collected = collectFactories([modelsListOp, codeCompletionsOp, providersListOp]);
        bootstrapTestBus({ slices: collected.slices });
    });
    afterEach(() => fixtureCleanup());

    it('базовые поля провайдер/модель/temperature/max_tokens', async () => {
        const el = await fixture(html`
            <flows-llm-config-editor .config=${{ provider: 'openai', model: 'gpt-4o' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        const fields = el.shadowRoot.querySelectorAll('.grid > .field');
        expect(fields.length).to.be.greaterThanOrEqual(4);
        const numbers = el.shadowRoot.querySelectorAll('input[type="number"]');
        expect(numbers.length).to.be.greaterThanOrEqual(2);
    });

    it('advanced секция содержит password+url+seed+reasoning_effort', async () => {
        const el = await fixture(html`
            <flows-llm-config-editor .config=${{ api_key: '@var:K' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        const details = el.shadowRoot.querySelector('details');
        expect(details).to.not.be.null;
        details.open = true;
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('input[type="password"]')).to.not.be.null;
        expect(el.shadowRoot.querySelector('flows-json-field-editor')).to.not.be.null;
        const selects = el.shadowRoot.querySelectorAll('select');
        expect(selects.length).to.be.greaterThanOrEqual(2);
    });

    it('emit change удаляет ключ при пустом значении провайдера', async () => {
        const el = await fixture(html`
            <flows-llm-config-editor .config=${{ provider: 'openai' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const select = el.shadowRoot.querySelector('select');
        select.value = '';
        select.dispatchEvent(new Event('change'));
        expect(last.config).to.deep.equal({});
    });
});

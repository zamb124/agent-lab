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
        const numberFields = el.shadowRoot.querySelectorAll('platform-field[type="number"], platform-field[type="integer"]');
        expect(numberFields.length).to.be.greaterThanOrEqual(2);
    });

    it('advanced секция содержит password+url+seed+reasoning_effort', async () => {
        const el = await fixture(html`
            <flows-llm-config-editor .config=${{ api_key: '@var:K' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        const apiPf = el.shadowRoot.querySelector('platform-field[input-type="password"]');
        expect(apiPf).to.not.be.null;
        const apiInner = apiPf.shadowRoot.querySelector('platform-field-string');
        expect(apiInner).to.not.be.null;
        expect(apiInner.shadowRoot.querySelector('input[type="password"]')).to.not.be.null;
        expect(el.shadowRoot.querySelector('flows-json-field-editor')).to.not.be.null;
        const enumFields = el.shadowRoot.querySelectorAll('platform-field[type="enum"]');
        expect(enumFields.length).to.be.greaterThanOrEqual(2);
    });

    it('emit change удаляет ключ при пустом значении провайдера', async () => {
        const el = await fixture(html`
            <flows-llm-config-editor .config=${{ provider: 'openai' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'config')) {
                last = e.detail;
            }
        });
        const providerPf = el.shadowRoot.querySelector('.grid > .field:nth-child(1) platform-field[type="enum"]');
        expect(providerPf).to.not.be.null;
        const providerEnum = providerPf.shadowRoot.querySelector('platform-field-enum');
        expect(providerEnum).to.not.be.null;
        const inp = providerEnum.shadowRoot.querySelector('input.field-pill-enum-input');
        expect(inp).to.not.be.null;
        inp.focus();
        await elementUpdated(providerEnum);
        const emptyOpt = providerEnum.shadowRoot.querySelector('[data-enum-value=""]');
        expect(emptyOpt).to.not.be.null;
        emptyOpt.click();
        await elementUpdated(el);
        expect(last.config).to.deep.equal({});
    });
});

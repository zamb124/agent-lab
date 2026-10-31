/**
 * Smoke: flows-llm-config-editor — расширенные поля + advanced секция.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import { modelsListOp } from '../../../../apps/flows/ui/events/resources/models.resource.js';
import { codeLspSessionOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { providersListOp } from '../../../../apps/flows/ui/events/resources/providers.resource.js';
import '../../../../apps/flows/ui/components/editors/flows-llm-config-editor.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';

describe('flows-llm-config-editor', () => {
    /** @type {typeof platformWs.request | undefined} */
    let originalWsRequest: any;

    beforeEach(() => {
        resetPlatformState();
        registerFactory(modelsListOp);
        registerFactory(codeLspSessionOp);
        registerFactory(providersListOp);
        const collected = collectFactories([modelsListOp, codeLspSessionOp, providersListOp]);
        bootstrapTestBus({ slices: collected.slices });
        originalWsRequest = platformWs.request;
        platformWs.request = async (opts) => {
            if (opts.type === 'flows/registry/providers_list_requested') {
                return { items: ['openrouter'] };
            }
            if (opts.type === 'flows/registry/models_list_requested') {
                return { items: ['test-model'] };
            }
            return originalWsRequest.call(platformWs, opts);
        };
    });
    afterEach(() => {
        if (originalWsRequest !== undefined) {
            platformWs.request = originalWsRequest;
        }
        fixtureCleanup();
    });

    it('базовые поля провайдер/модель/temperature/max_tokens', async () => {
        const el = await fixture<TestEl>(html`
            <flows-llm-config-editor .config=${{ provider: 'openai', model: 'gpt-4o' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        const fields = qsa(shadow(el), '.grid > .field');
        expect(fields.length).to.be.greaterThanOrEqual(4);
        const numberFields = qsa(shadow(el), 'platform-field[type="number"], platform-field[type="integer"]');
        expect(numberFields.length).to.be.greaterThanOrEqual(2);
    });

    it('advanced секция содержит password+url+seed+reasoning_effort', async () => {
        const el = await fixture<TestEl>(html`
            <flows-llm-config-editor .config=${{ api_key: '@var:K' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        const apiPf = qs(shadow(el), 'platform-field[input-type="password"]');
        expect(apiPf).to.not.be.null;
        const apiInner = qs(shadow(apiPf), 'platform-field-string');
        expect(apiInner).to.not.be.null;
        expect(qs(shadow(apiInner), 'input[type="password"]')).to.not.be.null;
        expect(qs(shadow(el), 'platform-json-editor')).to.not.be.null;
        const enumFields = qsa(shadow(el), 'platform-field[type="enum"]');
        expect(enumFields.length).to.be.greaterThanOrEqual(2);
    });

    it('emit change удаляет ключ при пустом значении провайдера', async () => {
        const el = await fixture<TestEl>(html`
            <flows-llm-config-editor .config=${{ provider: 'openai' }}></flows-llm-config-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if ((e as CustomEvent).detail && Object.prototype.hasOwnProperty.call((e as CustomEvent).detail, 'config')) {
                last = (e as CustomEvent).detail;
            }
        });
        const providerPf = qs(shadow(el), '.grid > .field:nth-child(1) platform-field[type="enum"]');
        expect(providerPf).to.not.be.null;
        const providerEnum = qs(shadow(providerPf), 'platform-field-enum');
        expect(providerEnum).to.not.be.null;
        const inp = qs(shadow(providerEnum), 'input.field-pill-enum-input');
        expect(inp).to.not.be.null;
        inp.focus();
        await elementUpdated(providerEnum);
        const emptyOpt = qs(shadow(providerEnum), '[data-enum-value=""]');
        expect(emptyOpt).to.not.be.null;
        (emptyOpt as TestEl).click();
        await elementUpdated(el);
        expect(last!.config).to.deep.equal({});
    });
});
